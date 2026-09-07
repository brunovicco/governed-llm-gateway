"""Contract tests for explicitly pinned approved evidence-driven ranking artifacts."""

import json
from datetime import date
from decimal import Decimal

import pytest
from governed_llm_gateway_core.adapters import (
    ApprovedRankingArtifactDocumentError,
    DuplicateApprovedRankingArtifactKeyError,
    dump_approved_ranking_artifact_text,
    load_approved_ranking_artifact_text,
)
from governed_llm_gateway_core.domain.evidence_ranking import (
    EvidenceDrivenRankingPolicy,
    ScoreProvenanceMode,
)
from governed_llm_gateway_core.domain.ranking import (
    RankingWeights,
    StaticDeploymentScore,
    WorkloadRankingPolicy,
)
from governed_llm_gateway_core.domain.ranking_override import ApprovedRankingArtifact

TODAY = date(2026, 9, 7)


def _artifact() -> ApprovedRankingArtifact:
    policy = EvidenceDrivenRankingPolicy(
        schema_version="1.1",
        policy_version="pc11-benchmark-v1",
        score_snapshot_id="pc11-score-v1",
        source_date=TODAY,
        workloads=(
            WorkloadRankingPolicy(
                workload="rag.answer",
                weights=RankingWeights(
                    quality=Decimal("0.4"),
                    reliability=Decimal("0.2"),
                    latency=Decimal("0.15"),
                    cost=Decimal("0.15"),
                    availability=Decimal("0.1"),
                ),
                deployments=(
                    StaticDeploymentScore(
                        deployment_id="openai-primary",
                        quality=Decimal("0.91"),
                        reliability=Decimal("0.8"),
                        latency=Decimal("0.7"),
                        cost=Decimal("0.6"),
                        availability=Decimal("0.99"),
                        expected_latency_ms=850,
                    ),
                ),
            ),
        ),
        score_provenance_mode=ScoreProvenanceMode.BENCHMARK_HYBRID,
        benchmark_snapshot_id="sha256:" + "a" * 64,
        promotion_evidence_id="sha256:" + "b" * 64,
    )
    return ApprovedRankingArtifact(
        policy=policy,
        approval_version="pc11-approval-v1",
        approval_date=TODAY,
        approved_by="ranking-reviewer",
    )


def test_round_trip_preserves_policy_and_approval_identity() -> None:
    artifact = _artifact()

    loaded = load_approved_ranking_artifact_text(
        dump_approved_ranking_artifact_text(artifact),
        expected_artifact_id=artifact.artifact_id,
    )

    assert isinstance(loaded.policy, EvidenceDrivenRankingPolicy)
    assert loaded.policy.digest == artifact.policy.digest
    assert loaded.artifact_id == artifact.artifact_id
    assert loaded == artifact


def test_policy_tampering_with_stale_declared_identity_fails_closed() -> None:
    artifact = _artifact()
    payload = json.loads(dump_approved_ranking_artifact_text(artifact))
    payload["policy"]["workloads"]["rag.answer"]["deployments"]["openai-primary"]["quality"] = "0.1"

    with pytest.raises(
        ApprovedRankingArtifactDocumentError,
        match="declared artifact_id does not match",
    ):
        load_approved_ranking_artifact_text(
            json.dumps(payload),
            expected_artifact_id=artifact.artifact_id,
        )


def test_approval_tampering_with_stale_declared_identity_fails_closed() -> None:
    artifact = _artifact()
    payload = json.loads(dump_approved_ranking_artifact_text(artifact))
    payload["approval"]["approved_by"] = "different-reviewer"

    with pytest.raises(
        ApprovedRankingArtifactDocumentError,
        match="declared artifact_id does not match",
    ):
        load_approved_ranking_artifact_text(
            json.dumps(payload),
            expected_artifact_id=artifact.artifact_id,
        )


def test_expected_artifact_identity_mismatch_fails_closed() -> None:
    artifact = _artifact()

    with pytest.raises(
        ApprovedRankingArtifactDocumentError,
        match="does not match expected_artifact_id",
    ):
        load_approved_ranking_artifact_text(
            dump_approved_ranking_artifact_text(artifact),
            expected_artifact_id="sha256:" + "f" * 64,
        )


def test_duplicate_and_unknown_fields_fail_closed() -> None:
    artifact = _artifact()
    with pytest.raises(DuplicateApprovedRankingArtifactKeyError):
        load_approved_ranking_artifact_text(
            '{"schema_version":"1.0","schema_version":"1.0"}',
            expected_artifact_id=artifact.artifact_id,
        )

    payload = json.loads(dump_approved_ranking_artifact_text(artifact))
    payload["unexpected"] = True
    with pytest.raises(ApprovedRankingArtifactDocumentError, match="unknown approved"):
        load_approved_ranking_artifact_text(
            json.dumps(payload),
            expected_artifact_id=artifact.artifact_id,
        )


def test_malformed_or_non_evidence_policy_fails_closed() -> None:
    artifact = _artifact()
    with pytest.raises(ApprovedRankingArtifactDocumentError, match="not valid JSON"):
        load_approved_ranking_artifact_text(
            "{",
            expected_artifact_id=artifact.artifact_id,
        )

    payload = json.loads(dump_approved_ranking_artifact_text(artifact))
    payload["policy"]["schema_version"] = "1.0"
    with pytest.raises(ApprovedRankingArtifactDocumentError, match="schema_version"):
        load_approved_ranking_artifact_text(
            json.dumps(payload),
            expected_artifact_id=artifact.artifact_id,
        )
