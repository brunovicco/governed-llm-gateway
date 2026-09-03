from datetime import date
from decimal import Decimal

import pytest

from benchmarks.contracts import BenchmarkSnapshot, BenchmarkWorkload, Scorecard
from benchmarks.promotion import (
    PromotionError,
    PromotionMapping,
    canonical_promoted_evidence_json,
    promote_snapshot,
)


def _scorecard(
    *,
    target_id: str = "target-a",
    workload: BenchmarkWorkload = BenchmarkWorkload.RAG_PTBR,
    total_cases: int = 4,
    completed_calls: int = 3,
    mean_quality_score: Decimal | None = Decimal("0.8"),
    availability_rate: Decimal = Decimal("0.75"),
    latency_p95_ms: int | None = 450,
    total_cost_usd: Decimal = Decimal("0.12"),
    fallback_frequency: Decimal = Decimal("0.25"),
) -> Scorecard:
    return Scorecard(
        target_id=target_id,
        workload=workload,
        total_cases=total_cases,
        completed_calls=completed_calls,
        provider_failures=total_cases - completed_calls,
        quality_successes=2 if completed_calls else 0,
        quality_failures=1 if completed_calls else 0,
        availability_rate=availability_rate,
        quality_success_rate=Decimal("0.666666") if completed_calls else None,
        mean_quality_score=mean_quality_score,
        latency_p50_ms=300 if completed_calls else None,
        latency_p95_ms=latency_p95_ms,
        ttft_p50_ms=100 if completed_calls else None,
        ttft_p95_ms=150 if completed_calls else None,
        total_input_units=300 if completed_calls else 0,
        total_output_units=120 if completed_calls else 0,
        total_cost_usd=total_cost_usd,
        rate_limit_errors=total_cases - completed_calls,
        fallback_frequency=fallback_frequency,
        provider_error_counts={"rate_limit": total_cases - completed_calls}
        if total_cases > completed_calls
        else {},
    )


def _snapshot(*scorecards: Scorecard) -> BenchmarkSnapshot:
    return BenchmarkSnapshot(
        schema_version="1.0",
        benchmark_version="gateway-eval-v1",
        runner_version="runner-v1",
        run_date=date(2026, 9, 3),
        dataset_digest="sha256:" + "a" * 64,
        snapshot_id="sha256:" + "b" * 64,
        targets=(),
        observations=(),
        scorecards=scorecards,
    )


def _mapping(
    *,
    target_id: str = "target-a",
    workload: BenchmarkWorkload = BenchmarkWorkload.RAG_PTBR,
    deployment_id: str = "deployment-a",
    runtime_workload: str = "knowledge.rag_ptbr",
) -> PromotionMapping:
    return PromotionMapping(
        target_id=target_id,
        benchmark_workload=workload,
        deployment_id=deployment_id,
        runtime_workload=runtime_workload,
    )


def test_promotes_explicit_mapped_evidence_without_inventing_scores() -> None:
    evidence = promote_snapshot(
        _snapshot(_scorecard()),
        promotion_version="phase11-promotion-v1",
        approval_date=date(2026, 9, 3),
        approved_by="architecture-review",
        mappings=(_mapping(),),
    )

    record = evidence.records[0]
    assert evidence.benchmark_snapshot_id == "sha256:" + "b" * 64
    assert record.deployment_id == "deployment-a"
    assert record.runtime_workload == "knowledge.rag_ptbr"
    assert record.quality_score == Decimal("0.8")
    assert record.availability_rate == Decimal("0.75")
    assert record.latency_p95_ms == 450
    assert record.cost_per_completed_call_usd == Decimal("0.04")
    assert record.fallback_frequency == Decimal("0.25")


def test_promotion_is_deterministic_and_mapping_order_independent() -> None:
    second_card = _scorecard(
        target_id="target-b",
        workload=BenchmarkWorkload.CODE_GENERATION,
        mean_quality_score=Decimal("0.9"),
    )
    second_mapping = _mapping(
        target_id="target-b",
        workload=BenchmarkWorkload.CODE_GENERATION,
        deployment_id="deployment-b",
        runtime_workload="engineering.code_generation",
    )
    snapshot = _snapshot(_scorecard(), second_card)

    first = promote_snapshot(
        snapshot,
        promotion_version="phase11-promotion-v1",
        approval_date=date(2026, 9, 3),
        approved_by="architecture-review",
        mappings=(_mapping(), second_mapping),
    )
    second = promote_snapshot(
        snapshot,
        promotion_version="phase11-promotion-v1",
        approval_date=date(2026, 9, 3),
        approved_by="architecture-review",
        mappings=(second_mapping, _mapping()),
    )

    assert first.evidence_id == second.evidence_id
    assert canonical_promoted_evidence_json(first) == canonical_promoted_evidence_json(second)


def test_provider_only_failure_cannot_be_promoted_as_zero_quality() -> None:
    failed = _scorecard(
        total_cases=4,
        completed_calls=0,
        mean_quality_score=None,
        availability_rate=Decimal("0"),
        latency_p95_ms=None,
        total_cost_usd=Decimal("0"),
        fallback_frequency=Decimal("0"),
    )

    with pytest.raises(PromotionError, match="at least one completed call"):
        promote_snapshot(
            _snapshot(failed),
            promotion_version="phase11-promotion-v1",
            approval_date=date(2026, 9, 3),
            approved_by="architecture-review",
            mappings=(_mapping(),),
        )


def test_missing_scorecard_mapping_fails_closed() -> None:
    with pytest.raises(PromotionError, match="has no scorecard"):
        promote_snapshot(
            _snapshot(_scorecard()),
            promotion_version="phase11-promotion-v1",
            approval_date=date(2026, 9, 3),
            approved_by="architecture-review",
            mappings=(_mapping(target_id="unknown-target"),),
        )


def test_duplicate_runtime_mapping_fails_closed() -> None:
    second_card = _scorecard(target_id="target-b")
    with pytest.raises(PromotionError, match="duplicate runtime"):
        promote_snapshot(
            _snapshot(_scorecard(), second_card),
            promotion_version="phase11-promotion-v1",
            approval_date=date(2026, 9, 3),
            approved_by="architecture-review",
            mappings=(
                _mapping(),
                _mapping(target_id="target-b"),
            ),
        )


def test_duplicate_source_mapping_fails_closed() -> None:
    with pytest.raises(PromotionError, match="duplicate benchmark"):
        promote_snapshot(
            _snapshot(_scorecard()),
            promotion_version="phase11-promotion-v1",
            approval_date=date(2026, 9, 3),
            approved_by="architecture-review",
            mappings=(
                _mapping(),
                _mapping(deployment_id="deployment-b"),
            ),
        )


def test_requires_explicit_normalized_approval_and_mapping() -> None:
    snapshot = _snapshot(_scorecard())
    with pytest.raises(PromotionError, match="at least one explicit"):
        promote_snapshot(
            snapshot,
            promotion_version="phase11-promotion-v1",
            approval_date=date(2026, 9, 3),
            approved_by="architecture-review",
            mappings=(),
        )
    with pytest.raises(PromotionError, match="approved_by"):
        promote_snapshot(
            snapshot,
            promotion_version="phase11-promotion-v1",
            approval_date=date(2026, 9, 3),
            approved_by=" architecture-review",
            mappings=(_mapping(),),
        )
    with pytest.raises(PromotionError, match="dotted"):
        _mapping(runtime_workload="rag_ptbr")


def test_rejects_non_content_addressed_snapshot_identity() -> None:
    snapshot = BenchmarkSnapshot(
        schema_version="1.0",
        benchmark_version="gateway-eval-v1",
        runner_version="runner-v1",
        run_date=date(2026, 9, 3),
        dataset_digest="sha256:" + "a" * 64,
        snapshot_id="not-a-digest",
        targets=(),
        observations=(),
        scorecards=(_scorecard(),),
    )
    with pytest.raises(PromotionError, match="snapshot_id"):
        promote_snapshot(
            snapshot,
            promotion_version="phase11-promotion-v1",
            approval_date=date(2026, 9, 3),
            approved_by="architecture-review",
            mappings=(_mapping(),),
        )
