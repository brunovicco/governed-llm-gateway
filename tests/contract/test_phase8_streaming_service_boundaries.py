import asyncio
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from governed_llm_gateway_contracts import (
    Capability,
    DataClassification,
    GatewayRequest,
    GatewayStreamEvent,
    Message,
    MessageRole,
    Modality,
    PolicyProvenance,
    RiskLevel,
    RoutingProvenance,
    StreamEventType,
    WorkloadRequirements,
)
from governed_llm_gateway_core.application.ranking import (
    RankedCandidate,
    RankingDecision,
    RankingInvariantViolation,
    ScoreBreakdown,
)
from governed_llm_gateway_core.application.resilience import (
    InMemoryHealthTracker,
    StaticProviderResolver,
)
from governed_llm_gateway_core.application.streaming import StreamingExecutionService
from governed_llm_gateway_core.domain.model_registry import ModelDeployment, PricingMetadata

REQUEST_ID = UUID("99999999-9999-4999-8999-999999999999")
TODAY = date(2026, 9, 1)


def _request(*, streaming: bool = True) -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(streaming=streaming),
        messages=(Message(role=MessageRole.USER, content="hello"),),
    )


def _deployment(*, streaming_capability: bool = True) -> ModelDeployment:
    capabilities = {Capability.TEXT}
    if streaming_capability:
        capabilities.add(Capability.STREAMING)
    return ModelDeployment(
        deployment_id="deployment-a",
        provider="provider-a",
        model_id="model/deployment-a",
        model_group="agentic-strong",
        api_family="openai-compatible",
        capabilities=frozenset(capabilities),
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


def _routing(deployment: ModelDeployment) -> RoutingProvenance:
    return RoutingProvenance(
        routing_decision_id="sha256:" + "b" * 64,
        policy=PolicyProvenance(
            decision_id="policy-decision",
            policy_id="gateway-policy",
            policy_version="1.0.0",
            policy_digest="sha256:" + "a" * 64,
        ),
        authorized_model_group="agentic-strong",
        model_registry_digest="c" * 64,
        ranking_policy_version="ranking-v1",
        ranking_policy_digest="d" * 64,
        score_snapshot_id="static-v1",
        provider=deployment.provider,
        model=deployment.model_id,
        deployment=deployment.deployment_id,
    )


def _ranked(deployment: ModelDeployment) -> RankedCandidate:
    score = Decimal("1")
    return RankedCandidate(
        deployment=deployment,
        score=ScoreBreakdown(
            quality=score,
            reliability=Decimal("0"),
            latency=Decimal("0"),
            cost=Decimal("0"),
            availability=Decimal("0"),
            total=score,
        ),
        estimated_cost_usd=Decimal("0.01"),
    )


def _decision(
    deployment: ModelDeployment,
    *,
    selected: bool = True,
) -> RankingDecision:
    return RankingDecision(
        routing=_routing(deployment),
        ranking_policy_digest="d" * 64,
        score_snapshot_id="static-v1",
        selected=_ranked(deployment) if selected else None,
        alternatives=(),
        rejected_candidates=(),
    )


def _service() -> StreamingExecutionService:
    return StreamingExecutionService(
        health=InMemoryHealthTracker(),
        resolver=StaticProviderResolver({}),
    )


async def _collect(
    service: StreamingExecutionService,
    request: GatewayRequest,
    decision: RankingDecision,
    *,
    max_output_tokens: int = 64,
    provider_timeout_seconds: float = 30.0,
) -> list[GatewayStreamEvent]:
    return [
        event
        async for event in service.stream(
            request,
            decision,
            max_output_tokens=max_output_tokens,
            provider_timeout_seconds=provider_timeout_seconds,
        )
    ]


def test_streaming_service_rejects_request_without_streaming_requirement() -> None:
    deployment = _deployment()

    with pytest.raises(ValueError, match="streaming execution requires"):
        asyncio.run(_collect(_service(), _request(streaming=False), _decision(deployment)))


@pytest.mark.parametrize(
    ("max_output_tokens", "provider_timeout_seconds", "message"),
    [
        (0, 30.0, "max_output_tokens must be positive"),
        (64, 0.0, "provider_timeout_seconds must be positive"),
    ],
)
def test_streaming_service_rejects_non_positive_execution_limits(
    max_output_tokens: int,
    provider_timeout_seconds: float,
    message: str,
) -> None:
    deployment = _deployment()

    with pytest.raises(ValueError, match=message):
        asyncio.run(
            _collect(
                _service(),
                _request(),
                _decision(deployment),
                max_output_tokens=max_output_tokens,
                provider_timeout_seconds=provider_timeout_seconds,
            )
        )


def test_streaming_service_returns_failure_when_ranking_has_no_selection() -> None:
    deployment = _deployment()

    events = asyncio.run(
        _collect(
            _service(),
            _request(),
            _decision(deployment, selected=False),
        )
    )

    assert len(events) == 1
    assert events[0].event_type is StreamEventType.RESPONSE_FAILED
    assert events[0].partial is False
    assert events[0].error is not None
    assert events[0].error.code == "no_eligible_streaming_deployment"


def test_streaming_service_fails_closed_when_provider_adapter_is_missing() -> None:
    deployment = _deployment()

    events = asyncio.run(_collect(_service(), _request(), _decision(deployment)))

    assert len(events) == 1
    assert events[0].event_type is StreamEventType.RESPONSE_FAILED
    assert events[0].error is not None
    assert events[0].error.code == "provider_adapter_unavailable"
    assert events[0].routing is not None
    assert events[0].routing.fallback_sequence == ("deployment-a",)


def test_streaming_service_rejects_ranked_candidate_without_streaming_capability() -> None:
    deployment = _deployment(streaming_capability=False)

    with pytest.raises(RankingInvariantViolation, match="streaming capability"):
        asyncio.run(_collect(_service(), _request(), _decision(deployment)))
