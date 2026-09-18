import asyncio
from collections.abc import AsyncGenerator
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
    ToolCall,
    ToolResult,
    ToolResultBlock,
    ToolUseBlock,
    WorkloadRequirements,
)
from governed_llm_gateway_core.application.execution_deadline import ExecutionDeadlineExceeded
from governed_llm_gateway_core.application.provider import (
    PreparedProviderStream,
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
from governed_llm_gateway_core.domain.resilience import (
    CircuitBreakerPolicy,
    CircuitState,
    RetryPolicy,
)

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

    def prepare_stream(self, request: ProviderRequest) -> PreparedProviderStream:
        return PreparedProviderStream(
            request=request,
            _factory=lambda: self.stream(request),
        )

    async def stream(self, request: ProviderRequest) -> AsyncGenerator[ProviderStreamEvent]:
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


def test_continuous_semantic_output_does_not_renew_the_stream_deadline() -> None:
    async def scenario() -> None:
        now = [100.0]
        deployment = _deployment("deployment-a", "provider-a")

        class TickProvider(SequenceStreamingProvider):
            async def stream(self, request: ProviderRequest) -> AsyncGenerator[ProviderStreamEvent]:
                try:
                    self.calls.append(request)
                    yield ProviderResponseStarted(response_id="tick")
                    for _ in range(10):
                        now[0] += 0.4
                        yield ProviderContentDelta(delta="tick")
                finally:
                    self.closed_count += 1

        provider = TickProvider()
        health = InMemoryHealthTracker()
        service = StreamingExecutionService(
            health=health,
            resolver=StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
            clock=lambda: now[0],
            execution_timeout_ms=1000,
        )
        events = [
            event
            async for event in service.stream(
                service.prepare(_request(), _decision(deployment), max_output_tokens=64)
            )
        ]
        assert [event.delta for event in events if event.delta is not None] == ["tick", "tick"]
        assert events[-1].partial and events[-1].error is not None
        assert events[-1].error.code == ExecutionDeadlineExceeded.code
        assert len(provider.calls) == provider.closed_count == 1
        assert (await health.snapshot(deployment.deployment_id)).request_count == 0

    asyncio.run(scenario())


def test_enabled_budget_allows_pre_output_retry_without_rebuilding_prepared_request() -> None:
    provider = SequenceStreamingProvider((_rate_limit(),), _successful_stream())
    deployment = _deployment("deployment-a", "provider-a")
    service = StreamingExecutionService(
        health=InMemoryHealthTracker(),
        resolver=StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
        retry_policy=RetryPolicy(base_delay_seconds=0, max_delay_seconds=0),
        execution_timeout_ms=10_000,
    )
    events = asyncio.run(_collect(service, _decision(deployment)))
    assert events[-1].event_type is StreamEventType.RESPONSE_COMPLETED
    assert len(provider.calls) == 2 and provider.calls[0] is provider.calls[1]
    assert provider.calls[0].timeout_seconds == 30.0


def test_deadline_failure_before_fallback_output_retains_actual_attempt_routing() -> None:
    async def scenario() -> None:
        selected = _deployment("deployment-a", "provider-a")
        alternative = _deployment("deployment-b", "provider-b")
        first = SequenceStreamingProvider((_rate_limit(),))
        second = BlockingStreamingProvider(content=False)
        service = StreamingExecutionService(
            health=InMemoryHealthTracker(),
            resolver=StaticProviderResolver(
                {
                    ("provider-a", "openai-compatible"): first,
                    ("provider-b", "openai-compatible"): second,
                }
            ),
            retry_policy=RetryPolicy(max_attempts_per_deployment=1),
            execution_timeout_ms=20,
        )
        events = [
            event
            async for event in service.stream(
                service.prepare(_request(), _decision(selected, alternative), max_output_tokens=64)
            )
        ]
        assert len(events) == 1 and events[0].routing is not None
        assert events[0].routing.deployment == alternative.deployment_id
        assert events[0].routing.fallback_sequence == ("deployment-a", "deployment-b")
        assert len(first.calls) == len(second.calls) == 1

    asyncio.run(asyncio.wait_for(scenario(), 2))


@pytest.mark.parametrize("events_read", [0, 1, 2, 3])
def test_total_stream_deadline_includes_preparation_gap_and_consumer_wait(events_read: int) -> None:
    async def scenario() -> None:
        now = [100.0]
        deployment = _deployment("deployment-a", "provider-a")
        provider = SequenceStreamingProvider(_successful_stream())
        health = InMemoryHealthTracker()
        service = StreamingExecutionService(
            health=health,
            resolver=StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
            clock=lambda: now[0],
            execution_timeout_ms=1000,
        )
        plan = service.prepare(_request(), _decision(deployment), max_output_tokens=64)
        stream = service.stream(plan)
        for _ in range(events_read):
            await anext(stream)
        now[0] += 1
        failed = await anext(stream)
        assert failed.event_type is StreamEventType.RESPONSE_FAILED
        assert failed.error is not None and failed.error.code == ExecutionDeadlineExceeded.code
        assert not failed.error.retryable
        assert failed.partial is (events_read >= 2)
        assert failed.sequence_number == events_read + 1
        assert failed.execution is None, "unknown usage/cost must not be fabricated"
        await stream.aclose()
        assert len(provider.calls) == (1 if events_read else 0)
        assert provider.closed_count == len(provider.calls)
        assert (await health.snapshot(deployment.deployment_id)).request_count == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("partial", [False, True])
@pytest.mark.parametrize("half_open", [False, True])
def test_total_stream_deadline_closes_upstream_and_releases_probe_neutrally(
    partial: bool, half_open: bool
) -> None:
    async def scenario() -> None:
        now = [100.0]
        deployment = _deployment("deployment-a", "provider-a")
        alternative = _deployment("deployment-b", "provider-b")
        health = InMemoryHealthTracker(
            CircuitBreakerPolicy(failure_threshold=1), clock=lambda: now[0]
        )
        if half_open:
            await health.record_failure(deployment.deployment_id, _rate_limit(), latency_ms=1)
            now[0] += 30
        before = await health.snapshot(deployment.deployment_id)
        provider = BlockingStreamingProvider(content=partial)
        fallback = SequenceStreamingProvider(_successful_stream("forbidden"))
        service = StreamingExecutionService(
            health=health,
            resolver=StaticProviderResolver(
                {
                    ("provider-a", "openai-compatible"): provider,
                    ("provider-b", "openai-compatible"): fallback,
                }
            ),
            execution_timeout_ms=10,
        )
        events = [
            event
            async for event in service.stream(
                service.prepare(
                    _request(), _decision(deployment, alternative), max_output_tokens=64
                )
            )
        ]
        assert events[-1].partial is partial
        assert (
            events[-1].error is not None and events[-1].error.code == ExecutionDeadlineExceeded.code
        )
        assert not events[-1].error.retryable
        assert len(provider.calls) == provider.closed_count == 1 and fallback.calls == []
        after = await health.snapshot(deployment.deployment_id)
        assert after.request_count == before.request_count
        assert after.success_count == before.success_count
        if half_open:
            assert after.circuit_state is CircuitState.HALF_OPEN
            assert await health.allow_request(deployment.deployment_id) is not None

    asyncio.run(asyncio.wait_for(scenario(), 2))


def test_total_deadline_does_not_cancel_an_external_consumer_task_across_yield() -> None:
    async def scenario() -> None:
        deployment = _deployment("deployment-a", "provider-a")
        provider = BlockingStreamingProvider(content=True)
        service = StreamingExecutionService(
            health=InMemoryHealthTracker(),
            resolver=StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
            execution_timeout_ms=10,
        )
        stream = service.stream(
            service.prepare(_request(), _decision(deployment), max_output_tokens=64)
        )
        await anext(stream)
        await anext(stream)
        await asyncio.sleep(0.02)
        failed = await anext(stream)
        assert failed.partial and failed.error is not None and not failed.error.retryable
        await stream.aclose()
        assert provider.closed_count == 1

    asyncio.run(asyncio.wait_for(scenario(), 2))


def test_total_deadline_covers_stream_backoff_without_retry_or_fallback() -> None:
    async def scenario() -> None:
        now = [100.0]
        selected = _deployment("deployment-a", "provider-a")
        alternative = _deployment("deployment-b", "provider-b")
        provider = SequenceStreamingProvider((_rate_limit(),), _successful_stream("forbidden"))
        fallback = SequenceStreamingProvider(_successful_stream("forbidden"))

        async def sleeper(seconds: float) -> None:
            now[0] += seconds

        service = StreamingExecutionService(
            health=InMemoryHealthTracker(),
            resolver=StaticProviderResolver(
                {
                    ("provider-a", "openai-compatible"): provider,
                    ("provider-b", "openai-compatible"): fallback,
                }
            ),
            retry_policy=RetryPolicy(base_delay_seconds=1, max_delay_seconds=1, jitter_ratio=0),
            clock=lambda: now[0],
            sleeper=sleeper,
            execution_timeout_ms=1000,
        )
        events = [
            event
            async for event in service.stream(
                service.prepare(_request(), _decision(selected, alternative), max_output_tokens=64)
            )
        ]
        assert len(events) == 1 and events[0].error is not None
        assert events[0].error.code == ExecutionDeadlineExceeded.code
        assert len(provider.calls) == 1 and fallback.calls == []

    asyncio.run(scenario())


async def _collect(
    service: StreamingExecutionService, decision: RankingDecision
) -> list[GatewayStreamEvent]:
    plan = service.prepare(_request(), decision, max_output_tokens=64)
    return [event async for event in service.stream(plan)]


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
    assert asyncio.run(health.snapshot("deployment-a")).success_count == 1


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


def test_tool_result_request_never_retries_or_falls_back_before_output() -> None:
    """The application may already have executed a side effect before this continuation."""
    primary = _deployment("deployment-a", "provider-a")
    fallback = _deployment("deployment-b", "provider-b")
    primary_provider = SequenceStreamingProvider(
        (ProviderResponseStarted(response_id="failed"), _rate_limit()),
        _successful_stream("must-not-retry"),
    )
    fallback_provider = SequenceStreamingProvider(_successful_stream("must-not-fallback"))
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
    request = GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(tool_calling=True, streaming=True),
        messages=(
            Message(
                role=MessageRole.ASSISTANT,
                content="",
                blocks=(ToolUseBlock(ToolCall("call-1", "lookup", {})),),
            ),
            Message(
                role=MessageRole.TOOL,
                content="",
                blocks=(ToolResultBlock(ToolResult("call-1", "done")),),
            ),
        ),
    )

    events = asyncio.run(
        _collect_request(service, request=request, decision=_decision(primary, fallback))
    )

    assert events[-1].event_type is StreamEventType.RESPONSE_FAILED
    assert events[-1].error is not None
    assert events[-1].error.retryable is False
    assert len(primary_provider.calls) == 1
    assert fallback_provider.calls == []


async def _collect_request(
    service: StreamingExecutionService,
    *,
    request: GatewayRequest,
    decision: RankingDecision,
) -> list[GatewayStreamEvent]:
    plan = service.prepare(request, decision, max_output_tokens=64)
    return [event async for event in service.stream(plan)]


def test_client_close_closes_provider_stream_without_recording_provider_failure() -> None:
    deployment = _deployment("deployment-a", "provider-a")
    provider = SequenceStreamingProvider(_successful_stream("partial"))
    health = InMemoryHealthTracker()
    service = StreamingExecutionService(
        health=health,
        resolver=StaticProviderResolver({(deployment.provider, deployment.api_family): provider}),
    )

    async def scenario() -> None:
        plan = service.prepare(
            _request(),
            _decision(deployment),
            max_output_tokens=64,
        )
        stream = service.stream(plan)
        first = await anext(stream)
        assert first.event_type is StreamEventType.RESPONSE_STARTED
        await stream.aclose()

    asyncio.run(scenario())

    assert provider.closed_count == 1
    snapshot = asyncio.run(health.snapshot("deployment-a"))
    assert snapshot.request_count == 0
    assert snapshot.transient_failure_count == 0


class BlockingStreamingProvider(SequenceStreamingProvider):
    def __init__(self, *, content: bool = False) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.resume = asyncio.Event()
        self.content = content

    async def stream(self, request: ProviderRequest) -> AsyncGenerator[ProviderStreamEvent]:
        self.calls.append(request)
        self.started.set()
        try:
            yield ProviderResponseStarted(response_id="probe-response")
            if self.content:
                yield ProviderContentDelta(delta="partial")
            await self.resume.wait()
            if not self.content:
                yield ProviderContentDelta(delta="success")
            yield ProviderUsageCompleted(usage=ProviderUsage(input_tokens=1, output_tokens=1))
            yield ProviderResponseCompleted(response_id="probe-response", finish_reason="stop")
        finally:
            self.closed_count += 1


def test_half_open_stream_excludes_concurrent_request_and_cancel_releases_probe() -> None:
    async def scenario() -> None:
        deployment = _deployment("deployment-a", "provider-a")
        now = [100.0]
        health = InMemoryHealthTracker(
            CircuitBreakerPolicy(failure_threshold=1), clock=lambda: now[0]
        )
        await health.record_failure(deployment.deployment_id, _rate_limit(), latency_ms=1)
        now[0] += 30
        provider = BlockingStreamingProvider()
        service = StreamingExecutionService(
            health=health,
            resolver=StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
            retry_policy=RetryPolicy(max_attempts_per_deployment=1, max_fallbacks=0),
        )
        plan = service.prepare(_request(), _decision(deployment), max_output_tokens=64)
        stream = service.stream(plan)
        task = asyncio.create_task(anext(stream))
        await provider.started.wait()
        other = [event async for event in service.stream(plan)]
        assert [event.event_type for event in other] == [StreamEventType.RESPONSE_FAILED]
        assert len(provider.calls) == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await stream.aclose()
        assert provider.closed_count == 1
        snapshot = await health.snapshot(deployment.deployment_id)
        assert snapshot.request_count == 1 and snapshot.circuit_state is CircuitState.HALF_OPEN
        provider.resume.set()
        events = [event async for event in service.stream(plan)]
        assert events[-1].event_type is StreamEventType.RESPONSE_COMPLETED
        assert (
            await health.snapshot(deployment.deployment_id)
        ).circuit_state is CircuitState.CLOSED

    asyncio.run(asyncio.wait_for(scenario(), timeout=2))


def test_closing_half_open_stream_after_start_releases_without_failure() -> None:
    async def scenario() -> None:
        deployment = _deployment("deployment-a", "provider-a")
        now = [100.0]
        health = InMemoryHealthTracker(
            CircuitBreakerPolicy(failure_threshold=1), clock=lambda: now[0]
        )
        await health.record_failure(deployment.deployment_id, _rate_limit(), latency_ms=1)
        now[0] += 30
        provider = BlockingStreamingProvider(content=True)
        service = StreamingExecutionService(
            health=health,
            resolver=StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
        )
        stream = service.stream(
            service.prepare(_request(), _decision(deployment), max_output_tokens=64)
        )
        assert (await anext(stream)).event_type is StreamEventType.RESPONSE_STARTED
        await stream.aclose()
        assert provider.closed_count == 1
        assert (await health.snapshot(deployment.deployment_id)).request_count == 1
        assert await health.allow_request(deployment.deployment_id) is not None

    asyncio.run(scenario())


@pytest.mark.parametrize("partial", [False, True])
def test_probe_timeout_closes_upstream_without_replaying_partial_output(partial: bool) -> None:
    async def scenario() -> None:
        deployment = _deployment("deployment-a", "provider-a")
        health = InMemoryHealthTracker(
            CircuitBreakerPolicy(
                failure_threshold=1, cooldown_seconds=0.001, probe_lease_seconds=0.01
            )
        )
        await health.record_failure(deployment.deployment_id, _rate_limit(), latency_ms=1)
        await asyncio.sleep(0.002)
        provider = BlockingStreamingProvider(content=partial)
        service = StreamingExecutionService(
            health=health,
            resolver=StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
            retry_policy=RetryPolicy(max_attempts_per_deployment=2, max_fallbacks=0),
        )
        events = [
            event
            async for event in service.stream(
                service.prepare(_request(), _decision(deployment), max_output_tokens=64)
            )
        ]
        assert events[-1].event_type is StreamEventType.RESPONSE_FAILED
        assert events[-1].error is not None and events[-1].partial is partial
        assert not any(event.event_type is StreamEventType.RESPONSE_COMPLETED for event in events)
        assert len(provider.calls) == (1 if partial else 2)
        assert provider.closed_count == len(provider.calls)
        assert provider.calls[0].timeout_seconds == 30.0
        assert (await health.snapshot(deployment.deployment_id)).success_count == 0

    asyncio.run(asyncio.wait_for(scenario(), timeout=2))


def test_probe_timeout_does_not_cancel_consumer_while_generator_is_suspended() -> None:
    async def scenario() -> None:
        deployment = _deployment("deployment-a", "provider-a")
        health = InMemoryHealthTracker(
            CircuitBreakerPolicy(
                failure_threshold=1, cooldown_seconds=0.001, probe_lease_seconds=0.01
            )
        )
        await health.record_failure(deployment.deployment_id, _rate_limit(), latency_ms=1)
        await asyncio.sleep(0.002)
        provider = BlockingStreamingProvider(content=True)
        service = StreamingExecutionService(
            health=health,
            resolver=StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
        )
        stream = service.stream(
            service.prepare(_request(), _decision(deployment), max_output_tokens=64)
        )
        assert (await anext(stream)).event_type is StreamEventType.RESPONSE_STARTED
        assert (await anext(stream)).event_type is StreamEventType.CONTENT_DELTA
        # A task-wide asyncio.timeout across yield would cancel this consumer sleep.
        await asyncio.sleep(0.02)
        event = await anext(stream)
        assert event.event_type is StreamEventType.RESPONSE_FAILED
        assert event.error is not None and event.partial
        await stream.aclose()
        assert provider.closed_count == 1 and len(provider.calls) == 1

    asyncio.run(asyncio.wait_for(scenario(), timeout=2))


def test_retired_probe_does_not_publish_buffered_content_after_public_start() -> None:
    async def scenario() -> None:
        deployment = _deployment("deployment-a", "provider-a")
        now = [100.0]
        health = InMemoryHealthTracker(
            CircuitBreakerPolicy(failure_threshold=1), clock=lambda: now[0]
        )
        await health.record_failure(deployment.deployment_id, _rate_limit(), latency_ms=1)
        now[0] += 30
        provider = BlockingStreamingProvider(content=True)
        service = StreamingExecutionService(
            health=health,
            resolver=StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
        )
        stream = service.stream(
            service.prepare(_request(), _decision(deployment), max_output_tokens=64)
        )
        assert (await anext(stream)).event_type is StreamEventType.RESPONSE_STARTED
        now[0] += 60
        replacement = await health.allow_request(deployment.deployment_id)
        assert replacement is not None
        failed = await anext(stream)
        assert failed.event_type is StreamEventType.RESPONSE_FAILED
        assert failed.sequence_number == 2 and failed.partial
        await stream.aclose()
        assert len(provider.calls) == 1 and provider.closed_count == 1
        assert await health.is_admitted(replacement)
        assert (await health.snapshot(deployment.deployment_id)).request_count == 1

    asyncio.run(scenario())


def test_invalid_probe_completion_does_not_prove_health_recovery() -> None:
    async def scenario() -> None:
        deployment = _deployment("deployment-a", "provider-a")
        now = [100.0]
        health = InMemoryHealthTracker(
            CircuitBreakerPolicy(failure_threshold=1), clock=lambda: now[0]
        )
        await health.record_failure(deployment.deployment_id, _rate_limit(), latency_ms=1)
        now[0] += 30
        provider = SequenceStreamingProvider(
            (
                ProviderResponseStarted(response_id="first"),
                ProviderContentDelta(delta="partial"),
                ProviderUsageCompleted(usage=ProviderUsage(input_tokens=1, output_tokens=1)),
                ProviderResponseCompleted(response_id="different", finish_reason="stop"),
            )
        )
        service = StreamingExecutionService(
            health=health,
            resolver=StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
        )
        events = [
            event
            async for event in service.stream(
                service.prepare(_request(), _decision(deployment), max_output_tokens=64)
            )
        ]
        assert events[-1].event_type is StreamEventType.RESPONSE_FAILED and events[-1].partial
        snapshot = await health.snapshot(deployment.deployment_id)
        assert snapshot.success_count == 0 and snapshot.circuit_state is CircuitState.HALF_OPEN
        assert await health.allow_request(deployment.deployment_id) is not None
        assert provider.closed_count == 1 and len(provider.calls) == 1

    asyncio.run(scenario())
