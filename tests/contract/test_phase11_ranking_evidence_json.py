import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.contracts import BenchmarkSnapshot, BenchmarkWorkload, Scorecard
from benchmarks.promotion import (
    canonical_promoted_evidence_json,
    promote_snapshot,
    PromotionMapping,
)
from governed_llm_gateway_core.adapters.ranking_evidence_json import (
    load_promoted_ranking_evidence,
    load_promoted_ranking_evidence_text,
)
from governed_llm_gateway_core.domain.ranking_evidence import RankingEvidenceError


def _evidence_json() -> str:
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
    return canonical_promoted_evidence_json(evidence)


def test_loads_promoted_evidence_from_text_and_file(tmp_path: Path) -> None:
    text = _evidence_json()
    from_text = load_promoted_ranking_evidence_text(text)
    path = tmp_path / "evidence.json"
    path.write_text(text, encoding="utf-8")
    from_file = load_promoted_ranking_evidence(path)

    assert from_text == from_file
    assert from_file.for_runtime("knowledge.rag_ptbr", "deployment-a") is not None


def test_loader_rejects_duplicate_json_keys() -> None:
    with pytest.raises(RankingEvidenceError, match="duplicate promoted ranking evidence key"):
        load_promoted_ranking_evidence_text('{"schema_version":"1.0","schema_version":"1.0"}')


def test_loader_rejects_non_mapping_root() -> None:
    with pytest.raises(RankingEvidenceError, match="root must be a mapping"):
        load_promoted_ranking_evidence_text("[]")


def test_loader_rejects_invalid_json() -> None:
    with pytest.raises(RankingEvidenceError, match="not valid JSON"):
        load_promoted_ranking_evidence_text("{")


def test_loader_rejects_tampered_valid_json() -> None:
    payload = json.loads(_evidence_json())
    payload["approved_by"] = "different-reviewer"

    with pytest.raises(RankingEvidenceError, match="evidence_id does not match"):
        load_promoted_ranking_evidence_text(json.dumps(payload))
