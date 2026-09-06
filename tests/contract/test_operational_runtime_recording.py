import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
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
from governed_llm_gateway_core.adapters.operational_samples_memory import (
    InMemoryOperationalSampleStore,
)
from governed_llm_gateway_core.application.operational_evidence import (
    OperationalAttemptSample,
    OperationalEvidenceMaterializationError,
    OperationalProviderErrorKind,
    OperationalSampleOutcome,
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
    ProviderResolutionError,
    ResilienceExecutionError,
    ResilientExecutionService,
    StaticProviderResolver,
)
from governed_llm_gateway_core.application.streaming import StreamingExecutionService
from governed_llm_gateway_core.domain.model_registry import ModelDeployment, PricingMetadata
from governed_llm_gateway_core.domain.resilience import CircuitBreakerPolicy, RetryPolicy

REQUEST_ID = UUID("77777777-7777-4777-8777-777777777777")
TODAY = date(2026, 9, 6)
START = datetime(2026, 9, 6, 21, 0, tzinfo=UTC)


class MonotonicClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class UtcClock:
    def __init__(self, value: datetime = START) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


class SequenceProvider:
    def __init__(
        self,
        clock: MonotonicClock,
        *outcomes: ProviderResponse | BaseException,
    ) -> None:
        self._clock = clock
        self._outcomes = list(outcomes)
        self.calls: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        self._clock.advance(0.125)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class SequenceStreamingProvider:
    feature_support = ProviderFeatureSupport(native_streaming=True, streaming_usage=True)

    def __init__(
        self,
        clock: MonotonicClock,
        *attempts: tuple[ProviderStreamEvent | BaseException, ...],
    ) -> None:
        self._clock = clock
        self._attempts = list(attempts)
        self.calls: list[ProviderRequest] = []
        self.closed_count = 0

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        del request
        raise AssertionError("streaming recorder tests must not call generate")

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        self.calls.append(request)
        self._clock.advance(0.250)
        attempt = self._attempts.pop(0)
        try:
            for item in attempt:
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            self.closed_count += 1


class FailingRecorder:
    def __init__(self) -> None:
        self.invalidated_at: list[datetime] = []

    def record(self, sample: OperationalAttemptSample) -> None:
        del sample
        raise RuntimeError("local recorder failed")

    def invalidate_completeness(self, *, observed_at: datetime) -> None:
        self.invalidated_at.append(observed_at)


def _request(*, streaming: bool = False) -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(streaming=streaming),
        messages=(Message(role=MessageRole.USER, content="hello"),),
    )


def _deployment(deployment_id: str, provider: str, *, streaming: bool = False) -> ModelDeployment:
    capabilities = {Capability.TEXT}
    if streaming:
        capabilities.add(Capability.STREAMING)
    return ModelDeployment(
        deployment_id=deployment_id,
        provider=provider,
        model_id=f"model/{deployment_id}",
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
            _ranked(item, str(Decimal("0.9") - Decimal(index) / Decimal("10")))
            for index, item in enumerate(alternatives)
        ),
        rejected_candidates=(),
    )


def _success(text: str = "ok") -> ProviderResponse:
    return ProviderResponse(text=text)


def _error(
    code: ProviderErrorCode,
    *,
    provider: str = "provider-a",
    retryable: bool = True,
) -> ProviderError:
    return ProviderError(
        provider=provider,
        code=code,
        message=f"{provider} failed with {code.value}",
        retryable=retryable,
    )


def _successful_stream(
    *,
    response_id: str = "response-1",
    completed_response_id: str | None = None,
) -> tuple[ProviderStreamEvent, ...]:
    return (
        ProviderResponseStarted(response_id=response_id),
        ProviderContentDelta(delta="hello"),
        ProviderUsageCompleted(usage=ProviderUsage(input_tokens=10, output_tokens=2)),
        ProviderResponseCompleted(
            response_id=completed_response_id or response_id,
            finish_reason="stop",
        ),
    )


async def _samples(
    store: InMemoryOperationalSampleStore,
    clock: UtcClock,
) -> tuple[OperationalAttemptSample, ...]:
    clock.advance(timedelta(seconds=1))
    return await store.read_window(window_start=START, window_end=clock())


async def _collect_stream(
    service: StreamingExecutionService,
    decision: RankingDecision,
) -> list[GatewayStreamEvent]:
    return [
        event
        async for event in service.stream(
            _request(streaming=True),
            decision,
            max_output_tokens=64,
        )
    ]


def test_store_invalidation_rejects_false_complete_history_and_allows_later_windows() -> None:
    utc = UtcClock()
    store = InMemoryOperationalSampleStore(max_samples=10, clock=utc)
    gap = START + timedelta(seconds=1)
    utc.advance(timedelta(seconds=2))

    store.invalidate_completeness(observed_at=gap)

    assert store.incomplete_through == gap
    with pytest.raises(OperationalEvidenceMaterializationError, match="incomplete runtime history"):
        asyncio.run(store.read_window(window_start=START, window_end=utc()))
    assert (
        asyncio.run(
            store.read_window(
                window_start=gap + timedelta(microseconds=1),
                window_end=utc(),
            )
        )
        == ()
    )


def test_nonstream_retry_records_rate_limit_then_success_with_separate_clocks() -> None:
    monotonic = MonotonicClock()
    utc = UtcClock()
    deployment = _deployment("deployment-a", "provider-a")
    provider = SequenceProvider(
        monotonic,
        _error(ProviderErrorCode.RATE_LIMIT),
        _success(),
    )
    store = InMemoryOperationalSampleStore(max_samples=10, clock=utc)
    service = ResilientExecutionService(
        InMemoryHealthTracker(clock=monotonic),
        StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
        RetryPolicy(
            max_attempts_per_deployment=2,
            max_fallbacks=0,
            base_delay_seconds=0,
            max_delay_seconds=0,
            jitter_ratio=0,
        ),
        clock=monotonic,
        operational_recorder=store,
        utc_clock=utc,
    )

    result = asyncio.run(service.execute(_request(), _decision(deployment), max_output_tokens=64))
    samples = asyncio.run(_samples(store, utc))

    assert result.response.text == "ok"
    assert len(samples) == 2
    assert [item.attempt_number for item in samples] == [1, 2]
    assert [item.fallback_index for item in samples] == [0, 0]
    assert [item.latency_ms for item in samples] == [125, 125]
    assert [item.outcome for item in samples] == [
        OperationalSampleOutcome.PROVIDER_ERROR,
        OperationalSampleOutcome.SUCCEEDED,
    ]
    assert samples[0].error_kind is OperationalProviderErrorKind.RATE_LIMIT
    assert samples[1].error_kind is None
    assert {item.observed_at for item in samples} == {START}
    assert {item.gateway_request_id for item in samples} == {REQUEST_ID}


def test_nonstream_fallback_records_actual_fallback_index() -> None:
    monotonic = MonotonicClock()
    utc = UtcClock()
    primary = _deployment("deployment-a", "provider-a")
    fallback = _deployment("deployment-b", "provider-b")
    primary_provider = SequenceProvider(
        monotonic,
        _error(ProviderErrorCode.UNAVAILABLE, provider="provider-a"),
    )
    fallback_provider = SequenceProvider(monotonic, _success("fallback"))
    store = InMemoryOperationalSampleStore(max_samples=10, clock=utc)
    service = ResilientExecutionService(
        InMemoryHealthTracker(clock=monotonic),
        StaticProviderResolver(
            {
                ("provider-a", "openai-compatible"): primary_provider,
                ("provider-b", "openai-compatible"): fallback_provider,
            }
        ),
        RetryPolicy(max_attempts_per_deployment=1, max_fallbacks=1),
        clock=monotonic,
        operational_recorder=store,
        utc_clock=utc,
    )

    result = asyncio.run(
        service.execute(_request(), _decision(primary, fallback), max_output_tokens=64)
    )
    samples = asyncio.run(_samples(store, utc))

    assert result.deployment.deployment_id == "deployment-b"
    assert [(item.deployment_id, item.fallback_index) for item in samples] == [
        ("deployment-a", 0),
        ("deployment-b", 1),
    ]


def test_timeout_maps_to_bounded_provider_error_kind() -> None:
    monotonic = MonotonicClock()
    utc = UtcClock()
    deployment = _deployment("deployment-a", "provider-a")
    provider = SequenceProvider(
        monotonic,
        _error(ProviderErrorCode.TIMEOUT, retryable=False),
    )
    store = InMemoryOperationalSampleStore(max_samples=10, clock=utc)
    service = ResilientExecutionService(
        InMemoryHealthTracker(clock=monotonic),
        StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
        clock=monotonic,
        operational_recorder=store,
        utc_clock=utc,
    )

    with pytest.raises(ResilienceExecutionError):
        asyncio.run(service.execute(_request(), _decision(deployment), max_output_tokens=64))
    samples = asyncio.run(_samples(store, utc))

    assert len(samples) == 1
    assert samples[0].error_kind is OperationalProviderErrorKind.TIMEOUT


def test_circuit_open_and_resolution_failure_do_not_create_provider_attempt_samples() -> None:
    monotonic = MonotonicClock()
    utc = UtcClock()
    deployment = _deployment("deployment-a", "provider-a")
    provider = SequenceProvider(monotonic, _success())
    store = InMemoryOperationalSampleStore(max_samples=10, clock=utc)
    health = InMemoryHealthTracker(
        CircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=30),
        clock=monotonic,
    )
    health.record_failure(
        deployment.deployment_id,
        _error(ProviderErrorCode.RATE_LIMIT),
        latency_ms=1,
    )
    service = ResilientExecutionService(
        health,
        StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
        clock=monotonic,
        operational_recorder=store,
        utc_clock=utc,
    )
    with pytest.raises(ResilienceExecutionError):
        asyncio.run(service.execute(_request(), _decision(deployment), max_output_tokens=64))
    assert provider.calls == []

    healthy_store = InMemoryOperationalSampleStore(max_samples=10, clock=utc)
    missing = ResilientExecutionService(
        InMemoryHealthTracker(clock=monotonic),
        StaticProviderResolver({}),
        clock=monotonic,
        operational_recorder=healthy_store,
        utc_clock=utc,
    )
    with pytest.raises(ProviderResolutionError):
        asyncio.run(missing.execute(_request(), _decision(deployment), max_output_tokens=64))

    assert asyncio.run(_samples(store, utc)) == ()
    utc.advance(timedelta(seconds=1))
    assert asyncio.run(healthy_store.read_window(window_start=START, window_end=utc())) == ()


def test_nonstream_cancellation_and_unexpected_exception_invalidate_without_fabricated_error() -> (
    None
):
    for raised in (asyncio.CancelledError(), RuntimeError("unexpected adapter failure")):
        monotonic = MonotonicClock()
        utc = UtcClock()
        deployment = _deployment("deployment-a", "provider-a")
        provider = SequenceProvider(monotonic, raised)
        store = InMemoryOperationalSampleStore(max_samples=10, clock=utc)
        service = ResilientExecutionService(
            InMemoryHealthTracker(clock=monotonic),
            StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
            clock=monotonic,
            operational_recorder=store,
            utc_clock=utc,
        )

        with pytest.raises(type(raised)):
            asyncio.run(service.execute(_request(), _decision(deployment), max_output_tokens=64))

        assert store.incomplete_through == START
        utc.advance(timedelta(seconds=1))
        with pytest.raises(
            OperationalEvidenceMaterializationError, match="incomplete runtime history"
        ):
            asyncio.run(store.read_window(window_start=START, window_end=utc()))


def test_recorder_failure_never_changes_successful_execution() -> None:
    monotonic = MonotonicClock()
    utc = UtcClock()
    deployment = _deployment("deployment-a", "provider-a")
    recorder = FailingRecorder()
    service = ResilientExecutionService(
        InMemoryHealthTracker(clock=monotonic),
        StaticProviderResolver(
            {("provider-a", "openai-compatible"): SequenceProvider(monotonic, _success())}
        ),
        clock=monotonic,
        operational_recorder=recorder,
        utc_clock=utc,
    )

    result = asyncio.run(service.execute(_request(), _decision(deployment), max_output_tokens=64))

    assert result.response.text == "ok"
    assert recorder.invalidated_at == [START]


def test_stream_success_records_one_terminal_attempt() -> None:
    monotonic = MonotonicClock()
    utc = UtcClock()
    deployment = _deployment("deployment-a", "provider-a", streaming=True)
    provider = SequenceStreamingProvider(monotonic, _successful_stream())
    store = InMemoryOperationalSampleStore(max_samples=10, clock=utc)
    service = StreamingExecutionService(
        health=InMemoryHealthTracker(clock=monotonic),
        resolver=StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
        clock=monotonic,
        operational_recorder=store,
        utc_clock=utc,
    )

    events = asyncio.run(_collect_stream(service, _decision(deployment)))
    samples = asyncio.run(_samples(store, utc))

    assert events[-1].event_type is StreamEventType.RESPONSE_COMPLETED
    assert len(samples) == 1
    assert samples[0].outcome is OperationalSampleOutcome.SUCCEEDED
    assert samples[0].latency_ms == 250
    assert samples[0].fallback_index == 0


def test_stream_fallback_records_error_then_actual_fallback_success() -> None:
    monotonic = MonotonicClock()
    utc = UtcClock()
    primary = _deployment("deployment-a", "provider-a", streaming=True)
    fallback = _deployment("deployment-b", "provider-b", streaming=True)
    provider_a = SequenceStreamingProvider(
        monotonic,
        (ProviderResponseStarted(response_id="failed"), _error(ProviderErrorCode.RATE_LIMIT)),
    )
    provider_b = SequenceStreamingProvider(monotonic, _successful_stream())
    store = InMemoryOperationalSampleStore(max_samples=10, clock=utc)
    service = StreamingExecutionService(
        health=InMemoryHealthTracker(clock=monotonic),
        resolver=StaticProviderResolver(
            {
                ("provider-a", "openai-compatible"): provider_a,
                ("provider-b", "openai-compatible"): provider_b,
            }
        ),
        retry_policy=RetryPolicy(max_attempts_per_deployment=1, max_fallbacks=1),
        clock=monotonic,
        operational_recorder=store,
        utc_clock=utc,
    )

    events = asyncio.run(_collect_stream(service, _decision(primary, fallback)))
    samples = asyncio.run(_samples(store, utc))

    assert events[-1].event_type is StreamEventType.RESPONSE_COMPLETED
    assert [(item.deployment_id, item.fallback_index) for item in samples] == [
        ("deployment-a", 0),
        ("deployment-b", 1),
    ]
    assert samples[0].error_kind is OperationalProviderErrorKind.RATE_LIMIT
    assert samples[1].outcome is OperationalSampleOutcome.SUCCEEDED


def test_stream_client_close_invalidates_completeness_without_provider_error_sample() -> None:
    monotonic = MonotonicClock()
    utc = UtcClock()
    deployment = _deployment("deployment-a", "provider-a", streaming=True)
    provider = SequenceStreamingProvider(monotonic, _successful_stream())
    store = InMemoryOperationalSampleStore(max_samples=10, clock=utc)
    service = StreamingExecutionService(
        health=InMemoryHealthTracker(clock=monotonic),
        resolver=StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
        clock=monotonic,
        operational_recorder=store,
        utc_clock=utc,
    )

    async def scenario() -> None:
        stream = service.stream(
            _request(streaming=True),
            _decision(deployment),
            max_output_tokens=64,
        )
        first = await anext(stream)
        assert first.event_type is StreamEventType.RESPONSE_STARTED
        await stream.aclose()

    asyncio.run(scenario())

    assert provider.closed_count == 1
    assert store.incomplete_through == START
    utc.advance(timedelta(seconds=1))
    with pytest.raises(OperationalEvidenceMaterializationError, match="incomplete runtime history"):
        asyncio.run(store.read_window(window_start=START, window_end=utc()))


def test_invalid_stream_terminal_records_only_provider_error_not_success() -> None:
    monotonic = MonotonicClock()
    utc = UtcClock()
    deployment = _deployment("deployment-a", "provider-a", streaming=True)
    provider = SequenceStreamingProvider(
        monotonic,
        _successful_stream(response_id="one", completed_response_id="two"),
    )
    store = InMemoryOperationalSampleStore(max_samples=10, clock=utc)
    service = StreamingExecutionService(
        health=InMemoryHealthTracker(clock=monotonic),
        resolver=StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
        clock=monotonic,
        operational_recorder=store,
        utc_clock=utc,
    )

    events = asyncio.run(_collect_stream(service, _decision(deployment)))
    samples = asyncio.run(_samples(store, utc))

    assert events[-1].event_type is StreamEventType.RESPONSE_FAILED
    assert len(samples) == 1
    assert samples[0].outcome is OperationalSampleOutcome.PROVIDER_ERROR
    assert samples[0].error_kind is OperationalProviderErrorKind.OTHER
