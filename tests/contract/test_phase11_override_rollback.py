from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from governed_llm_gateway_core.domain.evidence_ranking import (
    EvidenceDrivenRankingPolicy,
    EvidenceRankingError,
    ScoreProvenanceMode,
)
from governed_llm_gateway_core.domain.ranking import (
    RankingWeights,
    StaticDeploymentScore,
    WorkloadRankingPolicy,
)
from governed_llm_gateway_core.domain.ranking_override import (
    ApprovedRankingArtifact,
    ManualOverrideBundle,
    ManualScoreOverride,
    RankingOverrideError,
    apply_manual_override,
    select_rollback_policy,
)

TODAY = date(2026, 9, 3)


def _score(deployment_id: str, *, quality: str, availability: str) -> StaticDeploymentScore:
    return StaticDeploymentScore(
        deployment_id=deployment_id,
        quality=Decimal(quality),
        reliability=Decimal("0.8"),
        latency=Decimal("0.7"),
        cost=Decimal("0.6"),
        availability=Decimal(availability),
        expected_latency_ms=700,
    )


def _policy() -> EvidenceDrivenRankingPolicy:
    return EvidenceDrivenRankingPolicy(
        schema_version="1.1",
        policy_version="benchmark-v1",
        score_snapshot_id="benchmark-score-v1",
        source_date=TODAY,
        workloads=(
            WorkloadRankingPolicy(
                workload="agent.orchestration",
                weights=RankingWeights(
                    quality=Decimal("0.4"),
                    reliability=Decimal("0.2"),
                    latency=Decimal("0.15"),
                    cost=Decimal("0.15"),
                    availability=Decimal("0.1"),
                ),
                deployments=(
                    _score("candidate-a", quality="0.8", availability="0.9"),
                    _score("candidate-b", quality="0.7", availability="0.85"),
                ),
            ),
        ),
        score_provenance_mode=ScoreProvenanceMode.BENCHMARK_HYBRID,
        benchmark_snapshot_id="sha256:" + "a" * 64,
        promotion_evidence_id="sha256:" + "b" * 64,
    )


def _bundle(*overrides: ManualScoreOverride, reason: str = "incident mitigation") -> ManualOverrideBundle:
    return ManualOverrideBundle(
        schema_version="1.0",
        override_version="override-v1",
        approval_date=TODAY,
        approved_by="platform-oncall",
        reason=reason,
        overrides=overrides,
    )


def test_manual_override_bundle_identity_is_order_independent() -> None:
    first = ManualScoreOverride(
        workload="agent.orchestration",
        deployment_id="candidate-a",
        quality=Decimal("0.5"),
    )
    second = ManualScoreOverride(
        workload="agent.orchestration",
        deployment_id="candidate-b",
        availability=Decimal("0.6"),
    )

    assert _bundle(first, second).override_id == _bundle(second, first).override_id


def test_manual_override_bundle_identity_covers_operator_reason() -> None:
    override = ManualScoreOverride(
        workload="agent.orchestration",
        deployment_id="candidate-a",
        quality=Decimal("0.5"),
    )

    assert _bundle(override, reason="incident one").override_id != _bundle(
        override, reason="incident two"
    ).override_id


def test_manual_override_replaces_only_promoted_empirical_dimensions() -> None:
    baseline = _policy()
    override = ManualScoreOverride(
        workload="agent.orchestration",
        deployment_id="candidate-a",
        quality=Decimal("0.2"),
        availability=Decimal("0.3"),
    )
    bundle = _bundle(override)

    effective = apply_manual_override(
        baseline,
        bundle,
        policy_version="benchmark-v1-override-v1",
        score_snapshot_id="override-score-v1",
        source_date=TODAY,
    )

    score = effective.for_workload("agent.orchestration").score_for("candidate-a")
    assert score is not None
    assert score.quality == Decimal("0.2")
    assert score.availability == Decimal("0.3")
    assert score.reliability == Decimal("0.8")
    assert score.latency == Decimal("0.7")
    assert score.cost == Decimal("0.6")
    assert score.expected_latency_ms == 700
    assert effective.score_provenance_mode is ScoreProvenanceMode.MANUAL_OVERRIDE
    assert effective.manual_override_id == bundle.override_id
    assert effective.benchmark_snapshot_id == baseline.benchmark_snapshot_id
    assert effective.promotion_evidence_id == baseline.promotion_evidence_id


def test_manual_override_policy_digest_covers_override_identity() -> None:
    baseline = _policy()
    override = ManualScoreOverride(
        workload="agent.orchestration",
        deployment_id="candidate-a",
        quality=Decimal("0.5"),
    )
    first = apply_manual_override(
        baseline,
        _bundle(override, reason="reason one"),
        policy_version="override-v1",
        score_snapshot_id="override-score-v1",
        source_date=TODAY,
    )
    second = apply_manual_override(
        baseline,
        _bundle(override, reason="reason two"),
        policy_version="override-v1",
        score_snapshot_id="override-score-v1",
        source_date=TODAY,
    )

    assert first.for_workload("agent.orchestration") == second.for_workload(
        "agent.orchestration"
    )
    assert first.digest != second.digest


def test_manual_override_unknown_target_fails_closed() -> None:
    bundle = _bundle(
        ManualScoreOverride(
            workload="agent.orchestration",
            deployment_id="not-configured",
            quality=Decimal("0.5"),
        )
    )

    with pytest.raises(RankingOverrideError, match="target does not exist"):
        apply_manual_override(
            _policy(),
            bundle,
            policy_version="override-v1",
            score_snapshot_id="override-score-v1",
            source_date=TODAY,
        )


def test_manual_override_cannot_stack_over_an_active_override() -> None:
    bundle = _bundle(
        ManualScoreOverride(
            workload="agent.orchestration",
            deployment_id="candidate-a",
            quality=Decimal("0.5"),
        )
    )
    active = apply_manual_override(
        _policy(),
        bundle,
        policy_version="override-v1",
        score_snapshot_id="override-score-v1",
        source_date=TODAY,
    )

    with pytest.raises(RankingOverrideError, match="benchmark-hybrid baseline"):
        apply_manual_override(
            active,
            bundle,
            policy_version="override-v2",
            score_snapshot_id="override-score-v2",
            source_date=TODAY,
        )


def test_manual_override_validation_rejects_unsafe_shapes() -> None:
    with pytest.raises(RankingOverrideError, match="at least one score"):
        ManualScoreOverride(
            workload="agent.orchestration",
            deployment_id="candidate-a",
        )
    with pytest.raises(RankingOverrideError, match="between 0 and 1"):
        ManualScoreOverride(
            workload="agent.orchestration",
            deployment_id="candidate-a",
            quality=Decimal("1.1"),
        )
    duplicate = ManualScoreOverride(
        workload="agent.orchestration",
        deployment_id="candidate-a",
        quality=Decimal("0.5"),
    )
    with pytest.raises(RankingOverrideError, match="duplicate targets"):
        _bundle(duplicate, duplicate)


def test_evidence_policy_requires_override_identity_only_in_manual_mode() -> None:
    with pytest.raises(EvidenceRankingError, match="requires manual_override_id"):
        replace(
            _policy(),
            score_provenance_mode=ScoreProvenanceMode.MANUAL_OVERRIDE,
        )
    with pytest.raises(EvidenceRankingError, match="only valid"):
        replace(_policy(), manual_override_id="sha256:" + "c" * 64)


def test_rollback_selects_exact_previous_approved_policy() -> None:
    baseline = _policy()
    active = apply_manual_override(
        baseline,
        _bundle(
            ManualScoreOverride(
                workload="agent.orchestration",
                deployment_id="candidate-a",
                quality=Decimal("0.4"),
            )
        ),
        policy_version="override-v1",
        score_snapshot_id="override-score-v1",
        source_date=TODAY,
    )
    baseline_artifact = ApprovedRankingArtifact(
        policy=baseline,
        approval_version="approval-baseline-v1",
        approval_date=TODAY,
        approved_by="ranking-reviewer",
    )
    active_artifact = ApprovedRankingArtifact(
        policy=active,
        approval_version="approval-override-v1",
        approval_date=TODAY,
        approved_by="ranking-reviewer",
    )

    rolled_back = select_rollback_policy(
        (baseline_artifact, active_artifact),
        target_artifact_id=baseline_artifact.artifact_id,
    )

    assert rolled_back is baseline
    assert rolled_back.digest == baseline.digest
    assert rolled_back.benchmark_snapshot_id == baseline.benchmark_snapshot_id
    assert rolled_back.manual_override_id is None


def test_rollback_unknown_or_ambiguous_artifact_fails_closed() -> None:
    artifact = ApprovedRankingArtifact(
        policy=_policy(),
        approval_version="approval-v1",
        approval_date=TODAY,
        approved_by="ranking-reviewer",
    )

    with pytest.raises(RankingOverrideError, match="exactly one approved artifact"):
        select_rollback_policy(
            (artifact,),
            target_artifact_id="sha256:" + "f" * 64,
        )
    with pytest.raises(RankingOverrideError, match="exactly one approved artifact"):
        select_rollback_policy(
            (artifact, artifact),
            target_artifact_id=artifact.artifact_id,
        )
