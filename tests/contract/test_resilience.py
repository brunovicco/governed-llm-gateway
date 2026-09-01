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
    RankingInvariantViolation,
    ScoreBreakdown,
)
from governed_llm_gateway_core.application.resilience import (
    ExecutionAttemptOutcome,
    InMemoryHealthTracker,
    ResilienceExecutionError,
    ResilientExecutionService,
    StaticProviderResolver,
)
from governed_llm_gateway_core.domain.model_registry import ModelDeployment, PricingMetadata
from governed_llm_gateway_core.domain.resilience import (
    CircuitBreakerPolicy,
    CircuitState,
    FallbackSafetyState,
    HealthStatus,
    RetryPolicy,
)

REQUEST_ID = UUID("11111111-1111-4111-8111-111111111111")
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


class SequenceProvider:
    def __init__(self, *outcomes: ProviderResponse | ProviderError) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, ProviderError):
            raise outcome
        return outcome


def _request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        messages=(Message(role=MessageRole.USER, content="hello"),),
    )


def _deployment(
    deployment_id: str,
    *,
    provider: str,
    model_group: str = "agentic-strong",
) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider=provider,
        model_id=f"model/{deployment_id}",
        model_group=model_group,
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


def _decision(
    selected: ModelDeployment,
    *alternatives: ModelDeployment,
) -> RankingDecision:
    selected_ranked = _ranked(selected, "1")
    ranked_alternatives = tuple(
        _ranked(deployment, str(Decimal("0.9") - Decimal(index) / Decimal("10")))
        for index, deployment in enumerate(alternatives)
    )
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
        selected=selected_ranked,
        alternatives=ranked_alternatives,
        rejected_candidates=(),
    )


def _rate_limit() -> ProviderError:
    return ProviderError(
        provider="provider-a",
        code=ProviderErrorCode.RATE_LIMIT,
        message="provider-a request failed with HTTP 429",
        retryable=True,
        status_code=429,
        retry_after_seconds=0.2,
    )


def _server_error(provider: str = "provider-a") -> ProviderError:
    return ProviderError(
        provider=provider,
        code=ProviderErrorCode.UNAVAILABLE,
        message=f"{provider} request failed with HTTP 503",
        retryable=True,
        status_code=503,
    )


def _success(text: str = "ok") -> ProviderResponse:
    return ProviderResponse(text=text)


def test_429_retries_same_deployment_before_fallback() -> None:
    deployment = _deployment("candidate-a", provider="provider-a")
    provider = SequenceProvider(_rate_limit(), _success())
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
            max_delay_seconds=1.0,
            jitter_ratio=0,
        ),
        clock=clock,
        sleeper=sleeper,
    )

    result = asyncio.run(service.execute(_request(), _decision(deployment), max_output_tokens=100))

    assert len(provider.calls) == 2
    assert {call.model for call in provider.calls} == {deployment.model_id}
    assert sleeper.delays == [0.2]
    assert result.routing.fallback_sequence == ("candidate-a",)
    assert [attempt.outcome for attempt in result.attempts] == [
        ExecutionAttemptOutcome.TRANSIENT_FAILURE,
        ExecutionAttemptOutcome.SUCCEEDED,
    ]
    snapshot = health.snapshot("candidate-a")
    assert snapshot.request_count == 2
    assert snapshot.success_count == 1
    assert snapshot.rate_limit_count == 1
    assert snapshot.circuit_state is CircuitState.CLOSED


def test_5xx_falls_back_to_next_authorized_ranked_deployment() -> None:
    first = _deployment("candidate-a", provider="provider-a")
    second = _deployment("candidate-b", provider="provider-b")
    provider_a = SequenceProvider(_server_error())
    provider_b = SequenceProvider(_success("fallback-ok"))
    clock = FakeClock()
    service = ResilientExecutionService(
        InMemoryHealthTracker(clock=clock),
        StaticProviderResolver(
            {
                ("provider-a", "openai-compatible"): provider_a,
                ("provider-b", "openai-compatible"): provider_b,
            }
        ),
        RetryPolicy(max_attempts_per_deployment=1, max_fallbacks=1),
        clock=clock,
    )

    result = asyncio.run(
        service.execute(_request(), _decision(first, second), max_output_tokens=100)
    )

    assert len(provider_a.calls) == 1
    assert len(provider_b.calls) == 1
    assert result.deployment.deployment_id == "candidate-b"
    assert result.routing.fallback_sequence == ("candidate-a", "candidate-b")
    assert result.response.text == "fallback-ok"


def test_permanent_error_does_not_retry_or_fallback() -> None:
    first = _deployment("candidate-a", provider="provider-a")
    second = _deployment("candidate-b", provider="provider-b")
    permanent = ProviderError(
        provider="provider-a",
        code=ProviderErrorCode.INVALID_REQUEST,
        message="provider-a request failed with HTTP 400",
        retryable=False,
        status_code=400,
    )
    provider_a = SequenceProvider(permanent)
    provider_b = SequenceProvider(_success())
    service = ResilientExecutionService(
        InMemoryHealthTracker(),
        StaticProviderResolver(
            {
                ("provider-a", "openai-compatible"): provider_a,
                ("provider-b", "openai-compatible"): provider_b,
            }
        ),
        RetryPolicy(max_attempts_per_deployment=3, max_fallbacks=1),
    )

    with pytest.raises(ResilienceExecutionError) as exc_info:
        asyncio.run(service.execute(_request(), _decision(first, second), max_output_tokens=100))

    assert exc_info.value.last_error_code is ProviderErrorCode.INVALID_REQUEST
    assert len(provider_a.calls) == 1
    assert provider_b.calls == []
    assert len(exc_info.value.attempts) == 1
    assert exc_info.value.attempts[0].outcome is ExecutionAttemptOutcome.PERMANENT_FAILURE


@pytest.mark.parametrize(
    "safety",
    [
        FallbackSafetyState(provider_output_observed=True),
        FallbackSafetyState(external_side_effect_executed=True),
        FallbackSafetyState(opaque_reasoning_state_established=True),
    ],
)
def test_side_effect_or_continuation_state_blocks_automatic_replay(
    safety: FallbackSafetyState,
) -> None:
    deployment = _deployment("candidate-a", provider="provider-a")
    provider = SequenceProvider(_success())
    service = ResilientExecutionService(
        InMemoryHealthTracker(),
        StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
    )

    with pytest.raises(ResilienceExecutionError, match="safety boundary"):
        asyncio.run(
            service.execute(
                _request(),
                _decision(deployment),
                max_output_tokens=100,
                safety=safety,
            )
        )

    assert provider.calls == []


def test_circuit_opens_and_prevents_provider_call_until_cooldown() -> None:
    deployment = _deployment("candidate-a", provider="provider-a")
    provider = SequenceProvider(_server_error(), _success())
    clock = FakeClock()
    health = InMemoryHealthTracker(
        CircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=30),
        clock=clock,
    )
    service = ResilientExecutionService(
        health,
        StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
        RetryPolicy(max_attempts_per_deployment=1, max_fallbacks=0),
        clock=clock,
    )

    with pytest.raises(ResilienceExecutionError):
        asyncio.run(service.execute(_request(), _decision(deployment), max_output_tokens=100))

    assert health.snapshot("candidate-a").circuit_state is CircuitState.OPEN
    with pytest.raises(ResilienceExecutionError) as exc_info:
        asyncio.run(service.execute(_request(), _decision(deployment), max_output_tokens=100))
    assert len(provider.calls) == 1
    assert exc_info.value.attempts[0].outcome is ExecutionAttemptOutcome.CIRCUIT_OPEN

    clock.advance(30)
    half_open = health.snapshot("candidate-a")
    assert half_open.circuit_state is CircuitState.HALF_OPEN
    assert half_open.status is HealthStatus.DEGRADED

    result = asyncio.run(service.execute(_request(), _decision(deployment), max_output_tokens=100))
    assert result.response.text == "ok"
    recovered = health.snapshot("candidate-a")
    assert recovered.circuit_state is CircuitState.CLOSED
    assert recovered.status is HealthStatus.HEALTHY


def test_out_of_group_fallback_candidate_fails_before_any_provider_call() -> None:
    selected = _deployment("candidate-a", provider="provider-a")
    unauthorized = _deployment(
        "candidate-x",
        provider="provider-b",
        model_group="reasoning-strong",
    )
    provider_a = SequenceProvider(_success())
    provider_b = SequenceProvider(_success())
    service = ResilientExecutionService(
        InMemoryHealthTracker(),
        StaticProviderResolver(
            {
                ("provider-a", "openai-compatible"): provider_a,
                ("provider-b", "openai-compatible"): provider_b,
            }
        ),
    )

    with pytest.raises(RankingInvariantViolation, match="outside"):
        asyncio.run(
            service.execute(_request(), _decision(selected, unauthorized), max_output_tokens=100)
        )

    assert provider_a.calls == []
    assert provider_b.calls == []
