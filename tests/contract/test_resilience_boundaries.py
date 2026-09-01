import asyncio
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from governed_llm_gateway_contracts import (
    Capability,
    DataClassification,
    GatewayRequest,
    Message,
    MessageRole,
    Modality,
    PolicyProvenance,
    RiskLevel,
    RoutingProvenance,
)
from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderRequest,
    ProviderResponse,
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
from governed_llm_gateway_core.domain.model_registry import ModelDeployment, PricingMetadata
from governed_llm_gateway_core.domain.resilience import (
    CircuitBreakerPolicy,
    CircuitState,
    RetryPolicy,
)

REQUEST_ID = UUID("22222222-2222-4222-8222-222222222222")
TODAY = date(2026, 8, 31)


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class RecordingSleeper:
    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)
        self.clock.advance(seconds)


class AlwaysFailProvider:
    def __init__(self, error: ProviderError) -> None:
        self.error = error
        self.calls: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        raise self.error


class SuccessProvider:
    def __init__(self, text: str = "ok") -> None:
        self.text = text
        self.calls: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        return ProviderResponse(text=self.text)


def _request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        messages=(Message(role=MessageRole.USER, content="hello"),),
    )


def _deployment(deployment_id: str, provider: str) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider=provider,
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


def _ranked(deployment: ModelDeployment, score: str) -> RankedCandidate:
    total = Decimal(score)
    return RankedCandidate(
        deployment=deployment,
        score=ScoreBreakdown(
            quality=total,
            reliability=Decimal("0"),
            latency=Decimal("0"),
            cost=Decimal("0"),
            availability=Decimal("0"),
            total=total,
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


def _error(code: ProviderErrorCode, *, status: int | None = None) -> ProviderError:
    return ProviderError(
        provider="provider-a",
        code=code,
        message=f"provider-a normalized {code.value} failure",
        retryable=True,
        status_code=status,
    )


def test_timeout_retries_and_updates_timeout_health_counter() -> None:
    deployment = _deployment("candidate-a", "provider-a")
    provider = AlwaysFailProvider(_error(ProviderErrorCode.TIMEOUT, status=408))
    clock = FakeClock()
    sleeper = RecordingSleeper(clock)
    health = InMemoryHealthTracker(clock=clock)
    service = ResilientExecutionService(
        health,
        StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
        RetryPolicy(
            max_attempts_per_deployment=2,
            max_fallbacks=0,
            base_delay_seconds=0.1,
            max_delay_seconds=1,
            jitter_ratio=0,
        ),
        clock=clock,
        sleeper=sleeper,
    )

    with pytest.raises(ResilienceExecutionError):
        asyncio.run(service.execute(_request(), _decision(deployment), max_output_tokens=100))

    assert len(provider.calls) == 2
    assert sleeper.delays == [0.1]
    snapshot = health.snapshot("candidate-a")
    assert snapshot.timeout_count == 2
    assert snapshot.transient_failure_count == 2


def test_transport_failure_can_fallback_to_next_authorized_candidate() -> None:
    first = _deployment("candidate-a", "provider-a")
    second = _deployment("candidate-b", "provider-b")
    provider_a = AlwaysFailProvider(_error(ProviderErrorCode.TRANSPORT))
    provider_b = SuccessProvider("fallback-ok")
    service = ResilientExecutionService(
        InMemoryHealthTracker(),
        StaticProviderResolver(
            {
                ("provider-a", "openai-compatible"): provider_a,
                ("provider-b", "openai-compatible"): provider_b,
            }
        ),
        RetryPolicy(max_attempts_per_deployment=1, max_fallbacks=1),
    )

    result = asyncio.run(
        service.execute(_request(), _decision(first, second), max_output_tokens=100)
    )

    assert result.response.text == "fallback-ok"
    assert result.routing.fallback_sequence == ("candidate-a", "candidate-b")
    assert len(provider_a.calls) == 1
    assert len(provider_b.calls) == 1


def test_retry_attempt_limit_is_exact() -> None:
    deployment = _deployment("candidate-a", "provider-a")
    provider = AlwaysFailProvider(_error(ProviderErrorCode.UNAVAILABLE, status=503))
    service = ResilientExecutionService(
        InMemoryHealthTracker(CircuitBreakerPolicy(failure_threshold=10, cooldown_seconds=30)),
        StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
        RetryPolicy(
            max_attempts_per_deployment=3,
            max_fallbacks=0,
            base_delay_seconds=0,
            max_delay_seconds=0,
            jitter_ratio=0,
        ),
    )

    with pytest.raises(ResilienceExecutionError) as exc_info:
        asyncio.run(service.execute(_request(), _decision(deployment), max_output_tokens=100))

    assert len(provider.calls) == 3
    assert len(exc_info.value.attempts) == 3


def test_fallback_limit_does_not_reach_unbounded_alternatives() -> None:
    first = _deployment("candidate-a", "provider-a")
    second = _deployment("candidate-b", "provider-b")
    third = _deployment("candidate-c", "provider-c")
    provider_a = AlwaysFailProvider(_error(ProviderErrorCode.UNAVAILABLE, status=503))
    provider_b = AlwaysFailProvider(_error(ProviderErrorCode.UNAVAILABLE, status=503))
    provider_c = SuccessProvider("must-not-run")
    service = ResilientExecutionService(
        InMemoryHealthTracker(CircuitBreakerPolicy(failure_threshold=10, cooldown_seconds=30)),
        StaticProviderResolver(
            {
                ("provider-a", "openai-compatible"): provider_a,
                ("provider-b", "openai-compatible"): provider_b,
                ("provider-c", "openai-compatible"): provider_c,
            }
        ),
        RetryPolicy(max_attempts_per_deployment=1, max_fallbacks=1),
    )

    with pytest.raises(ResilienceExecutionError):
        asyncio.run(
            service.execute(_request(), _decision(first, second, third), max_output_tokens=100)
        )

    assert len(provider_a.calls) == 1
    assert len(provider_b.calls) == 1
    assert provider_c.calls == []


def test_missing_provider_adapter_fails_closed_without_fallback() -> None:
    first = _deployment("candidate-a", "provider-a")
    second = _deployment("candidate-b", "provider-b")
    provider_b = SuccessProvider()
    service = ResilientExecutionService(
        InMemoryHealthTracker(),
        StaticProviderResolver({("provider-b", "openai-compatible"): provider_b}),
        RetryPolicy(max_attempts_per_deployment=2, max_fallbacks=1),
    )

    with pytest.raises(ProviderResolutionError):
        asyncio.run(service.execute(_request(), _decision(first, second), max_output_tokens=100))

    assert provider_b.calls == []


def test_transient_half_open_probe_failure_reopens_circuit() -> None:
    clock = FakeClock()
    health = InMemoryHealthTracker(
        CircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=10),
        clock=clock,
    )
    transient = _error(ProviderErrorCode.UNAVAILABLE, status=503)

    health.record_failure("candidate-a", transient, latency_ms=10)
    assert health.snapshot("candidate-a").circuit_state is CircuitState.OPEN

    clock.advance(10)
    assert health.snapshot("candidate-a").circuit_state is CircuitState.HALF_OPEN

    health.record_failure("candidate-a", transient, latency_ms=10)
    assert health.snapshot("candidate-a").circuit_state is CircuitState.OPEN


def test_retry_schedule_is_reconstructable_for_same_request_and_policy() -> None:
    deployment = _deployment("candidate-a", "provider-a")

    def run_once() -> list[float]:
        clock = FakeClock()
        sleeper = RecordingSleeper(clock)
        provider = AlwaysFailProvider(_error(ProviderErrorCode.RATE_LIMIT, status=429))
        service = ResilientExecutionService(
            InMemoryHealthTracker(
                CircuitBreakerPolicy(failure_threshold=10, cooldown_seconds=30),
                clock=clock,
            ),
            StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
            RetryPolicy(
                max_attempts_per_deployment=3,
                max_fallbacks=0,
                base_delay_seconds=0.1,
                max_delay_seconds=1,
                jitter_ratio=0.2,
            ),
            clock=clock,
            sleeper=sleeper,
        )
        with pytest.raises(ResilienceExecutionError):
            asyncio.run(service.execute(_request(), _decision(deployment), max_output_tokens=100))
        return sleeper.delays

    first = run_once()
    second = run_once()
    assert first == second
    assert len(first) == 2
