"""Contract tests for benchmark-grounded complexity candidate narrowing."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

import pytest
from governed_llm_gateway_contracts import (
    Capability,
    ComplexityAssessment,
    DataClassification,
    Modality,
    PolicyProvenance,
    TaskComplexity,
)
from governed_llm_gateway_core.application import (
    AuthorizedCandidateSet,
    ComplexityEligibleCandidateSet,
    ComplexityNarrowingError,
    narrow_authorized_candidates_by_complexity,
)
from governed_llm_gateway_core.application.policy import PolicyAuthorizationDecision
from governed_llm_gateway_core.domain import (
    ComplexityQualityPolicy,
    ComplexityQualityPolicyError,
    ModelDeployment,
    PolicyAuthorization,
    RankingPolicy,
    RankingWeights,
    StaticDeploymentScore,
    WorkloadRankingPolicy,
)
from governed_llm_gateway_core.domain.evidence_ranking import (
    EvidenceDrivenRankingPolicy,
    ScoreProvenanceMode,
)

_WORKLOAD = "demo.reasoning"


def _deployment(deployment_id: str) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider="provider-neutral",
        model_id=f"model-{deployment_id}",
        model_group="general",
        api_family="responses",
        capabilities=frozenset({Capability.TEXT}),
        context_tokens=128_000,
        modalities=frozenset({Modality.TEXT}),
        pricing=None,
        max_data_classification=DataClassification.INTERNAL,
        allowed_environments=frozenset({"prod"}),
        enabled=True,
        source_date=date(2026, 9, 7),
        catalog_version="test-v1",
    )


def _authorized(*deployments: ModelDeployment) -> AuthorizedCandidateSet:
    authorization = PolicyAuthorization(
        decision_id="decision-1",
        authorized_model_groups=frozenset({"general"}),
    )
    provenance = PolicyProvenance(
        decision_id="decision-1",
        policy_id="router",
        policy_version="v1",
        policy_digest="sha256:" + "1" * 64,
    )
    decision = PolicyAuthorizationDecision(
        authorization=authorization,
        provenance=provenance,
        decided_at=datetime(2026, 9, 7, tzinfo=UTC),
        reason="allowed",
        service_version="v1",
        environment="prod",
    )
    return AuthorizedCandidateSet(
        policy=decision,
        registry_digest="registry-digest",
        candidates=tuple(deployments),
    )


def _score(deployment_id: str, quality: str) -> StaticDeploymentScore:
    return StaticDeploymentScore(
        deployment_id=deployment_id,
        quality=Decimal(quality),
        reliability=Decimal("1"),
        latency=Decimal("1"),
        cost=Decimal("1"),
        availability=Decimal("1"),
        expected_latency_ms=100,
    )


def _workload_policy(*scores: StaticDeploymentScore) -> WorkloadRankingPolicy:
    return WorkloadRankingPolicy(
        workload=_WORKLOAD,
        weights=RankingWeights(
            quality=Decimal("1"),
            reliability=Decimal("0"),
            latency=Decimal("0"),
            cost=Decimal("0"),
            availability=Decimal("0"),
        ),
        deployments=tuple(scores),
    )


def _evidence_policy(
    *scores: StaticDeploymentScore,
    mode: ScoreProvenanceMode = ScoreProvenanceMode.BENCHMARK_HYBRID,
) -> EvidenceDrivenRankingPolicy:
    manual_override_id = (
        "sha256:" + "c" * 64 if mode is ScoreProvenanceMode.MANUAL_OVERRIDE else None
    )
    return EvidenceDrivenRankingPolicy(
        schema_version="1.1",
        policy_version="ranking-v1",
        score_snapshot_id="snapshot-v1",
        source_date=date(2026, 9, 7),
        workloads=(_workload_policy(*scores),),
        score_provenance_mode=mode,
        benchmark_snapshot_id="sha256:" + "a" * 64,
        promotion_evidence_id="sha256:" + "b" * 64,
        manual_override_id=manual_override_id,
    )


def _quality_policy() -> ComplexityQualityPolicy:
    return ComplexityQualityPolicy(
        policy_id="complexity-quality",
        version="v1",
        low_min_quality=Decimal("0.50"),
        medium_min_quality=Decimal("0.75"),
        high_min_quality=Decimal("0.90"),
    )


def _assessment(level: TaskComplexity) -> ComplexityAssessment:
    return ComplexityAssessment(
        level=level,
        assessment_id="assessment-001",
        evaluator_id="deterministic-complexity",
        evaluator_version="v1",
    )


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (TaskComplexity.LOW, Decimal("0.50")),
        (TaskComplexity.MEDIUM, Decimal("0.75")),
        (TaskComplexity.HIGH, Decimal("0.90")),
    ],
)
def test_quality_policy_exposes_monotonic_floor_by_complexity(
    level: TaskComplexity,
    expected: Decimal,
) -> None:
    policy = _quality_policy()

    assert policy.minimum_for(level) == expected
    assert policy.digest == _quality_policy().digest


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("low_min_quality", Decimal("-0.01")),
        ("medium_min_quality", Decimal("1.01")),
        ("high_min_quality", Decimal("NaN")),
    ],
)
def test_quality_policy_rejects_invalid_floors(field_name: str, value: Decimal) -> None:
    values = {
        "low_min_quality": Decimal("0.50"),
        "medium_min_quality": Decimal("0.75"),
        "high_min_quality": Decimal("0.90"),
    }
    values[field_name] = value

    with pytest.raises(ComplexityQualityPolicyError, match=field_name):
        ComplexityQualityPolicy(
            policy_id="complexity-quality",
            version="v1",
            low_min_quality=values["low_min_quality"],
            medium_min_quality=values["medium_min_quality"],
            high_min_quality=values["high_min_quality"],
        )


def test_quality_policy_rejects_non_decimal_and_non_monotonic_runtime_inputs() -> None:
    with pytest.raises(ComplexityQualityPolicyError, match="low_min_quality"):
        ComplexityQualityPolicy(
            policy_id="complexity-quality",
            version="v1",
            low_min_quality=cast(Decimal, 0.5),
            medium_min_quality=Decimal("0.75"),
            high_min_quality=Decimal("0.90"),
        )

    with pytest.raises(ComplexityQualityPolicyError, match="must be monotonic"):
        ComplexityQualityPolicy(
            policy_id="complexity-quality",
            version="v1",
            low_min_quality=Decimal("0.60"),
            medium_min_quality=Decimal("0.95"),
            high_min_quality=Decimal("0.90"),
        )


def test_complexity_narrowing_is_monotonic_across_quality_floors() -> None:
    small = _deployment("deployment-small")
    large = _deployment("deployment-large")
    authorized = _authorized(large, small)
    ranking = _evidence_policy(
        _score("deployment-large", "0.92"),
        _score("deployment-small", "0.60"),
    )

    low = narrow_authorized_candidates_by_complexity(
        workload=_WORKLOAD,
        authorized=authorized,
        assessment=_assessment(TaskComplexity.LOW),
        ranking_policy=ranking,
        quality_policy=_quality_policy(),
    )
    medium = narrow_authorized_candidates_by_complexity(
        workload=_WORKLOAD,
        authorized=authorized,
        assessment=_assessment(TaskComplexity.MEDIUM),
        ranking_policy=ranking,
        quality_policy=_quality_policy(),
    )
    high = narrow_authorized_candidates_by_complexity(
        workload=_WORKLOAD,
        authorized=authorized,
        assessment=_assessment(TaskComplexity.HIGH),
        ranking_policy=ranking,
        quality_policy=_quality_policy(),
    )

    assert tuple(item.deployment_id for item in low.candidates) == (
        "deployment-large",
        "deployment-small",
    )
    assert tuple(item.deployment_id for item in medium.candidates) == ("deployment-large",)
    assert tuple(item.deployment_id for item in high.candidates) == ("deployment-large",)
    assert high.provenance.minimum_quality == "0.9"
    assert high.provenance.excluded_deployments == ("deployment-small",)


def test_quality_floor_is_inclusive_at_exact_boundary() -> None:
    boundary = _deployment("deployment-boundary")
    result = narrow_authorized_candidates_by_complexity(
        workload=_WORKLOAD,
        authorized=_authorized(boundary),
        assessment=_assessment(TaskComplexity.HIGH),
        ranking_policy=_evidence_policy(_score("deployment-boundary", "0.90")),
        quality_policy=_quality_policy(),
    )

    assert result.candidates == (boundary,)


def test_narrowing_never_resurrects_high_quality_unauthorized_deployment() -> None:
    authorized_only = _deployment("deployment-authorized")
    unauthorized = _deployment("deployment-unauthorized")
    ranking = _evidence_policy(
        _score("deployment-authorized", "0.60"),
        _score("deployment-unauthorized", "1.00"),
    )

    result = narrow_authorized_candidates_by_complexity(
        workload=_WORKLOAD,
        authorized=_authorized(authorized_only),
        assessment=_assessment(TaskComplexity.HIGH),
        ranking_policy=ranking,
        quality_policy=_quality_policy(),
    )

    assert result.candidates == ()
    assert unauthorized.deployment_id not in result.provenance.excluded_deployments
    assert result.provenance.excluded_deployments == (authorized_only.deployment_id,)


def test_narrowing_fails_closed_without_benchmark_hybrid_provenance() -> None:
    deployment = _deployment("deployment-one")
    base_policy = RankingPolicy(
        schema_version="1.0",
        policy_version="ranking-v1",
        score_snapshot_id="snapshot-v1",
        source_date=date(2026, 9, 7),
        workloads=(_workload_policy(_score(deployment.deployment_id, "0.95")),),
    )

    with pytest.raises(ComplexityNarrowingError, match="evidence-driven"):
        narrow_authorized_candidates_by_complexity(
            workload=_WORKLOAD,
            authorized=_authorized(deployment),
            assessment=_assessment(TaskComplexity.HIGH),
            ranking_policy=base_policy,
            quality_policy=_quality_policy(),
        )

    with pytest.raises(ComplexityNarrowingError, match="benchmark_hybrid"):
        narrow_authorized_candidates_by_complexity(
            workload=_WORKLOAD,
            authorized=_authorized(deployment),
            assessment=_assessment(TaskComplexity.HIGH),
            ranking_policy=_evidence_policy(
                _score(deployment.deployment_id, "0.95"),
                mode=ScoreProvenanceMode.MANUAL_OVERRIDE,
            ),
            quality_policy=_quality_policy(),
        )


def test_narrowing_fails_closed_when_authorized_candidate_lacks_quality_evidence() -> None:
    deployment = _deployment("deployment-missing")

    with pytest.raises(ComplexityNarrowingError, match="missing benchmark-derived quality"):
        narrow_authorized_candidates_by_complexity(
            workload=_WORKLOAD,
            authorized=_authorized(deployment),
            assessment=_assessment(TaskComplexity.MEDIUM),
            ranking_policy=_evidence_policy(),
            quality_policy=_quality_policy(),
        )


def test_narrowing_fails_closed_when_workload_has_no_ranking_evidence() -> None:
    deployment = _deployment("deployment-one")

    with pytest.raises(ComplexityNarrowingError, match="has no ranking evidence"):
        narrow_authorized_candidates_by_complexity(
            workload="demo.other",
            authorized=_authorized(deployment),
            assessment=_assessment(TaskComplexity.MEDIUM),
            ranking_policy=_evidence_policy(_score(deployment.deployment_id, "0.95")),
            quality_policy=_quality_policy(),
        )


def test_candidate_set_direct_construction_defends_authorization_subset() -> None:
    authorized = _deployment("deployment-authorized")
    outsider = _deployment("deployment-outsider")
    baseline = narrow_authorized_candidates_by_complexity(
        workload=_WORKLOAD,
        authorized=_authorized(authorized),
        assessment=_assessment(TaskComplexity.LOW),
        ranking_policy=_evidence_policy(_score(authorized.deployment_id, "0.95")),
        quality_policy=_quality_policy(),
    )

    with pytest.raises(ComplexityNarrowingError, match="subset of the authorized"):
        ComplexityEligibleCandidateSet(
            authorized=baseline.authorized,
            candidates=(outsider,),
            provenance=baseline.provenance,
        )


def test_narrowing_provenance_is_deterministic_and_metadata_only() -> None:
    deployment = _deployment("deployment-one")
    kwargs = {
        "workload": _WORKLOAD,
        "authorized": _authorized(deployment),
        "assessment": _assessment(TaskComplexity.MEDIUM),
        "ranking_policy": _evidence_policy(_score(deployment.deployment_id, "0.95")),
        "quality_policy": _quality_policy(),
    }

    first = narrow_authorized_candidates_by_complexity(**kwargs)
    second = narrow_authorized_candidates_by_complexity(**kwargs)

    assert first == second
    assert first.provenance.complexity_assessment_id == "assessment-001"
    assert first.provenance.benchmark_snapshot_id == "sha256:" + "a" * 64
    assert first.provenance.promotion_evidence_id == "sha256:" + "b" * 64
    assert len(first.provenance.quality_policy_digest) == 64
    assert len(first.provenance.ranking_policy_digest) == 64
