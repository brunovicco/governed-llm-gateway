"""Contract tests for ranking only the benchmark-grounded complexity subset."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from governed_llm_gateway_contracts import (
    Capability,
    DataClassification,
    GatewayRequest,
    Modality,
    PolicyProvenance,
    RiskLevel,
    TaskComplexity,
)
from governed_llm_gateway_core.application import (
    AuthorizedCandidateSet,
    ComplexityAwareRankingService,
    ComplexityEligibleCandidateSet,
    ComplexityNarrowingProvenance,
    ComplexityRankingError,
    PolicyAuthorizationDecision,
    PolicyRequestMetadata,
)
from governed_llm_gateway_core.domain import (
    ModelDeployment,
    ModelRegistry,
    PolicyAuthorization,
    PricingMetadata,
    RankingWeights,
    StaticDeploymentScore,
    WorkloadRankingPolicy,
)
from governed_llm_gateway_core.domain.evidence_ranking import (
    EvidenceDrivenRankingPolicy,
    ScoreProvenanceMode,
)
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext

_WORKLOAD = "demo.reasoning"
_REQUEST_ID = UUID("00000000-0000-0000-0000-000000000123")


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
        pricing=PricingMetadata(
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("2"),
            source_date=date(2026, 9, 7),
            snapshot_version="pricing-v1",
        ),
        max_data_classification=DataClassification.INTERNAL,
        allowed_environments=frozenset({"prod"}),
        enabled=True,
        source_date=date(2026, 9, 7),
        catalog_version="catalog-v1",
    )


def _registry(*deployments: ModelDeployment) -> ModelRegistry:
    return ModelRegistry(
        schema_version="1.0",
        catalog_version="catalog-v1",
        source_date=date(2026, 9, 7),
        deployments=tuple(sorted(deployments, key=lambda item: item.deployment_id)),
    )


def _authorized(registry: ModelRegistry) -> AuthorizedCandidateSet:
    authorization = PolicyAuthorization(
        decision_id="decision-123",
        authorized_model_groups=frozenset({"general"}),
    )
    provenance = PolicyProvenance(
        decision_id="decision-123",
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
        registry_digest=registry.digest,
        candidates=registry.deployments,
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


def _ranking_policy(
    *scores: StaticDeploymentScore,
    policy_version: str = "ranking-v1",
) -> EvidenceDrivenRankingPolicy:
    workload = WorkloadRankingPolicy(
        workload=_WORKLOAD,
        weights=RankingWeights(
            quality=Decimal("1"),
            reliability=Decimal("0"),
            latency=Decimal("0"),
            cost=Decimal("0"),
            availability=Decimal("0"),
        ),
        deployments=tuple(sorted(scores, key=lambda item: item.deployment_id)),
    )
    return EvidenceDrivenRankingPolicy(
        schema_version="1.1",
        policy_version=policy_version,
        score_snapshot_id="snapshot-v1",
        source_date=date(2026, 9, 7),
        workloads=(workload,),
        score_provenance_mode=ScoreProvenanceMode.BENCHMARK_HYBRID,
        benchmark_snapshot_id="sha256:" + "a" * 64,
        promotion_evidence_id="sha256:" + "b" * 64,
    )


def _eligible(
    *,
    authorized: AuthorizedCandidateSet,
    candidates: tuple[ModelDeployment, ...],
    ranking_policy: EvidenceDrivenRankingPolicy,
) -> ComplexityEligibleCandidateSet:
    return ComplexityEligibleCandidateSet(
        authorized=authorized,
        candidates=tuple(sorted(candidates, key=lambda item: item.deployment_id)),
        provenance=ComplexityNarrowingProvenance(
            complexity_assessment_id="assessment-123",
            complexity_level=TaskComplexity.HIGH,
            minimum_quality="0.9",
            quality_policy_digest="2" * 64,
            ranking_policy_digest=ranking_policy.digest,
            benchmark_snapshot_id=ranking_policy.benchmark_snapshot_id,
            promotion_evidence_id=ranking_policy.promotion_evidence_id,
            excluded_deployments=tuple(
                item.deployment_id
                for item in authorized.candidates
                if item.deployment_id not in {candidate.deployment_id for candidate in candidates}
            ),
        ),
    )


def _request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=_REQUEST_ID,
        workload=_WORKLOAD,
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.INTERNAL,
    )


def _effective_context() -> EffectivePolicyContext:
    return EffectivePolicyContext(
        client_id="client-1",
        environment="prod",
        workload=_WORKLOAD,
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.INTERNAL,
    )


def _policy_request() -> PolicyRequestMetadata:
    return PolicyRequestMetadata(
        request_id=_REQUEST_ID,
        client_id="client-1",
        environment="prod",
        workload=_WORKLOAD,
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.INTERNAL,
        context_tokens_estimated=1_000,
        max_output_tokens_estimated=500,
        structured_output_required=False,
        max_latency_ms=5_000,
        max_cost_usd=Decimal("1"),
    )


def test_ranking_uses_only_complexity_eligible_candidates() -> None:
    excluded = _deployment("deployment-excluded")
    eligible_low = _deployment("deployment-eligible-low")
    eligible_high = _deployment("deployment-eligible-high")
    registry = _registry(excluded, eligible_low, eligible_high)
    authorized = _authorized(registry)
    ranking_policy = _ranking_policy(
        _score(excluded.deployment_id, "1.00"),
        _score(eligible_low.deployment_id, "0.91"),
        _score(eligible_high.deployment_id, "0.95"),
    )
    eligible = _eligible(
        authorized=authorized,
        candidates=(eligible_low, eligible_high),
        ranking_policy=ranking_policy,
    )

    result = ComplexityAwareRankingService().rank(
        _request(),
        _effective_context(),
        registry,
        eligible,
        _policy_request(),
        ranking_policy,
    )

    assert result.ranking.selected is not None
    assert result.ranking.selected.deployment.deployment_id == eligible_high.deployment_id
    assert tuple(item.deployment.deployment_id for item in result.ranking.alternatives) == (
        eligible_low.deployment_id,
    )
    assert excluded.deployment_id not in {
        result.ranking.selected.deployment.deployment_id,
        *(item.deployment.deployment_id for item in result.ranking.alternatives),
    }


def test_empty_complexity_subset_fails_closed_without_broader_fallback() -> None:
    authorized_deployment = _deployment("deployment-authorized")
    registry = _registry(authorized_deployment)
    authorized = _authorized(registry)
    ranking_policy = _ranking_policy(_score(authorized_deployment.deployment_id, "1.00"))
    eligible = _eligible(
        authorized=authorized,
        candidates=(),
        ranking_policy=ranking_policy,
    )

    with pytest.raises(ComplexityRankingError, match="at least one complexity-eligible"):
        ComplexityAwareRankingService().rank(
            _request(),
            _effective_context(),
            registry,
            eligible,
            _policy_request(),
            ranking_policy,
        )


def test_ranking_policy_must_match_narrowing_provenance() -> None:
    deployment = _deployment("deployment-one")
    registry = _registry(deployment)
    authorized = _authorized(registry)
    narrowing_policy = _ranking_policy(_score(deployment.deployment_id, "0.95"))
    changed_policy = _ranking_policy(
        _score(deployment.deployment_id, "0.95"),
        policy_version="ranking-v2",
    )
    eligible = _eligible(
        authorized=authorized,
        candidates=(deployment,),
        ranking_policy=narrowing_policy,
    )

    with pytest.raises(ComplexityRankingError, match="does not match complexity-narrowing"):
        ComplexityAwareRankingService().rank(
            _request(),
            _effective_context(),
            registry,
            eligible,
            _policy_request(),
            changed_policy,
        )


def test_ranking_preserves_pdp_registry_and_complexity_lineage() -> None:
    deployment = _deployment("deployment-one")
    registry = _registry(deployment)
    authorized = _authorized(registry)
    ranking_policy = _ranking_policy(_score(deployment.deployment_id, "0.95"))
    eligible = _eligible(
        authorized=authorized,
        candidates=(deployment,),
        ranking_policy=ranking_policy,
    )

    result = ComplexityAwareRankingService().rank(
        _request(),
        _effective_context(),
        registry,
        eligible,
        _policy_request(),
        ranking_policy,
    )

    assert result.narrowing == eligible.provenance
    assert result.ranking.routing.policy == authorized.policy.provenance
    assert result.ranking.routing.model_registry_digest == authorized.registry_digest
    assert result.ranking.ranking_policy_digest == eligible.provenance.ranking_policy_digest


def test_phase5_rejections_remain_confined_to_complexity_subset() -> None:
    excluded = _deployment("deployment-excluded")
    eligible = _deployment("deployment-eligible")
    disabled_eligible = ModelDeployment(
        deployment_id=eligible.deployment_id,
        provider=eligible.provider,
        model_id=eligible.model_id,
        model_group=eligible.model_group,
        api_family=eligible.api_family,
        capabilities=eligible.capabilities,
        context_tokens=eligible.context_tokens,
        modalities=eligible.modalities,
        pricing=eligible.pricing,
        max_data_classification=eligible.max_data_classification,
        allowed_environments=eligible.allowed_environments,
        enabled=False,
        source_date=eligible.source_date,
        catalog_version=eligible.catalog_version,
    )
    registry = _registry(excluded, disabled_eligible)
    authorized = _authorized(registry)
    ranking_policy = _ranking_policy(
        _score(excluded.deployment_id, "1.00"),
        _score(disabled_eligible.deployment_id, "0.95"),
    )
    complexity_subset = _eligible(
        authorized=authorized,
        candidates=(disabled_eligible,),
        ranking_policy=ranking_policy,
    )

    result = ComplexityAwareRankingService().rank(
        _request(),
        _effective_context(),
        registry,
        complexity_subset,
        _policy_request(),
        ranking_policy,
    )

    assert result.ranking.selected is None
    assert result.ranking.alternatives == ()
    assert tuple(item.deployment for item in result.ranking.rejected_candidates) == (
        disabled_eligible.deployment_id,
    )
    assert excluded.deployment_id not in {
        item.deployment for item in result.ranking.rejected_candidates
    }
