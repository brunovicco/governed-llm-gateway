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
    RequestLimits,
    RiskLevel,
    WorkloadRequirements,
)
from governed_llm_gateway_core.application.policy import (
    AuthorizedCandidateSet,
    PolicyAuthorizationDecision,
    PolicyRequestMetadata,
)
from governed_llm_gateway_core.application.ranking import (
    OperationalRankingService,
    RankingInvariantViolation,
)
from governed_llm_gateway_core.domain.authorization import PolicyAuthorization
from governed_llm_gateway_core.domain.model_registry import (
    ModelDeployment,
    ModelRegistry,
    PricingMetadata,
)
from governed_llm_gateway_core.domain.ranking import (
    RankingPolicy,
    RankingWeights,
    StaticDeploymentScore,
    WorkloadRankingPolicy,
)
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext

REQUEST_ID = UUID("55555555-5555-4555-8555-555555555555")
TODAY = date(2026, 8, 31)


def _deployment(
    *,
    model_group: str = "agentic-strong",
    context_tokens: int = 128_000,
) -> ModelDeployment:
    return ModelDeployment(
        deployment_id="candidate-a",
        provider="provider-a",
        model_id="model/a",
        model_group=model_group,
        api_family="openai-compatible",
        capabilities=frozenset({Capability.TEXT, Capability.TOOL_CALLING}),
        context_tokens=context_tokens,
        modalities=frozenset({Modality.TEXT}),
        pricing=PricingMetadata(
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("2"),
            source_date=TODAY,
            snapshot_version="pricing-v1",
        ),
        max_data_classification=DataClassification.INTERNAL,
        allowed_environments=frozenset({"development"}),
        enabled=True,
        source_date=TODAY,
        catalog_version="catalog-v1",
    )


def _registry(deployment: ModelDeployment) -> ModelRegistry:
    return ModelRegistry(
        schema_version="1.0",
        catalog_version="catalog-v1",
        source_date=TODAY,
        deployments=(deployment,),
    )


def _request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(tool_calling=True),
        limits=RequestLimits(max_latency_ms=5_000, max_cost_usd=Decimal("1")),
    )


def _context() -> EffectivePolicyContext:
    return EffectivePolicyContext(
        client_id="service-a",
        environment="development",
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
    )


def _policy_request() -> PolicyRequestMetadata:
    return PolicyRequestMetadata(
        request_id=REQUEST_ID,
        client_id="service-a",
        environment="development",
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        context_tokens_estimated=1_000,
        max_output_tokens_estimated=500,
        structured_output_required=False,
        max_latency_ms=5_000,
        max_cost_usd=Decimal("1"),
    )


def _ranking_policy() -> RankingPolicy:
    return RankingPolicy(
        schema_version="1.0",
        policy_version="ranking-v1",
        score_snapshot_id="static-v1",
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
                    StaticDeploymentScore(
                        deployment_id="candidate-a",
                        quality=Decimal("0.8"),
                        reliability=Decimal("0.8"),
                        latency=Decimal("0.8"),
                        cost=Decimal("0.8"),
                        availability=Decimal("0.8"),
                        expected_latency_ms=1_000,
                    ),
                ),
            ),
        ),
    )


def _authorized(
    registry: ModelRegistry,
    *,
    groups: frozenset[str] = frozenset({"agentic-strong"}),
) -> AuthorizedCandidateSet:
    decision = PolicyAuthorizationDecision(
        authorization=PolicyAuthorization(
            decision_id="decision-phase5",
            authorized_model_groups=groups,
        ),
        provenance=PolicyProvenance(
            decision_id="decision-phase5",
            policy_id="gateway-policy",
            policy_version="1.0.0",
            policy_digest="sha256:" + "c" * 64,
        ),
        decided_at=datetime(2026, 8, 31, 12, tzinfo=UTC),
        reason="authorized",
        service_version="0.4.0",
        environment="development",
    )
    return AuthorizedCandidateSet(
        policy=decision,
        registry_digest=registry.digest,
        candidates=registry.deployments,
    )


def _rank(registry: ModelRegistry, authorized: AuthorizedCandidateSet) -> None:
    OperationalRankingService().rank(
        _request(),
        _context(),
        registry,
        authorized,
        _policy_request(),
        _ranking_policy(),
    )


def test_registry_change_after_authorization_fails_closed() -> None:
    authorized_registry = _registry(_deployment(context_tokens=128_000))
    changed_registry = _registry(_deployment(context_tokens=256_000))

    with pytest.raises(RankingInvariantViolation, match="registry changed"):
        _rank(changed_registry, _authorized(authorized_registry))


def test_candidate_outside_pdp_authorized_group_fails_closed() -> None:
    registry = _registry(_deployment(model_group="balanced"))

    with pytest.raises(RankingInvariantViolation, match="outside PDP authorization"):
        _rank(registry, _authorized(registry))


def test_multiple_pdp_authorized_groups_are_rejected_as_ambiguous() -> None:
    registry = _registry(_deployment())
    authorized = _authorized(
        registry,
        groups=frozenset({"agentic-strong", "balanced"}),
    )

    with pytest.raises(RankingInvariantViolation, match="exactly one PDP-authorized"):
        _rank(registry, authorized)
