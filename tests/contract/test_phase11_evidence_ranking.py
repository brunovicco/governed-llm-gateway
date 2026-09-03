from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from governed_llm_gateway_core.domain.evidence_ranking import (
    EvidenceDrivenRankingPolicy,
    EvidenceRankingError,
    ScoreProvenanceMode,
    benchmark_snapshot_id,
    compile_benchmark_hybrid_policy,
)
from governed_llm_gateway_core.domain.ranking import (
    RankingPolicy,
    RankingWeights,
    StaticDeploymentScore,
    WorkloadRankingPolicy,
)
from governed_llm_gateway_core.domain.ranking_evidence import (
    PromotedRankingEvidence,
    RankingEvidenceRecord,
)

TODAY = date(2026, 9, 3)


def _base_policy() -> RankingPolicy:
    return RankingPolicy(
        schema_version="1.0",
        policy_version="phase5-static-v1",
        score_snapshot_id="phase5-static-v1",
        source_date=TODAY,
        workloads=(
            WorkloadRankingPolicy(
                workload="knowledge.rag_ptbr",
                weights=RankingWeights(
                    quality=Decimal("0.4"),
                    reliability=Decimal("0.2"),
                    latency=Decimal("0.15"),
                    cost=Decimal("0.15"),
                    availability=Decimal("0.1"),
                ),
                deployments=(
                    StaticDeploymentScore(
                        deployment_id="deployment-a",
                        quality=Decimal("0.5"),
                        reliability=Decimal("0.7"),
                        latency=Decimal("0.8"),
                        cost=Decimal("0.6"),
                        availability=Decimal("0.5"),
                        expected_latency_ms=900,
                    ),
                ),
            ),
        ),
    )


def _evidence() -> PromotedRankingEvidence:
    return PromotedRankingEvidence(
        schema_version="1.0",
        promotion_version="phase11-promotion-v1",
        approval_date=TODAY,
        approved_by="architecture-review",
        benchmark_snapshot_id="sha256:" + "b" * 64,
        benchmark_version="gateway-eval-v1",
        dataset_digest="sha256:" + "a" * 64,
        evidence_id="sha256:" + "c" * 64,
        records=(
            RankingEvidenceRecord(
                target_id="target-a",
                deployment_id="deployment-a",
                benchmark_workload="rag_ptbr",
                runtime_workload="knowledge.rag_ptbr",
                total_cases=4,
                completed_calls=4,
                quality_score=Decimal("0.9"),
                availability_rate=Decimal("0.95"),
                latency_p95_ms=500,
                cost_per_completed_call_usd=Decimal("0.03"),
                fallback_frequency=Decimal("0.1"),
            ),
        ),
    )


def test_hybrid_compilation_replaces_only_empirical_dimensions() -> None:
    base = _base_policy()
    compiled = compile_benchmark_hybrid_policy(
        base,
        _evidence(),
        policy_version="phase11-hybrid-v1",
        score_snapshot_id="phase11-hybrid-v1",
        source_date=TODAY,
    )

    score = compiled.for_workload("knowledge.rag_ptbr").score_for("deployment-a")
    assert score is not None
    assert score.quality == Decimal("0.9")
    assert score.availability == Decimal("0.95")
    assert score.reliability == Decimal("0.7")
    assert score.latency == Decimal("0.8")
    assert score.cost == Decimal("0.6")
    assert score.expected_latency_ms == 900
    assert compiled.score_provenance_mode is ScoreProvenanceMode.BENCHMARK_HYBRID
    assert benchmark_snapshot_id(compiled) == "sha256:" + "b" * 64
    assert benchmark_snapshot_id(base) is None


def test_hybrid_policy_digest_covers_benchmark_provenance() -> None:
    first = compile_benchmark_hybrid_policy(
        _base_policy(),
        _evidence(),
        policy_version="phase11-hybrid-v1",
        score_snapshot_id="phase11-hybrid-v1",
        source_date=TODAY,
    )
    changed_evidence = replace(_evidence(), benchmark_snapshot_id="sha256:" + "d" * 64)
    second = compile_benchmark_hybrid_policy(
        _base_policy(),
        changed_evidence,
        policy_version="phase11-hybrid-v1",
        score_snapshot_id="phase11-hybrid-v1",
        source_date=TODAY,
    )

    assert first.digest != second.digest


def test_missing_promoted_evidence_fails_closed() -> None:
    evidence = PromotedRankingEvidence(
        schema_version="1.0",
        promotion_version="phase11-promotion-v1",
        approval_date=TODAY,
        approved_by="architecture-review",
        benchmark_snapshot_id="sha256:" + "b" * 64,
        benchmark_version="gateway-eval-v1",
        dataset_digest="sha256:" + "a" * 64,
        evidence_id="sha256:" + "c" * 64,
        records=(),
    )

    with pytest.raises(EvidenceRankingError, match="missing promoted evidence"):
        compile_benchmark_hybrid_policy(
            _base_policy(),
            evidence,
            policy_version="phase11-hybrid-v1",
            score_snapshot_id="phase11-hybrid-v1",
            source_date=TODAY,
        )


def test_compiler_rejects_empty_base_policy() -> None:
    base = RankingPolicy(
        schema_version="1.0",
        policy_version="phase5-static-v1",
        score_snapshot_id="phase5-static-v1",
        source_date=TODAY,
        workloads=(),
    )

    with pytest.raises(EvidenceRankingError, match="configured workloads"):
        compile_benchmark_hybrid_policy(
            base,
            _evidence(),
            policy_version="phase11-hybrid-v1",
            score_snapshot_id="phase11-hybrid-v1",
            source_date=TODAY,
        )


def test_evidence_driven_policy_rejects_invalid_provenance() -> None:
    with pytest.raises(EvidenceRankingError, match="schema_version"):
        EvidenceDrivenRankingPolicy(
            schema_version="1.0",
            policy_version="phase11-hybrid-v1",
            score_snapshot_id="phase11-hybrid-v1",
            source_date=TODAY,
            workloads=_base_policy().workloads,
            score_provenance_mode=ScoreProvenanceMode.BENCHMARK_HYBRID,
            benchmark_snapshot_id="sha256:" + "b" * 64,
            promotion_evidence_id="sha256:" + "c" * 64,
        )
