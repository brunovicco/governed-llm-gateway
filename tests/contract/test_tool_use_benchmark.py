"""Tool-use v1 benchmark contract and end-to-end evidence tests."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import (
    BenchmarkCase,
    BenchmarkTarget,
    BenchmarkWorkload,
    ObservationStatus,
    ProviderCall,
)
from benchmarks.promotion import PromotionMapping, promote_snapshot
from benchmarks.runner import BenchmarkProviderFailure, BenchmarkRunner
from benchmarks.scoring import build_default_scorers
from benchmarks.snapshot import build_snapshot, dataset_digest
from benchmarks.workloads.tool_use import (
    assess_tool_use,
    load_tool_use_dataset,
    score_tool_use,
)

_DATASET = Path("benchmarks/datasets/tool-use-v1.json")


class _CanonicalToolExecutor:
    """Fixture returning reviewed tool proposals without executing tools."""

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        return ProviderCall(
            output=case.expected,
            latency_ms=18,
            ttft_ms=7,
            input_units=16,
            output_units=6,
            cost_usd=Decimal("0.001"),
        )


class _MixedToolExecutor:
    """Fixture separating one provider failure from one completed quality failure."""

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        if case.case_id.endswith("weather_001"):
            raise BenchmarkProviderFailure(code="timeout", status_code=504, latency_ms=250)
        if case.case_id.endswith("order_001"):
            return ProviderCall(
                output={"name": "cancel_order", "arguments": {"order_id": "ORD-42"}},
                latency_ms=20,
            )
        return ProviderCall(output=case.expected, latency_ms=15)


def test_tool_use_dataset_is_public_synthetic_and_never_executes_tools() -> None:
    dataset = load_tool_use_dataset(_DATASET)

    assert dataset.benchmark_version == "tool-use-v1"
    assert dataset.data_classification == "public"
    assert len(dataset.cases) == 6
    assert len({case.case_id for case in dataset.cases}) == 6
    assert all(case.workload is BenchmarkWorkload.TOOL_USE for case in dataset.cases)
    assert all(case.metadata["synthetic"] is True for case in dataset.cases)
    assert all(case.metadata["execute_tool"] is False for case in dataset.cases)
    assert sum(case.expected is None for case in dataset.cases) == 1


def test_tool_use_dataset_digest_is_deterministic() -> None:
    first = load_tool_use_dataset(_DATASET)
    second = load_tool_use_dataset(_DATASET)

    assert dataset_digest(first.cases) == dataset_digest(second.cases)


def test_tool_use_scorer_separates_selection_and_arguments() -> None:
    case = load_tool_use_dataset(_DATASET).cases[0]

    exact = assess_tool_use(case, case.expected)
    assert exact.score == Decimal("1")
    assert exact.selection_score == Decimal("1")
    assert exact.arguments_score == Decimal("1")
    assert exact.issues == ()

    missing_argument = assess_tool_use(
        case,
        {"name": "get_weather", "arguments": {"city": "São Paulo"}},
    )
    assert missing_argument.score == Decimal("0.5")
    assert missing_argument.selection_score == Decimal("1")
    assert missing_argument.arguments_score == Decimal("0")
    assert ("missing_argument", "/arguments/date") in {
        (issue.code, issue.path) for issue in missing_argument.issues
    }

    wrong_allowed_tool = assess_tool_use(
        case,
        {
            "name": "search_docs",
            "arguments": {"city": "São Paulo", "date": "2026-09-06"},
        },
    )
    assert wrong_allowed_tool.score == Decimal("0.5")
    assert wrong_allowed_tool.selection_score == Decimal("0")
    assert wrong_allowed_tool.arguments_score == Decimal("1")
    assert ("wrong_tool", "/name") in {
        (issue.code, issue.path) for issue in wrong_allowed_tool.issues
    }


def test_tool_use_rejects_undeclared_tool_and_invalid_shape() -> None:
    case = load_tool_use_dataset(_DATASET).cases[0]

    undeclared = assess_tool_use(
        case,
        {"name": "delete_everything", "arguments": {}},
    )
    assert undeclared.score == Decimal("0")
    assert len(undeclared.issues) == 1
    assert undeclared.issues[0].code == "undeclared_tool"
    assert undeclared.issues[0].path == "/name"

    assert score_tool_use(
        case,
        {
            "name": "get_weather",
            "arguments": {"city": "São Paulo", "date": "2026-09-06"},
            "extra": True,
        },
    ) == Decimal("0")


def test_tool_use_arguments_are_recursive_and_type_sensitive() -> None:
    dataset = load_tool_use_dataset(_DATASET)
    customer = next(case for case in dataset.cases if case.case_id.endswith("customer_001"))
    ticket = next(case for case in dataset.cases if case.case_id.endswith("ticket_001"))

    customer_assessment = assess_tool_use(
        customer,
        {
            "name": "get_customer",
            "arguments": {"customer_id": "C-100", "include_contacts": 1},
        },
    )
    assert customer_assessment.score == Decimal("0.5")
    assert ("wrong_argument_type", "/arguments/include_contacts") in {
        (issue.code, issue.path) for issue in customer_assessment.issues
    }

    ticket_assessment = assess_tool_use(
        ticket,
        {
            "name": "create_ticket",
            "arguments": {
                "priority": "critical",
                "requester": {"team": "payments", "region": "US"},
                "tags": ["api"],
            },
        },
    )
    assert ticket_assessment.score == Decimal("0.5")
    issue_pairs = {(issue.code, issue.path) for issue in ticket_assessment.issues}
    assert ("wrong_argument_value", "/arguments/requester/region") in issue_pairs
    assert ("argument_array_length_mismatch", "/arguments/tags") in issue_pairs


def test_tool_use_explicitly_scores_abstention() -> None:
    case = load_tool_use_dataset(_DATASET).cases[-1]

    assert case.expected is None
    assert score_tool_use(case, None) == Decimal("1")

    unexpected = assess_tool_use(
        case,
        {"name": "get_customer", "arguments": {"customer_id": "C-100"}},
    )
    assert unexpected.score == Decimal("0")
    assert ("unexpected_tool_call", "/") in {
        (issue.code, issue.path) for issue in unexpected.issues
    }


def test_tool_use_runner_keeps_provider_failure_separate_from_quality_failure() -> None:
    dataset = load_tool_use_dataset(_DATASET)
    target = BenchmarkTarget(
        target_id="fixture-tool-use-mixed",
        provider="fixture",
        model="tool-model",
        api="fixture-v1",
        configuration="temperature=0;tool_execution=false",
        source_date=date(2026, 9, 5),
    )
    runner = BenchmarkRunner(_MixedToolExecutor(), build_default_scorers())

    observations, scorecards = asyncio.run(runner.run(dataset.cases, (target,)))

    by_case = {item.case_id: item for item in observations}
    weather = by_case["tool_use.weather_001"]
    order = by_case["tool_use.order_001"]
    assert weather.status is ObservationStatus.PROVIDER_FAILURE
    assert weather.quality_score is None
    assert weather.provider_error_code == "timeout"
    assert order.status is ObservationStatus.QUALITY_FAILURE
    assert order.quality_score == Decimal("0.5")
    assert order.provider_error_code is None

    scorecard = scorecards[0]
    assert scorecard.provider_failures == 1
    assert scorecard.completed_calls == 5
    assert scorecard.quality_failures == 1
    assert scorecard.quality_successes == 4


def test_tool_use_pipeline_reaches_deterministic_snapshot_and_explicit_promotion() -> None:
    dataset = load_tool_use_dataset(_DATASET)
    target = BenchmarkTarget(
        target_id="fixture-tool-use-v1",
        provider="fixture",
        model="tool-model",
        api="fixture-v1",
        configuration="temperature=0;tool_execution=false",
        source_date=date(2026, 9, 5),
    )
    runner = BenchmarkRunner(_CanonicalToolExecutor(), build_default_scorers())

    observations, scorecards = asyncio.run(runner.run(dataset.cases, (target,)))

    assert len(observations) == 6
    assert all(item.status is ObservationStatus.SUCCEEDED for item in observations)
    assert all(item.quality_score == Decimal("1") for item in observations)
    scorecard = scorecards[0]
    assert scorecard.workload is BenchmarkWorkload.TOOL_USE
    assert scorecard.total_cases == 6
    assert scorecard.mean_quality_score == Decimal("1")
    assert scorecard.total_cost_usd == Decimal("0.006")

    snapshot = build_snapshot(
        benchmark_version=dataset.benchmark_version,
        runner_version="tool-use-runner-v1",
        run_date=date(2026, 9, 5),
        cases=dataset.cases,
        targets=(target,),
        observations=observations,
        scorecards=scorecards,
    )
    repeated = build_snapshot(
        benchmark_version=dataset.benchmark_version,
        runner_version="tool-use-runner-v1",
        run_date=date(2026, 9, 5),
        cases=dataset.cases,
        targets=(target,),
        observations=observations,
        scorecards=scorecards,
    )
    assert repeated.snapshot_id == snapshot.snapshot_id

    promoted = promote_snapshot(
        snapshot,
        promotion_version="tool-use-promotion-v1",
        approval_date=date(2026, 9, 5),
        approved_by="benchmark-review",
        mappings=(
            PromotionMapping(
                target_id=target.target_id,
                benchmark_workload=BenchmarkWorkload.TOOL_USE,
                deployment_id="fixture-deployment",
                runtime_workload="benchmark.tool_use",
            ),
        ),
    )

    assert promoted.benchmark_snapshot_id == snapshot.snapshot_id
    assert promoted.records[0].quality_score == Decimal("1")
