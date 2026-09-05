"""Agent-orchestration v1 benchmark contract and end-to-end evidence tests."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import (
    BenchmarkCase,
    BenchmarkTarget,
    BenchmarkWorkload,
    JsonValue,
    ObservationStatus,
    ProviderCall,
)
from benchmarks.promotion import PromotionMapping, promote_snapshot
from benchmarks.runner import BenchmarkProviderFailure, BenchmarkRunner
from benchmarks.scoring import build_default_scorers
from benchmarks.snapshot import build_snapshot, dataset_digest
from benchmarks.workloads.agent_orchestration import (
    assess_agent_orchestration,
    load_agent_orchestration_dataset,
    score_agent_orchestration,
)

_DATASET = Path("benchmarks/datasets/agent-orchestration-v1.json")


class _CanonicalTrajectoryExecutor:
    """Fixture returning reviewed trajectories without executing any step."""

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        return ProviderCall(
            output=case.expected,
            latency_ms=24,
            ttft_ms=9,
            input_units=22,
            output_units=14,
            cost_usd=Decimal("0.002"),
        )


class _MixedTrajectoryExecutor:
    """Fixture separating provider failure from completed trajectory-quality failure."""

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        if case.case_id.endswith("faq_001"):
            raise BenchmarkProviderFailure(code="timeout", status_code=504, latency_ms=260)
        if case.case_id.endswith("order_001"):
            return ProviderCall(
                output={
                    "steps": [
                        {
                            "agent": "router",
                            "action": "classify_request",
                            "handoff_to": "knowledge",
                        },
                        {
                            "agent": "knowledge",
                            "action": "answer_public_knowledge",
                            "handoff_to": None,
                        },
                    ]
                },
                latency_ms=31,
            )
        return ProviderCall(output=case.expected, latency_ms=19)


def test_agent_orchestration_dataset_is_public_synthetic_and_non_executing() -> None:
    dataset = load_agent_orchestration_dataset(_DATASET)

    assert dataset.benchmark_version == "agent-orchestration-v1"
    assert dataset.data_classification == "public"
    assert len(dataset.cases) == 6
    assert len({case.case_id for case in dataset.cases}) == 6
    assert all(case.workload is BenchmarkWorkload.AGENT_ORCHESTRATION for case in dataset.cases)
    assert all(case.metadata["synthetic"] is True for case in dataset.cases)
    assert all(case.metadata["execute_steps"] is False for case in dataset.cases)


def test_agent_orchestration_dataset_digest_is_deterministic() -> None:
    first = load_agent_orchestration_dataset(_DATASET)
    second = load_agent_orchestration_dataset(_DATASET)

    assert dataset_digest(first.cases) == dataset_digest(second.cases)


def test_agent_orchestration_scorer_separates_sequence_and_handoffs() -> None:
    case = load_agent_orchestration_dataset(_DATASET).cases[0]

    exact = assess_agent_orchestration(case, case.expected)
    assert exact.score == Decimal("1")
    assert exact.sequence_score == Decimal("1")
    assert exact.handoff_score == Decimal("1")
    assert exact.trajectory_success is True
    assert exact.issues == ()

    wrong_handoff = assess_agent_orchestration(
        case,
        {
            "steps": [
                {
                    "agent": "router",
                    "action": "classify_request",
                    "handoff_to": "customer_support",
                },
                {
                    "agent": "knowledge",
                    "action": "answer_public_knowledge",
                    "handoff_to": None,
                },
            ]
        },
    )
    assert wrong_handoff.sequence_score == Decimal("1")
    assert wrong_handoff.handoff_score == Decimal("0.5")
    assert wrong_handoff.score == Decimal("0.75")
    issue_pairs = {(issue.code, issue.path) for issue in wrong_handoff.issues}
    assert ("wrong_handoff", "/steps/0/handoff_to") in issue_pairs
    assert ("broken_handoff_chain", "/steps/0/handoff_to") in issue_pairs


def test_agent_orchestration_penalizes_wrong_allowed_trajectory() -> None:
    case = load_agent_orchestration_dataset(_DATASET).cases[0]

    assessment = assess_agent_orchestration(
        case,
        {
            "steps": [
                {
                    "agent": "router",
                    "action": "classify_request",
                    "handoff_to": "customer_support",
                },
                {
                    "agent": "customer_support",
                    "action": "resolve_customer_request",
                    "handoff_to": None,
                },
            ]
        },
    )

    assert assessment.sequence_score == Decimal("0.5")
    assert assessment.handoff_score == Decimal("0.5")
    assert assessment.score == Decimal("0.5")
    assert assessment.trajectory_success is False
    issue_pairs = {(issue.code, issue.path) for issue in assessment.issues}
    assert ("wrong_agent", "/steps/1/agent") in issue_pairs
    assert ("wrong_action", "/steps/1/action") in issue_pairs


def test_agent_orchestration_rejects_undeclared_roles_and_actions() -> None:
    case = load_agent_orchestration_dataset(_DATASET).cases[0]

    undeclared_agent = assess_agent_orchestration(
        case,
        {
            "steps": [
                {
                    "agent": "admin",
                    "action": "classify_request",
                    "handoff_to": None,
                }
            ]
        },
    )
    assert undeclared_agent.score == Decimal("0")
    assert ("undeclared_agent", "/steps/0/agent") in {
        (issue.code, issue.path) for issue in undeclared_agent.issues
    }

    undeclared_action = assess_agent_orchestration(
        case,
        {
            "steps": [
                {
                    "agent": "router",
                    "action": "execute_refund",
                    "handoff_to": None,
                }
            ]
        },
    )
    assert undeclared_action.score == Decimal("0")
    assert ("undeclared_action", "/steps/0/action") in {
        (issue.code, issue.path) for issue in undeclared_action.issues
    }


def test_agent_orchestration_penalizes_missing_and_extra_steps() -> None:
    case = load_agent_orchestration_dataset(_DATASET).cases[0]
    assert isinstance(case.expected, dict)
    expected_steps = case.expected["steps"]
    assert isinstance(expected_steps, list)

    missing = assess_agent_orchestration(
        case,
        {"steps": [expected_steps[0]]},
    )
    assert missing.sequence_score == Decimal("0.5")
    assert missing.handoff_score == Decimal("0.5")
    assert missing.score == Decimal("0.5")
    assert ("missing_step", "/steps/1") in {(issue.code, issue.path) for issue in missing.issues}

    extra_step: JsonValue = {
        "agent": "escalation",
        "action": "prepare_human_handoff",
        "handoff_to": None,
    }
    extra = assess_agent_orchestration(
        case,
        {"steps": [*expected_steps, extra_step]},
    )
    assert extra.sequence_score == Decimal(2) / Decimal(3)
    assert extra.handoff_score == Decimal(2) / Decimal(3)
    assert extra.score == Decimal(2) / Decimal(3)
    assert ("unexpected_step", "/steps/2") in {(issue.code, issue.path) for issue in extra.issues}


def test_agent_orchestration_does_not_permissively_parse_json_text() -> None:
    case = load_agent_orchestration_dataset(_DATASET).cases[0]

    assessment = assess_agent_orchestration(
        case,
        '{"steps":[{"agent":"router","action":"classify_request","handoff_to":"knowledge"}]}',
    )

    assert assessment.score == Decimal("0")
    assert assessment.issues == (assessment.issues[0],)
    assert assessment.issues[0].code == "invalid_output_shape"
    assert score_agent_orchestration(case, case.expected) == Decimal("1")


def test_agent_orchestration_runner_separates_provider_and_quality_failure() -> None:
    dataset = load_agent_orchestration_dataset(_DATASET)
    target = BenchmarkTarget(
        target_id="fixture-agent-orchestration-mixed",
        provider="fixture",
        model="trajectory-model",
        api="fixture-v1",
        configuration="temperature=0;step_execution=false",
        source_date=date(2026, 9, 5),
    )
    runner = BenchmarkRunner(_MixedTrajectoryExecutor(), build_default_scorers())

    observations, scorecards = asyncio.run(runner.run(dataset.cases, (target,)))

    by_case = {item.case_id: item for item in observations}
    faq = by_case["agent_orchestration.faq_001"]
    order = by_case["agent_orchestration.order_001"]
    assert faq.status is ObservationStatus.PROVIDER_FAILURE
    assert faq.quality_score is None
    assert faq.provider_error_code == "timeout"
    assert order.status is ObservationStatus.QUALITY_FAILURE
    assert order.quality_score == Decimal("0.5")
    assert order.provider_error_code is None

    scorecard = scorecards[0]
    assert scorecard.provider_failures == 1
    assert scorecard.completed_calls == 5
    assert scorecard.quality_failures == 1
    assert scorecard.quality_successes == 4


def test_agent_orchestration_pipeline_reaches_snapshot_and_explicit_promotion() -> None:
    dataset = load_agent_orchestration_dataset(_DATASET)
    target = BenchmarkTarget(
        target_id="fixture-agent-orchestration-v1",
        provider="fixture",
        model="trajectory-model",
        api="fixture-v1",
        configuration="temperature=0;step_execution=false",
        source_date=date(2026, 9, 5),
    )
    runner = BenchmarkRunner(_CanonicalTrajectoryExecutor(), build_default_scorers())

    observations, scorecards = asyncio.run(runner.run(dataset.cases, (target,)))

    assert len(observations) == 6
    assert all(item.status is ObservationStatus.SUCCEEDED for item in observations)
    assert all(item.quality_score == Decimal("1") for item in observations)
    scorecard = scorecards[0]
    assert scorecard.workload is BenchmarkWorkload.AGENT_ORCHESTRATION
    assert scorecard.total_cases == 6
    assert scorecard.mean_quality_score == Decimal("1")
    assert scorecard.total_cost_usd == Decimal("0.012")

    snapshot = build_snapshot(
        benchmark_version=dataset.benchmark_version,
        runner_version="agent-orchestration-runner-v1",
        run_date=date(2026, 9, 5),
        cases=dataset.cases,
        targets=(target,),
        observations=observations,
        scorecards=scorecards,
    )
    repeated = build_snapshot(
        benchmark_version=dataset.benchmark_version,
        runner_version="agent-orchestration-runner-v1",
        run_date=date(2026, 9, 5),
        cases=dataset.cases,
        targets=(target,),
        observations=observations,
        scorecards=scorecards,
    )
    assert repeated.snapshot_id == snapshot.snapshot_id

    promoted = promote_snapshot(
        snapshot,
        promotion_version="agent-orchestration-promotion-v1",
        approval_date=date(2026, 9, 5),
        approved_by="benchmark-review",
        mappings=(
            PromotionMapping(
                target_id=target.target_id,
                benchmark_workload=BenchmarkWorkload.AGENT_ORCHESTRATION,
                deployment_id="fixture-deployment",
                runtime_workload="benchmark.agent_orchestration",
            ),
        ),
    )

    assert promoted.benchmark_snapshot_id == snapshot.snapshot_id
    assert promoted.records[0].quality_score == Decimal("1")
