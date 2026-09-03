import asyncio
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from uuid import UUID

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
from governed_llm_gateway_core.application.provider import (
    ProviderContentDelta,
    ProviderError,
    ProviderErrorCode,
    ProviderFeatureSupport,
    ProviderRequest,
    ProviderResponse,
    ProviderResponseCompleted,
    ProviderResponseStarted,
    ProviderStreamEvent,
    ProviderUsage,
    ProviderUsageCompleted,
)
from governed_llm_gateway_core.application.ranking import (
    RankedCandidate,
    RankingDecision,
    ScoreBreakdown,
)
from governed_llm_gateway_core.application.resilience import (
    InMemoryHealthTracker,
    StaticProviderResolver,
)
from governed_llm_gateway_core.application.streaming import StreamingExecutionService
from governed_llm_gateway_core.domain.model_registry import ModelDeployment, PricingMetadata
from governed_llm_gateway_core.domain.resilience import RetryPolicy

REQUEST_ID = UUID("88888888-8888-4888-8888-888888888888")
TODAY = date(2026, 9, 1)


class SequenceStreamingProvider:
    feature_support = ProviderFeatureSupport(
        native_streaming=True,
        streaming_usage=True,
    )

    def __init__(self, *attempts: tuple[ProviderStreamEvent | ProviderError, ...]) -> None:
        self.attempts = list(attempts)
        self.calls: list[ProviderRequest] = []
        self.closed_count = 0

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        del request
        raise AssertionError("streaming tests must not call generate")

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        self.calls.append(request)
        attempt = self.attempts.pop(0)
        try:
            for event in attempt:
                if isinstance(event, ProviderError):
                    raise event
                yield event
        finally:
            self.closed_count += 1


def _request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(streaming=True),
        messages=(Message(role=MessageRole.USER, content="hello"),),
    )


def _deployment(deployment_id: str, provider: str) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider=provider,
        model_id=f"model/{deployment_id}",
        model_group="agentic-strong",
        api_family="openai-compatible",
        capabilities=frozenset({Capability.TEXT, Capability.STREAMING}),
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


def _ranked(deployment: ModelDeployment, score: str) -> RankedCandidate:
    value = Decimal(score)
    return RankedCandidate(
        deployment=deployment,
        score=ScoreBreakdown(
            quality=value,
            reliability=Decimal("0"),
            latency=Decimal("0"),
            cost=Decimal("0"),
            availability=Decimal("0"),
            total=value,
        ),
        estimated_cost_usd=Decimal("0.01"),
    )


def _decision(selected: ModelDeployment, *alternatives: ModelDeployment) -> RankingDecision:
    return RankingDecision(
        routing=RoutingProvenance(
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
            provider=selected.provider,
            model=selected.model_id,
            deployment=selected.deployment_id,
        ),
        ranking_policy_digest="d" * 64,
        score_snapshot_id="static-v1",
        selected=_ranked(selected, "1"),
        alternatives=tuple(
            _ranked(deployment, str(Decimal("0.9") - Decimal(index) / Decimal("10")))
            for index, deployment in enumerate(alternatives)
        ),
        rejected_candidates=(),
    )


def _successful_stream(text: str = "hello") -> tuple[ProviderStreamEvent, ...]:
    return (
        ProviderResponseStarted(response_id="response-1"),
        ProviderContentDelta(delta=text),
        ProviderUsageCompleted(usage=ProviderUsage(input_tokens=10, output_tokens=2)),
        ProviderResponseCompleted(response_id="response-1", finish_reason="stop"),
    )


def _rate_limit() -> ProviderError:
    return ProviderError(
        provider="provider-a",
        code=ProviderErrorCode.RATE_LIMIT,
        message="provider-a stream was rate limited",
        retryable=True,
        status_code=429,
    )


async def _collect(
    service: StreamingExecutionService, decision: RankingDecision
) -> list[GatewayStreamEvent]:
    return [
        event
        async for event in service.stream(
            _request(),
            decision,
            max_output_tokens=64,
        )
    ]


def test_successful_stream_has_one_deterministic_terminal_lifecycle() -> None:
    deployment = _deployment("deployment-a", "provider-a")
    provider = SequenceStreamingProvider(_successful_stream())
    health = InMemoryHealthTracker()
    service = StreamingExecutionService(
        health=health,
        resolver=StaticProviderResolver({(deployment.provider, deployment.api_family): provider}),
    )

    events = asyncio.run(_collect(service, _decision(deployment)))

    assert [event.event_type for event in events] == [
        StreamEventType.RESPONSE_STARTED,
        StreamEventType.CONTENT_DELTA,
        StreamEventType.USAGE_COMPLETED,
        StreamEventType.RESPONSE_COMPLETED,
    ]
    assert [event.sequence_number for event in events] == [1, 2, 3, 4]
    assert events[0].routing is not None
    assert events[0].routing.deployment == "deployment-a"
    assert events[2].usage is not None
    assert events[2].usage.input_tokens == 10
    assert provider.closed_count == 1
    assert health.snapshot("deployment-a").success_count == 1


def test_transient_failure_before_output_can_fallback_inside_ranked_sequence() -> None:
    primary = _deployment("deployment-a", "provider-a")
    fallback = _deployment("deployment-b", "provider-b")
    primary_provider = SequenceStreamingProvider(
        (ProviderResponseStarted(response_id="failed"), _rate_limit()),
    )
    fallback_provider = SequenceStreamingProvider(_successful_stream("fallback"))
    health = InMemoryHealthTracker()
    service = StreamingExecutionService(
        health=health,
        resolver=StaticProviderResolver(
            {
                (primary.provider, primary.api_family): primary_provider,
                (fallback.provider, fallback.api_family): fallback_provider,
            }
        ),
        retry_policy=RetryPolicy(max_attempts_per_deployment=1, max_fallbacks=1),
    )

    events = asyncio.run(_collect(service, _decision(primary, fallback)))

    assert events[0].event_type is StreamEventType.RESPONSE_STARTED
    assert events[0].routing is not None
    assert events[0].routing.deployment == "deployment-b"
    assert events[0].routing.fallback_sequence == ("deployment-a", "deployment-b")
    assert [
        event.delta for event in events if event.event_type is StreamEventType.CONTENT_DELTA
    ] == ["fallback"]
    assert len(primary_provider.calls) == 1
    assert len(fallback_provider.calls) == 1


def test_failure_after_content_delta_never_retries_or_falls_back() -> None:
    primary = _deployment("deployment-a", "provider-a")
    fallback = _deployment("deployment-b", "provider-b")
    primary_provider = SequenceStreamingProvider(
        (
            ProviderResponseStarted(response_id="partial"),
            ProviderContentDelta(delta="partial"),
            _rate_limit(),
        ),
    )
    fallback_provider = SequenceStreamingProvider(_successful_stream("must-not-run"))
    service = StreamingExecutionService(
        health=InMemoryHealthTracker(),
        resolver=StaticProviderResolver(
            {
                (primary.provider, primary.api_family): primary_provider,
                (fallback.provider, fallback.api_family): fallback_provider,
            }
        ),
        retry_policy=RetryPolicy(max_attempts_per_deployment=2, max_fallbacks=1),
    )

    events = asyncio.run(_collect(service, _decision(primary, fallback)))

    assert [event.event_type for event in events] == [
        StreamEventType.RESPONSE_STARTED,
        StreamEventType.CONTENT_DELTA,
        StreamEventType.RESPONSE_FAILED,
    ]
    assert events[-1].partial is True
    assert events[-1].error is not None
    assert events[-1].error.retryable is False
    assert len(primary_provider.calls) == 1
    assert fallback_provider.calls == []


def test_client_close_closes_provider_stream_without_recording_provider_failure() -> None:
    deployment = _deployment("deployment-a", "provider-a")
    provider = SequenceStreamingProvider(_successful_stream("partial"))
    health = InMemoryHealthTracker()
    service = StreamingExecutionService(
        health=health,
        resolver=StaticProviderResolver({(deployment.provider, deployment.api_family): provider}),
    )

    async def scenario() -> None:
        stream = service.stream(_request(), _decision(deployment), max_output_tokens=64)
        first = await anext(stream)
        assert first.event_type is StreamEventType.RESPONSE_STARTED
        await stream.aclose()

    asyncio.run(scenario())

    assert provider.closed_count == 1
    snapshot = health.snapshot("deployment-a")
    assert snapshot.request_count == 0
    assert snapshot.transient_failure_count == 0
