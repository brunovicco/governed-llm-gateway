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
from benchmarks.runner import BenchmarkRunner
from benchmarks.scoring import build_default_scorers
from benchmarks.snapshot import build_snapshot
from benchmarks.workloads.tool_use import load_tool_use_dataset, score_tool_use

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


def test_tool_use_dataset_is_public_synthetic_and_never_executes_tools() -> None:
    dataset = load_tool_use_dataset(_DATASET)

    assert dataset.benchmark_version == "tool-use-v1"
    assert dataset.data_classification == "public"
    assert len(dataset.cases) == 6
    assert all(case.workload is BenchmarkWorkload.TOOL_USE for case in dataset.cases)
    assert all(case.metadata["execute_tool"] is False for case in dataset.cases)


def test_tool_use_scorer_separates_tool_selection_and_arguments() -> None:
    case = load_tool_use_dataset(_DATASET).cases[0]

    assert score_tool_use(case, case.expected) == Decimal("1")
    assert score_tool_use(
        case,
        {"name": "get_weather", "arguments": {"city": "São Paulo"}},
    ) == Decimal("0.5")
    assert score_tool_use(
        case,
        {
            "name": "search_docs",
            "arguments": {"city": "São Paulo", "date": "2026-09-06"},
        },
    ) == Decimal("0.5")
    assert score_tool_use(
        case,
        {"name": "delete_everything", "arguments": {}},
    ) == Decimal("0")
    assert score_tool_use(
        case,
        {
            "name": "get_weather",
            "arguments": {"city": "São Paulo", "date": "2026-09-06"},
            "extra": True,
        },
    ) == Decimal("0")


def test_tool_use_arguments_are_type_sensitive() -> None:
    case = load_tool_use_dataset(_DATASET).cases[-1]

    assert score_tool_use(
        case,
        {
            "name": "get_customer",
            "arguments": {"customer_id": "C-100", "include_contacts": 1},
        },
    ) == Decimal("0.5")


def test_tool_use_pipeline_reaches_explicit_promotion() -> None:
    dataset = load_tool_use_dataset(_DATASET)
    target = BenchmarkTarget(
        target_id="fixture-tool-use-v1",
        provider="fixture",
        model="tool-model",
        api="fixture-v1",
        configuration="temperature=0;tool_execution=false",
        source_date=date(2026, 9, 4),
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
        run_date=date(2026, 9, 4),
        cases=dataset.cases,
        targets=(target,),
        observations=observations,
        scorecards=scorecards,
    )
    promoted = promote_snapshot(
        snapshot,
        promotion_version="tool-use-promotion-v1",
        approval_date=date(2026, 9, 4),
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
