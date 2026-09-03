import json
from datetime import date
from decimal import Decimal

import pytest

from benchmarks.contracts import BenchmarkSnapshot, BenchmarkWorkload, Scorecard
from benchmarks.promotion import (
    PromotionMapping,
    canonical_promoted_evidence_json,
    promote_snapshot,
)
from governed_llm_gateway_core.domain.ranking_evidence import (
    RankingEvidenceError,
    build_promoted_ranking_evidence,
)


def _payload() -> dict[str, object]:
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
    evidence = promote_snapshot(
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
    parsed = json.loads(canonical_promoted_evidence_json(evidence))
    assert isinstance(parsed, dict)
    return parsed


def test_runtime_contract_accepts_offline_compiler_artifact() -> None:
    evidence = build_promoted_ranking_evidence(_payload())

    record = evidence.for_runtime("knowledge.rag_ptbr", "deployment-a")
    assert record is not None
    assert record.quality_score == Decimal("0.9")
    assert evidence.benchmark_snapshot_id == "sha256:" + "b" * 64
    assert evidence.for_runtime("knowledge.rag_ptbr", "missing") is None


def test_runtime_contract_rejects_tampered_content() -> None:
    payload = _payload()
    records = payload["records"]
    assert isinstance(records, list)
    record = records[0]
    assert isinstance(record, dict)
    record["quality_score"] = "0.1"

    with pytest.raises(RankingEvidenceError, match="evidence_id does not match"):
        build_promoted_ranking_evidence(payload)


def test_runtime_contract_rejects_unknown_fields() -> None:
    payload = _payload()
    payload["unexpected"] = True

    with pytest.raises(RankingEvidenceError, match="unknown promoted ranking evidence fields"):
        build_promoted_ranking_evidence(payload)


def test_runtime_contract_rejects_invalid_content_identity() -> None:
    payload = _payload()
    payload["benchmark_snapshot_id"] = "sha256:not-hex"

    with pytest.raises(RankingEvidenceError, match="benchmark_snapshot_id"):
        build_promoted_ranking_evidence(payload)


def test_runtime_contract_rejects_duplicate_runtime_identity() -> None:
    payload = _payload()
    records = payload["records"]
    assert isinstance(records, list)
    records.append(dict(records[0]))

    with pytest.raises(RankingEvidenceError, match="duplicate runtime"):
        build_promoted_ranking_evidence(payload)
