from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.contracts import BenchmarkSnapshot, BenchmarkWorkload, Scorecard
from benchmarks.promotion import PromotedBenchmarkEvidence, PromotionMapping, promote_snapshot
from benchmarks.promotion_store import persist_promoted_evidence


def _evidence() -> PromotedBenchmarkEvidence:
    scorecard = Scorecard(
        target_id="target-a",
        workload=BenchmarkWorkload.RAG_PTBR,
        total_cases=2,
        completed_calls=2,
        provider_failures=0,
        quality_successes=2,
        quality_failures=0,
        availability_rate=Decimal("1"),
        quality_success_rate=Decimal("1"),
        mean_quality_score=Decimal("0.9"),
        latency_p50_ms=100,
        latency_p95_ms=120,
        ttft_p50_ms=20,
        ttft_p95_ms=25,
        total_input_units=100,
        total_output_units=50,
        total_cost_usd=Decimal("0.02"),
        rate_limit_errors=0,
        fallback_frequency=Decimal("0"),
        provider_error_counts={},
    )
    snapshot = BenchmarkSnapshot(
        schema_version="1.0",
        benchmark_version="gateway-eval-v1",
        runner_version="runner-v1",
        run_date=date(2026, 9, 3),
        dataset_digest="sha256:" + "a" * 64,
        snapshot_id="sha256:" + "b" * 64,
        targets=(),
        observations=(),
        scorecards=(scorecard,),
    )
    return promote_snapshot(
        snapshot,
        promotion_version="phase11-promotion-v1",
        approval_date=date(2026, 9, 3),
        approved_by="architecture-review",
        mappings=(
            PromotionMapping(
                target_id="target-a",
                benchmark_workload=BenchmarkWorkload.RAG_PTBR,
                deployment_id="deployment-a",
                runtime_workload="knowledge.rag_ptbr",
            ),
        ),
    )


def test_persist_promoted_evidence_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    evidence = _evidence()
    first = persist_promoted_evidence(tmp_path, evidence)
    second = persist_promoted_evidence(tmp_path, evidence)

    assert first == second
    assert first.parent.name == "phase11-promotion-v1"
    assert first.name == f"{evidence.evidence_id.removeprefix('sha256:')}.json"
    assert evidence.benchmark_snapshot_id in first.read_text(encoding="utf-8")


def test_persist_promoted_evidence_rejects_content_collision(tmp_path: Path) -> None:
    evidence = _evidence()
    path = persist_promoted_evidence(tmp_path, evidence)
    path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="collision"):
        persist_promoted_evidence(tmp_path, evidence)
