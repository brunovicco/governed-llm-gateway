"""Phase 6 bounded retry, fallback, circuit-breaker, and health orchestration."""

import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

from a2a_otel_kit import Observability
from governed_llm_gateway_contracts import GatewayRequest, RoutingProvenance

from governed_llm_gateway_core.domain.model_registry import ModelDeployment
from governed_llm_gateway_core.domain.resilience import (
    CircuitBreakerPolicy,
    CircuitState,
    DeploymentHealthSnapshot,
    FallbackSafetyState,
    HealthStatus,
    RetryPolicy,
)

from .provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderPort,
    ProviderRequest,
    ProviderResponse,
)
from .ranking import RankedCandidate, RankingDecision, RankingInvariantViolation
from .telemetry import (
    add_gateway_span_event,
    mark_span_failure,
    mark_span_success,
    set_gateway_span_attributes,
)

Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]


class ExecutionAttemptOutcome(StrEnum):
    """Stable result categories for one concrete provider attempt."""

    SUCCEEDED = "succeeded"
    TRANSIENT_FAILURE = "transient_failure"
    PERMANENT_FAILURE = "permanent_failure"
    CIRCUIT_OPEN = "circuit_open"


@dataclass(frozen=True, slots=True)
class ExecutionAttempt:
    """Metadata-only evidence for one provider attempt or circuit skip."""

    deployment_id: str
    attempt_number: int
    outcome: ExecutionAttemptOutcome
    latency_ms: int = 0
    error_code: ProviderErrorCode | None = None
    status_code: int | None = None
    retry_delay_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class ResilientExecutionResult:
    """Successful execution plus retry/fallback reconstruction evidence."""

    deployment: ModelDeployment
    response: ProviderResponse
    routing: RoutingProvenance
    attempts: tuple[ExecutionAttempt, ...]


class ProviderResolver(Protocol):
    """Resolve the configured adapter for one concrete registry deployment."""

    def resolve(self, deployment: ModelDeployment) -> ProviderPort:
        """Return the provider adapter bound to the deployment's API family."""
        ...


class ProviderResolutionError(RuntimeError):
    """Raised when an authorized deployment has no configured provider adapter."""


class StaticProviderResolver:
    """Small composition helper keyed by provider and API family."""

    def __init__(self, providers: Mapping[tuple[str, str], ProviderPort]) -> None:
        """Copy the configured adapter mapping so callers cannot mutate it afterward."""
        self._providers = dict(providers)

    def resolve(self, deployment: ModelDeployment) -> ProviderPort:
        """Resolve an adapter without provider/model authorization authority."""
        key = (deployment.provider, deployment.api_family)
        try:
            return self._providers[key]
        except KeyError as exc:
            raise ProviderResolutionError(
                f"no provider adapter configured for {deployment.provider}/{deployment.api_family}"
            ) from exc


@dataclass(slots=True)
class _MutableDeploymentHealth:
    request_count: int = 0
    success_count: int = 0
    transient_failure_count: int = 0
    timeout_count: int = 0
    rate_limit_count: int = 0
    server_error_count: int = 0
    consecutive_transient_failures: int = 0
    last_latency_ms: int | None = None
    circuit_state: CircuitState = CircuitState.CLOSED
    opened_at: float | None = None


class InMemoryHealthTracker:
    """Initial per-process deployment health and circuit-breaker state."""

    def __init__(
        self,
        policy: CircuitBreakerPolicy | None = None,
        *,
        clock: Clock = time.monotonic,
    ) -> None:
        """Create isolated per-process state; shared Redis state is deliberately deferred."""
        self._policy = policy or CircuitBreakerPolicy()
        self._clock = clock
        self._states: dict[str, _MutableDeploymentHealth] = {}

    def snapshot(self, deployment_id: str) -> DeploymentHealthSnapshot:
        """Return current state, moving an expired open circuit to half-open."""
        state = self._state(deployment_id)
        self._refresh_circuit(state)
        return _snapshot(deployment_id, state)

    def snapshots(self, deployment_ids: tuple[str, ...]) -> dict[str, DeploymentHealthSnapshot]:
        """Return deterministic snapshots for all requested deployments."""
        return {deployment_id: self.snapshot(deployment_id) for deployment_id in deployment_ids}

    def allow_request(self, deployment_id: str) -> bool:
        """Reject calls while the circuit is open and allow a half-open probe after cooldown."""
        state = self._state(deployment_id)
        self._refresh_circuit(state)
        return state.circuit_state is not CircuitState.OPEN

    def record_success(self, deployment_id: str, *, latency_ms: int) -> None:
        """Record success and close/reset a half-open or degraded circuit."""
        state = self._state(deployment_id)
        state.request_count += 1
        state.success_count += 1
        state.last_latency_ms = latency_ms
        state.consecutive_transient_failures = 0
        state.circuit_state = CircuitState.CLOSED
        state.opened_at = None

    def record_failure(
        self,
        deployment_id: str,
        error: ProviderError,
        *,
        latency_ms: int,
    ) -> None:
        """Record sanitized failure metadata and open the circuit on bounded transient failures."""
        state = self._state(deployment_id)
        state.request_count += 1
        state.last_latency_ms = latency_ms
        if not _is_transient(error):
            state.consecutive_transient_failures = 0
            return

        state.transient_failure_count += 1
        state.consecutive_transient_failures += 1
        if error.code is ProviderErrorCode.TIMEOUT:
            state.timeout_count += 1
        if error.code is ProviderErrorCode.RATE_LIMIT:
            state.rate_limit_count += 1
        if error.code is ProviderErrorCode.UNAVAILABLE and (
            error.status_code is None or error.status_code >= 500
        ):
            state.server_error_count += 1

        should_open = (
            state.circuit_state is CircuitState.HALF_OPEN
            or state.consecutive_transient_failures >= self._policy.failure_threshold
        )
        if should_open:
            state.circuit_state = CircuitState.OPEN
            state.opened_at = self._clock()

    def _state(self, deployment_id: str) -> _MutableDeploymentHealth:
        if not deployment_id or deployment_id.strip() != deployment_id:
            raise ValueError("deployment_id must be a non-empty normalized string")
        return self._states.setdefault(deployment_id, _MutableDeploymentHealth())

    def _refresh_circuit(self, state: _MutableDeploymentHealth) -> None:
        if state.circuit_state is not CircuitState.OPEN or state.opened_at is None:
            return
        if self._clock() - state.opened_at >= self._policy.cooldown_seconds:
            state.circuit_state = CircuitState.HALF_OPEN


class ResilienceExecutionError(RuntimeError):
    """Sanitized terminal execution failure after bounded resilience handling."""

    def __init__(
        self,
        message: str,
        *,
        attempts: tuple[ExecutionAttempt, ...],
        last_error_code: ProviderErrorCode | None,
    ) -> None:
        """Retain only bounded operational failure metadata."""
        super().__init__(message)
        self.attempts = attempts
        self.last_error_code = last_error_code


class ResilientExecutionService:
    """Execute Phase 5 ranked candidates with bounded safe resilience semantics."""

    def __init__(
        self,
        health: InMemoryHealthTracker,
        resolver: ProviderResolver,
        retry_policy: RetryPolicy | None = None,
        *,
        clock: Clock = time.monotonic,
        sleeper: Sleeper = asyncio.sleep,
        observability: Observability | None = None,
    ) -> None:
        """Bind health, resolver, retry controls, and optional Phase 9 telemetry."""
        self._health = health
        self._resolver = resolver
        self._retry_policy = retry_policy or RetryPolicy()
        self._clock = clock
        self._sleeper = sleeper
        self._observability = observability

    async def execute(
        self,
        request: GatewayRequest,
        decision: RankingDecision,
        *,
        max_output_tokens: int,
        provider_timeout_seconds: float = 30.0,
        safety: FallbackSafetyState | None = None,
    ) -> ResilientExecutionResult:
        """Retry transient failures and fall back only within the ranked authorized candidates."""
        if decision.selected is None:
            raise ResilienceExecutionError(
                "no eligible authorized deployment is available for execution",
                attempts=(),
                last_error_code=None,
            )
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if provider_timeout_seconds <= 0:
            raise ValueError("provider_timeout_seconds must be positive")

        safety_state = safety or FallbackSafetyState()
        if not safety_state.automatic_replay_allowed:
            raise ResilienceExecutionError(
                "automatic model execution is blocked by the side-effect/replay safety boundary",
                attempts=(),
                last_error_code=None,
            )

        candidates = (decision.selected, *decision.alternatives)
        bounded_candidates = candidates[: self._retry_policy.max_fallbacks + 1]
        for candidate in bounded_candidates:
            self._validate_candidate(candidate, decision)

        attempts: list[ExecutionAttempt] = []
        fallback_sequence: list[str] = []
        last_error: ProviderError | None = None

        for candidate_index, candidate in enumerate(bounded_candidates):
            deployment_id = candidate.deployment.deployment_id
            if not self._health.allow_request(deployment_id):
                attempts.append(
                    ExecutionAttempt(
                        deployment_id=deployment_id,
                        attempt_number=0,
                        outcome=ExecutionAttemptOutcome.CIRCUIT_OPEN,
                    )
                )
                continue

            fallback_sequence.append(deployment_id)
            for attempt_number in range(1, self._retry_policy.max_attempts_per_deployment + 1):
                if not self._health.allow_request(deployment_id):
                    attempts.append(
                        ExecutionAttempt(
                            deployment_id=deployment_id,
                            attempt_number=attempt_number,
                            outcome=ExecutionAttemptOutcome.CIRCUIT_OPEN,
                        )
                    )
                    break

                provider = self._resolver.resolve(candidate.deployment)
                provider_request = ProviderRequest(
                    model=candidate.deployment.model_id,
                    messages=request.messages,
                    max_output_tokens=max_output_tokens,
                    timeout_seconds=provider_timeout_seconds,
                    structured_output=request.structured_output,
                    tools=request.tools,
                )
                span_context = (
                    self._observability.start_span(
                        "provider.inference",
                        attributes={
                            "request_id": str(request.request_id),
                            "operation": "generate",
                            "retry_count": attempt_number - 1,
                        },
                        record_exception=False,
                    )
                    if self._observability is not None
                    else nullcontext(None)
                )
                started = self._clock()
                with span_context as span:
                    if span is not None:
                        set_gateway_span_attributes(
                            span,
                            {
                                "llm.workload": request.workload,
                                "llm.provider": candidate.deployment.provider,
                                "llm.model": candidate.deployment.model_id,
                                "llm.deployment": deployment_id,
                                "llm.attempt_number": attempt_number,
                                "llm.fallback_count": len(fallback_sequence) - 1,
                                "llm.streaming": False,
                                "routing.decision_id": decision.routing.routing_decision_id,
                                "routing.model_group": decision.routing.authorized_model_group,
                                "registry.digest": decision.routing.model_registry_digest,
                                "ranking.policy_version": decision.routing.ranking_policy_version,
                                "ranking.policy_digest": decision.routing.ranking_policy_digest,
                                "ranking.score_snapshot_id": decision.routing.score_snapshot_id,
                            },
                        )
                    try:
                        response = await provider.generate(provider_request)
                    except ProviderError as exc:
                        latency_ms = _latency_ms(started, self._clock())
                        self._health.record_failure(deployment_id, exc, latency_ms=latency_ms)
                        transient = _is_transient(exc)
                        retry_delay: float | None = None
                        can_retry = (
                            transient
                            and attempt_number < self._retry_policy.max_attempts_per_deployment
                            and self._health.allow_request(deployment_id)
                        )
                        if can_retry:
                            retry_delay = _retry_delay_seconds(
                                self._retry_policy,
                                request_id=str(request.request_id),
                                deployment_id=deployment_id,
                                attempt_number=attempt_number,
                                retry_after_seconds=exc.retry_after_seconds,
                            )
                        if span is not None:
                            failure_attributes: dict[str, object] = {
                                "llm.latency_ms": latency_ms,
                            }
                            if exc.status_code is not None:
                                failure_attributes["http.status_code"] = exc.status_code
                            set_gateway_span_attributes(span, failure_attributes)
                            mark_span_failure(span, exc.code.value)
                            if can_retry and retry_delay is not None:
                                add_gateway_span_event(
                                    span,
                                    "llm.gateway.retry",
                                    {
                                        "retry_count": attempt_number,
                                        "llm.retry_delay_ms": int(retry_delay * 1000),
                                        "llm.deployment": deployment_id,
                                    },
                                )
                            elif transient and candidate_index + 1 < len(bounded_candidates):
                                add_gateway_span_event(
                                    span,
                                    "llm.gateway.fallback",
                                    {
                                        "llm.fallback_count": len(fallback_sequence),
                                        "llm.deployment": deployment_id,
                                    },
                                )
                        attempts.append(
                            ExecutionAttempt(
                                deployment_id=deployment_id,
                                attempt_number=attempt_number,
                                outcome=(
                                    ExecutionAttemptOutcome.TRANSIENT_FAILURE
                                    if transient
                                    else ExecutionAttemptOutcome.PERMANENT_FAILURE
                                ),
                                latency_ms=latency_ms,
                                error_code=exc.code,
                                status_code=exc.status_code,
                                retry_delay_seconds=retry_delay,
                            )
                        )
                        last_error = exc
                        if not transient:
                            raise ResilienceExecutionError(
                                "provider returned a permanent failure; "
                                "automatic retry/fallback stopped",
                                attempts=tuple(attempts),
                                last_error_code=exc.code,
                            ) from exc
                        if can_retry and retry_delay is not None:
                            await self._sleeper(retry_delay)
                            continue
                        break
                    else:
                        latency_ms = _latency_ms(started, self._clock())
                        self._health.record_success(deployment_id, latency_ms=latency_ms)
                        if span is not None:
                            set_gateway_span_attributes(
                                span,
                                {
                                    "llm.latency_ms": latency_ms,
                                    "llm.usage.input_count": response.usage.input_tokens,
                                    "llm.usage.output_count": response.usage.output_tokens,
                                },
                            )
                            mark_span_success(span)
                        attempts.append(
                            ExecutionAttempt(
                                deployment_id=deployment_id,
                                attempt_number=attempt_number,
                                outcome=ExecutionAttemptOutcome.SUCCEEDED,
                                latency_ms=latency_ms,
                            )
                        )
                        routing = replace(
                            decision.routing,
                            provider=candidate.deployment.provider,
                            model=candidate.deployment.model_id,
                            deployment=deployment_id,
                            fallback_sequence=tuple(fallback_sequence),
                        )
                        return ResilientExecutionResult(
                            deployment=candidate.deployment,
                            response=response,
                            routing=routing,
                            attempts=tuple(attempts),
                        )

        raise ResilienceExecutionError(
            "all bounded authorized execution candidates were exhausted",
            attempts=tuple(attempts),
            last_error_code=last_error.code if last_error is not None else None,
        )

    @staticmethod
    def _validate_candidate(candidate: RankedCandidate, decision: RankingDecision) -> None:
        if candidate.deployment.model_group != decision.routing.authorized_model_group:
            raise RankingInvariantViolation(
                "resilience candidate is outside the PDP-authorized logical model group"
            )


def _is_transient(error: ProviderError) -> bool:
    return error.retryable and error.code in {
        ProviderErrorCode.RATE_LIMIT,
        ProviderErrorCode.TIMEOUT,
        ProviderErrorCode.UNAVAILABLE,
        ProviderErrorCode.TRANSPORT,
    }


def _retry_delay_seconds(
    policy: RetryPolicy,
    *,
    request_id: str,
    deployment_id: str,
    attempt_number: int,
    retry_after_seconds: float | None,
) -> float:
    exponent = attempt_number - 1
    if exponent < 0:
        exponent = 0
    exponential: float = policy.base_delay_seconds * (2.0**exponent)
    if exponential > policy.max_delay_seconds:
        exponential = policy.max_delay_seconds

    seed = f"{request_id}:{deployment_id}:{attempt_number}".encode()
    unit: float = int.from_bytes(hashlib.sha256(seed).digest()[:8], "big") / float(2**64)
    jittered: float = exponential + (exponential * policy.jitter_ratio * unit)
    requested: float = retry_after_seconds if retry_after_seconds is not None else 0.0
    delay: float = jittered if jittered >= requested else requested
    if delay > policy.max_delay_seconds:
        delay = policy.max_delay_seconds
    return delay


def _latency_ms(started: float, finished: float) -> int:
    return max(0, int((finished - started) * 1000))


def _snapshot(
    deployment_id: str,
    state: _MutableDeploymentHealth,
) -> DeploymentHealthSnapshot:
    if state.circuit_state is CircuitState.OPEN:
        status = HealthStatus.UNHEALTHY
    elif state.circuit_state is CircuitState.HALF_OPEN or state.consecutive_transient_failures:
        status = HealthStatus.DEGRADED
    else:
        status = HealthStatus.HEALTHY
    return DeploymentHealthSnapshot(
        deployment_id=deployment_id,
        status=status,
        circuit_state=state.circuit_state,
        request_count=state.request_count,
        success_count=state.success_count,
        transient_failure_count=state.transient_failure_count,
        timeout_count=state.timeout_count,
        rate_limit_count=state.rate_limit_count,
        server_error_count=state.server_error_count,
        consecutive_transient_failures=state.consecutive_transient_failures,
        last_latency_ms=state.last_latency_ms,
    )
