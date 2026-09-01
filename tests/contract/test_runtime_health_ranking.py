from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from governed_llm_gateway_contracts import (
    Capability,
    DataClassification,
    GatewayRequest,
    Modality,
    PolicyProvenance,
    RejectionReason,
    RiskLevel,
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
from governed_llm_gateway_core.domain.resilience import (
    CircuitState,
    DeploymentHealthSnapshot,
    HealthStatus,
)
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext

REQUEST_ID = UUID("11111111-1111-4111-8111-111111111111")
TODAY = date(2026, 8, 31)


def _deployment(deployment_id: str) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider="provider-a",
        model_id=f"model/{deployment_id}",
        model_group="agentic-strong",
        api_family="openai-compatible",
        capabilities=frozenset({Capability.TEXT}),
        context_tokens=128_000,
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


def _registry(*deployments: ModelDeployment) -> ModelRegistry:
    return ModelRegistry(
        schema_version="1.0",
        catalog_version="catalog-v1",
        source_date=TODAY,
        deployments=deployments,
    )


def _request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
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


def _ranking_policy(*deployment_ids: str) -> RankingPolicy:
    return RankingPolicy(
        schema_version="1.0",
        policy_version="ranking-v1",
        score_snapshot_id="static-v1",
        source_date=TODAY,
        workloads=(
            WorkloadRankingPolicy(
                workload="agent.orchestration",
                weights=RankingWeights(
                    quality=Decimal("1"),
                    reliability=Decimal("0"),
                    latency=Decimal("0"),
                    cost=Decimal("0"),
                    availability=Decimal("0"),
                ),
                deployments=tuple(
                    StaticDeploymentScore(
                        deployment_id=deployment_id,
                        quality=Decimal("1"),
                        reliability=Decimal("1"),
                        latency=Decimal("1"),
                        cost=Decimal("1"),
                        availability=Decimal("1"),
                        expected_latency_ms=100,
                    )
                    for deployment_id in deployment_ids
                ),
            ),
        ),
    )


def _authorized(registry: ModelRegistry) -> AuthorizedCandidateSet:
    decision = PolicyAuthorizationDecision(
        authorization=PolicyAuthorization(
            decision_id="decision-1",
            authorized_model_groups=frozenset({"agentic-strong"}),
        ),
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


def test_open_circuit_removes_deployment_from_eligibility() -> None:
    open_candidate = _deployment("candidate-a")
    healthy_candidate = _deployment("candidate-b")
    registry = _registry(open_candidate, healthy_candidate)
    health = {
        "candidate-a": DeploymentHealthSnapshot(
            deployment_id="candidate-a",
            status=HealthStatus.UNHEALTHY,
            circuit_state=CircuitState.OPEN,
        ),
        "candidate-b": DeploymentHealthSnapshot(
            deployment_id="candidate-b",
            status=HealthStatus.HEALTHY,
            circuit_state=CircuitState.CLOSED,
        ),
    }

    decision = OperationalRankingService().rank(
        _request(),
        _context(),
        registry,
        _authorized(registry),
        _policy_request(),
        _ranking_policy("candidate-a", "candidate-b"),
        health,
    )

    assert decision.selected is not None
    assert decision.selected.deployment.deployment_id == "candidate-b"
    rejected = {item.deployment: item for item in decision.rejected_candidates}
    assert rejected["candidate-a"].reason is RejectionReason.CIRCUIT_BREAKER_OPEN


def test_missing_runtime_health_fails_closed_when_health_filter_is_active() -> None:
    deployment = _deployment("candidate-a")
    registry = _registry(deployment)

    decision = OperationalRankingService().rank(
        _request(),
        _context(),
        registry,
        _authorized(registry),
        _policy_request(),
        _ranking_policy("candidate-a"),
        {},
    )

    assert decision.selected is None
    assert decision.rejected_candidates[0].reason is RejectionReason.DEPLOYMENT_UNHEALTHY
    assert decision.rejected_candidates[0].detail == "runtime_health_unavailable"
