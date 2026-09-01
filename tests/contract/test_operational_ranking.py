from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from governed_llm_gateway_contracts import (
    CandidateRejection,
    Capability,
    DataClassification,
    GatewayRequest,
    Modality,
    PolicyProvenance,
    RejectionReason,
    RequestLimits,
    RiskLevel,
    WorkloadRequirements,
)
from governed_llm_gateway_core.application.policy import (
    AuthorizedCandidateSet,
    PolicyAuthorizationDecision,
    PolicyRequestMetadata,
)
from governed_llm_gateway_core.application.ranking import OperationalRankingService
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

REQUEST_ID = UUID("11111111-1111-4111-8111-111111111111")
TODAY = date(2026, 8, 31)


def _deployment(
    deployment_id: str,
    *,
    enabled: bool = True,
    capabilities: frozenset[Capability] | None = None,
    context_tokens: int = 200_000,
    pricing: PricingMetadata | None = None,
    environment: str = "development",
    classification: DataClassification = DataClassification.INTERNAL,
) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider="provider-a",
        model_id=f"model/{deployment_id}",
        model_group="agentic-strong",
        api_family="openai-compatible",
        capabilities=capabilities
        or frozenset(
            {
                Capability.TEXT,
                Capability.TOOL_CALLING,
                Capability.STRUCTURED_OUTPUT,
            }
        ),
        context_tokens=context_tokens,
        modalities=frozenset({Modality.TEXT}),
        pricing=pricing
        if pricing is not None
        else PricingMetadata(
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("2"),
            source_date=TODAY,
            snapshot_version="pricing-v1",
        ),
        max_data_classification=classification,
        allowed_environments=frozenset({environment}),
        enabled=enabled,
        source_date=TODAY,
        catalog_version="catalog-v1",
    )


def _registry(*deployments: ModelDeployment) -> ModelRegistry:
    return ModelRegistry(
        schema_version="1.0",
        catalog_version="catalog-v1",
        source_date=TODAY,
        deployments=tuple(sorted(deployments, key=lambda item: item.deployment_id)),
    )


def _policy(*scores: StaticDeploymentScore) -> RankingPolicy:
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
                deployments=tuple(sorted(scores, key=lambda item: item.deployment_id)),
            ),
        ),
    )


def _score(deployment_id: str, value: str, *, latency_ms: int = 1000) -> StaticDeploymentScore:
    score = Decimal(value)
    return StaticDeploymentScore(
        deployment_id=deployment_id,
        quality=score,
        reliability=score,
        latency=score,
        cost=score,
        availability=score,
        expected_latency_ms=latency_ms,
    )


def _request(
    *,
    tool_calling: bool = True,
    structured_output: bool = False,
    vision: bool = False,
    min_context_tokens: int = 0,
    max_cost_usd: Decimal = Decimal("1"),
    max_latency_ms: int = 10_000,
) -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(
            tool_calling=tool_calling,
            structured_output=structured_output,
            vision=vision,
            min_context_tokens=min_context_tokens,
        ),
        limits=RequestLimits(
            max_latency_ms=max_latency_ms,
            max_cost_usd=max_cost_usd,
        ),
    )


def _context() -> EffectivePolicyContext:
    return EffectivePolicyContext(
        client_id="service-a",
        environment="development",
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
    )


def _policy_request(
    *,
    max_latency_ms: int = 10_000,
    max_cost_usd: Decimal = Decimal("1"),
) -> PolicyRequestMetadata:
    return PolicyRequestMetadata(
        request_id=REQUEST_ID,
        client_id="service-a",
        environment="development",
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        context_tokens_estimated=2_000,
        max_output_tokens_estimated=1_000,
        structured_output_required=False,
        max_latency_ms=max_latency_ms,
        max_cost_usd=max_cost_usd,
    )


def _authorized(registry: ModelRegistry) -> AuthorizedCandidateSet:
    authorization = PolicyAuthorization(
        decision_id="decision-1",
        authorized_model_groups=frozenset({"agentic-strong"}),
    )
    decision = PolicyAuthorizationDecision(
        authorization=authorization,
        provenance=PolicyProvenance(
            decision_id="decision-1",
            policy_id="gateway-policy",
            policy_version="1.0.0",
            policy_digest="sha256:" + "a" * 64,
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


def test_same_inputs_produce_same_ranking() -> None:
    registry = _registry(_deployment("candidate-b"), _deployment("candidate-a"))
    policy = _policy(_score("candidate-a", "0.8"), _score("candidate-b", "0.9"))
    service = OperationalRankingService()

    first = service.rank(
        _request(), _context(), registry, _authorized(registry), _policy_request(), policy
    )
    second = service.rank(
        _request(), _context(), registry, _authorized(registry), _policy_request(), policy
    )

    assert first == second
    assert first.selected is not None
    assert first.selected.deployment.deployment_id == "candidate-b"
    assert first.routing.routing_decision_id.startswith("sha256:")


def test_ineligible_highest_score_can_never_win() -> None:
    registry = _registry(
        _deployment("disabled-best", enabled=False),
        _deployment("eligible"),
    )
    policy = _policy(_score("disabled-best", "1"), _score("eligible", "0.6"))

    decision = OperationalRankingService().rank(
        _request(),
        _context(),
        registry,
        _authorized(registry),
        _policy_request(),
        policy,
    )

    assert decision.selected is not None
    assert decision.selected.deployment.deployment_id == "eligible"
    assert (
        CandidateRejection(
            deployment="disabled-best",
            reason=RejectionReason.DEPLOYMENT_DISABLED,
        )
        in decision.rejected_candidates
    )


def test_ties_resolve_by_deployment_identifier() -> None:
    registry = _registry(_deployment("candidate-b"), _deployment("candidate-a"))
    policy = _policy(_score("candidate-b", "0.8"), _score("candidate-a", "0.8"))

    decision = OperationalRankingService().rank(
        _request(),
        _context(),
        registry,
        _authorized(registry),
        _policy_request(),
        policy,
    )

    assert decision.selected is not None
    assert decision.selected.deployment.deployment_id == "candidate-a"
    assert [item.deployment.deployment_id for item in decision.alternatives] == ["candidate-b"]


@pytest.mark.parametrize(
    ("deployment", "gateway_request", "reason"),
    [
        (
            _deployment("missing-tool", capabilities=frozenset({Capability.TEXT})),
            _request(tool_calling=True),
            RejectionReason.MISSING_CAPABILITY,
        ),
        (
            _deployment("small-context", context_tokens=1_500),
            _request(tool_calling=False, min_context_tokens=2_000),
            RejectionReason.CONTEXT_TOO_SMALL,
        ),
        (
            _deployment("wrong-env", environment="production"),
            _request(),
            RejectionReason.PROVIDER_NOT_AUTHORIZED,
        ),
    ],
)
def test_static_eligibility_filters_reject_before_scoring(
    deployment: ModelDeployment,
    gateway_request: GatewayRequest,
    reason: RejectionReason,
) -> None:
    registry = _registry(deployment)
    policy = _policy(_score(deployment.deployment_id, "1"))

    decision = OperationalRankingService().rank(
        gateway_request,
        _context(),
        registry,
        _authorized(registry),
        _policy_request(),
        policy,
    )

    assert decision.selected is None
    assert decision.rejected_candidates[0].reason is reason


def test_unknown_pricing_fails_closed_under_cost_ceiling() -> None:
    deployment = _deployment("unknown-price")
    deployment = ModelDeployment(
        deployment_id=deployment.deployment_id,
        provider=deployment.provider,
        model_id=deployment.model_id,
        model_group=deployment.model_group,
        api_family=deployment.api_family,
        capabilities=deployment.capabilities,
        context_tokens=deployment.context_tokens,
        modalities=deployment.modalities,
        pricing=None,
        max_data_classification=deployment.max_data_classification,
        allowed_environments=deployment.allowed_environments,
        enabled=deployment.enabled,
        source_date=deployment.source_date,
        catalog_version=deployment.catalog_version,
    )
    registry = _registry(deployment)

    decision = OperationalRankingService().rank(
        _request(),
        _context(),
        registry,
        _authorized(registry),
        _policy_request(),
        _policy(_score("unknown-price", "1")),
    )

    assert decision.selected is None
    assert decision.rejected_candidates[0].reason is RejectionReason.PRICING_UNAVAILABLE


def test_latency_ceiling_uses_versioned_static_expectation() -> None:
    deployment = _deployment("slow")
    registry = _registry(deployment)

    decision = OperationalRankingService().rank(
        _request(),
        _context(),
        registry,
        _authorized(registry),
        _policy_request(max_latency_ms=500),
        _policy(_score("slow", "1", latency_ms=600)),
    )

    assert decision.selected is None
    assert decision.rejected_candidates[0].reason is RejectionReason.LATENCY_LIMIT_EXCEEDED
