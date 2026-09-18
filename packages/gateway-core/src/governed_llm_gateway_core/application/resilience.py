"""Phase 6 bounded retry, fallback, circuit-breaker, and health orchestration."""

import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import AsyncExitStack, nullcontext
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from governed_llm_gateway_contracts import GatewayRequest, RoutingProvenance

from governed_llm_gateway_core.domain.model_registry import ModelDeployment
from governed_llm_gateway_core.domain.resilience import (
    CircuitBreakerPolicy,
    CircuitState,
    DeploymentHealthSnapshot,
    FallbackSafetyState,
    HealthAdmission,
    HealthStatus,
    RetryPolicy,
)

from .execution_deadline import ExecutionDeadline, validate_execution_timeout_ms
from .health import DeploymentHealthPort, health_admission_scope, health_attempt_id
from .health_probe import bounded_probe_call, probe_expired_error
from .observability import ObservabilityPort
from .operational_evidence import OperationalAttemptRecorder, UtcClock
from .operational_recording import (
    invalidate_operational_completeness_best_effort,
    record_operational_attempt_best_effort,
    utc_now,
)
from .provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderPort,
    ProviderRequest,
    ProviderResponse,
    is_transient_provider_error,
)
from .ranking import RankedCandidate, RankingDecision, RankingInvariantViolation
from .telemetry import (
    GatewaySpanEventName,
    GatewaySpanName,
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
    generation: str = field(default_factory=lambda: uuid4().hex)
    probe_owner: str | None = None
    probe_expires_at: float | None = None


class InMemoryHealthTracker:
    """Initial per-process deployment health and circuit-breaker state."""

    def __init__(
        self,
        policy: CircuitBreakerPolicy | None = None,
        *,
        clock: Clock = time.monotonic,
    ) -> None:
        """Create isolated per-process state with attempt-owned recovery probes."""
        self._policy = policy or CircuitBreakerPolicy()
        self._clock = clock
        self._states: dict[str, _MutableDeploymentHealth] = {}

    async def snapshot(self, deployment_id: str) -> DeploymentHealthSnapshot:
        """Return current state, moving an expired open circuit to half-open."""
        state = self._state(deployment_id)
        self._refresh_circuit(state)
        return _snapshot(deployment_id, state)

    async def snapshots(self, deployment_ids: Sequence[str]) -> dict[str, DeploymentHealthSnapshot]:
        """Return deterministic snapshots for all requested deployments."""
        return {
            deployment_id: await self.snapshot(deployment_id) for deployment_id in deployment_ids
        }

    async def allow_request(
        self, deployment_id: str, *, attempt_id: str | None = None
    ) -> HealthAdmission | None:
        """Atomically admit one live HALF_OPEN owner without extending its lease."""
        owner = health_attempt_id(attempt_id)
        state = self._state(deployment_id)
        self._refresh_circuit(state)
        if state.circuit_state is CircuitState.OPEN:
            return None
        if state.circuit_state is CircuitState.CLOSED:
            return HealthAdmission(deployment_id, owner, state.generation)
        if state.probe_owner is not None and state.probe_owner != owner:
            return None
        if state.probe_owner is None:
            state.generation = uuid4().hex
            state.probe_owner = owner
            state.probe_expires_at = self._clock() + self._policy.probe_lease_seconds
        if state.probe_expires_at is None:
            raise RuntimeError("half-open probe has no expiry")
        return HealthAdmission(
            deployment_id, owner, state.generation, state.probe_expires_at - self._clock()
        )

    async def release_request(self, admission: HealthAdmission) -> None:
        """Release only the matching probe; cancellation is not provider failure."""
        state = self._state(admission.deployment_id)
        self._refresh_circuit(state)
        if admission.is_probe and self._matches(state, admission):
            self._retire_probe(state)

    async def is_admitted(self, admission: HealthAdmission) -> bool:
        """Check without consuming a new probe or extending lifetime."""
        state = self._state(admission.deployment_id)
        self._refresh_circuit(state)
        return self._matches(state, admission)

    async def record_success(
        self, deployment_id: str, *, latency_ms: int, admission: HealthAdmission | None = None
    ) -> bool:
        """Fence circuit recovery; reject a retired probe's late success."""
        state = self._state(deployment_id)
        self._refresh_circuit(state)
        controls_circuit = self._controls_circuit(deployment_id, state, admission)
        if admission is not None and admission.is_probe and not controls_circuit:
            return False
        state.request_count += 1
        state.success_count += 1
        state.last_latency_ms = latency_ms
        if controls_circuit:
            state.consecutive_transient_failures = 0
            state.circuit_state = CircuitState.CLOSED
            state.opened_at = None
            if admission is not None and admission.is_probe:
                self._retire_probe(state)
        return True

    async def record_failure(
        self,
        deployment_id: str,
        error: ProviderError,
        *,
        latency_ms: int,
        admission: HealthAdmission | None = None,
    ) -> None:
        """Record sanitized failure metadata and open the circuit on bounded transient failures."""
        state = self._state(deployment_id)
        self._refresh_circuit(state)
        controls_circuit = self._controls_circuit(deployment_id, state, admission)
        if admission is not None and admission.is_probe and not controls_circuit:
            return
        state.request_count += 1
        state.last_latency_ms = latency_ms
        if not is_transient_provider_error(error):
            if controls_circuit:
                state.consecutive_transient_failures = 0
                if admission is not None and admission.is_probe:
                    self._retire_probe(state)
            return

        state.transient_failure_count += 1
        if controls_circuit:
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
        if controls_circuit and should_open:
            state.circuit_state = CircuitState.OPEN
            state.opened_at = self._clock()
            self._retire_probe(state)

    @staticmethod
    def _matches(state: _MutableDeploymentHealth, admission: HealthAdmission) -> bool:
        return state.generation == admission.generation and (
            (state.circuit_state is CircuitState.CLOSED and not admission.is_probe)
            or (
                state.circuit_state is CircuitState.HALF_OPEN
                and admission.is_probe
                and state.probe_owner == admission.attempt_id
            )
        )

    def _controls_circuit(
        self, deployment_id: str, state: _MutableDeploymentHealth, admission: HealthAdmission | None
    ) -> bool:
        if admission is None:
            return state.circuit_state is CircuitState.CLOSED
        if admission.deployment_id != deployment_id:
            raise ValueError("health admission belongs to another deployment")
        return self._matches(state, admission)

    @staticmethod
    def _retire_probe(state: _MutableDeploymentHealth) -> None:
        state.generation = uuid4().hex
        state.probe_owner = None
        state.probe_expires_at = None

    def _state(self, deployment_id: str) -> _MutableDeploymentHealth:
        if not deployment_id or deployment_id.strip() != deployment_id:
            raise ValueError("deployment_id must be a non-empty normalized string")
        return self._states.setdefault(deployment_id, _MutableDeploymentHealth())

    def _refresh_circuit(self, state: _MutableDeploymentHealth) -> None:
        now = self._clock()
        if (
            state.circuit_state is CircuitState.OPEN
            and state.opened_at is not None
            and now - state.opened_at >= self._policy.cooldown_seconds
        ):
            state.circuit_state = CircuitState.HALF_OPEN
        if state.probe_expires_at is not None and now >= state.probe_expires_at:
            self._retire_probe(state)


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
        health: DeploymentHealthPort,
        resolver: ProviderResolver,
        retry_policy: RetryPolicy | None = None,
        *,
        clock: Clock = time.monotonic,
        sleeper: Sleeper = asyncio.sleep,
        observability: ObservabilityPort | None = None,
        operational_recorder: OperationalAttemptRecorder | None = None,
        utc_clock: UtcClock = utc_now,
        execution_timeout_ms: int | None = None,
    ) -> None:
        """Bind resilience controls plus optional local telemetry/evidence recording."""
        self._health = health
        self._resolver = resolver
        self._retry_policy = retry_policy or RetryPolicy()
        self._clock = clock
        self._sleeper = sleeper
        self._observability = observability
        self._operational_recorder = operational_recorder
        self._utc_clock = utc_clock
        validate_execution_timeout_ms(execution_timeout_ms)
        self._execution_timeout_ms = execution_timeout_ms

    async def execute(
        self,
        request: GatewayRequest,
        decision: RankingDecision,
        *,
        max_output_tokens: int,
        provider_timeout_seconds: float = 30.0,
        safety: FallbackSafetyState | None = None,
        deadline: ExecutionDeadline | None = None,
    ) -> ResilientExecutionResult:
        """Consume one budget for all attempts; local expiry never authorizes replay."""
        budget = deadline or ExecutionDeadline.start(self._execution_timeout_ms, clock=self._clock)
        return await budget.run(
            lambda: self._execute(
                request,
                decision,
                max_output_tokens=max_output_tokens,
                provider_timeout_seconds=provider_timeout_seconds,
                safety=safety,
                deadline=budget,
            )
        )

    async def _execute(
        self,
        request: GatewayRequest,
        decision: RankingDecision,
        *,
        max_output_tokens: int,
        provider_timeout_seconds: float,
        safety: FallbackSafetyState | None,
        deadline: ExecutionDeadline,
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
            for attempt_number in range(1, self._retry_policy.max_attempts_per_deployment + 1):
                deadline.check()
                provider = self._resolver.resolve(candidate.deployment)
                provider_request = ProviderRequest(
                    model=candidate.deployment.model_id,
                    messages=request.messages,
                    max_output_tokens=max_output_tokens,
                    timeout_seconds=provider_timeout_seconds,
                    structured_output=request.structured_output,
                    tools=request.tools,
                    parallel_tool_calling=request.requirements.parallel_tool_calling,
                )
                span_context = (
                    self._observability.start_span(
                        GatewaySpanName.PROVIDER_ATTEMPT.value,
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
                admission = await self._health.allow_request(deployment_id)
                if admission is None:
                    attempts.append(
                        ExecutionAttempt(
                            deployment_id=deployment_id,
                            attempt_number=0 if attempt_number == 1 else attempt_number,
                            outcome=ExecutionAttemptOutcome.CIRCUIT_OPEN,
                        )
                    )
                    break
                if attempt_number == 1:
                    fallback_sequence.append(deployment_id)
                started = self._clock()
                retry_delay_after_span: float | None = None
                async with AsyncExitStack() as attempt_stack:
                    await attempt_stack.enter_async_context(
                        health_admission_scope(
                            self._health,
                            admission,
                            cleanup_timeout_seconds=1.0 if deadline.enabled else None,
                        )
                    )
                    span = attempt_stack.enter_context(span_context)
                    if span is not None:
                        span.set_attributes(
                            {
                                "llm.workload": request.workload,
                                "llm.provider": candidate.deployment.provider,
                                "llm.model": candidate.deployment.model_id,
                                "llm.deployment": deployment_id,
                                "llm.attempt_number": attempt_number,
                                "llm.fallback_count": len(fallback_sequence) - 1,
                                "llm.streaming": False,
                                "client.protocol": request.client_protocol.value,
                                "routing.decision_id": decision.routing.routing_decision_id,
                                "routing.policy_id": decision.routing.policy.policy_id,
                                "routing.policy_version": decision.routing.policy.policy_version,
                                "routing.policy_digest": decision.routing.policy.policy_digest,
                                "routing.model_group": decision.routing.authorized_model_group,
                                "registry.digest": decision.routing.model_registry_digest,
                                "ranking.policy_version": decision.routing.ranking_policy_version,
                                "ranking.policy_digest": decision.routing.ranking_policy_digest,
                                "ranking.score_snapshot_id": decision.routing.score_snapshot_id,
                            },
                        )
                    try:
                        deadline.check()
                        response = await bounded_probe_call(
                            admission,
                            candidate.deployment.provider,
                            provider.generate(provider_request),
                        )
                        deadline.check()
                        latency_ms = _latency_ms(started, self._clock())
                        if not await self._health.record_success(
                            deployment_id, latency_ms=latency_ms, admission=admission
                        ):
                            raise probe_expired_error(candidate.deployment.provider)
                    except asyncio.CancelledError:
                        invalidate_operational_completeness_best_effort(
                            self._operational_recorder,
                            utc_clock=self._utc_clock,
                        )
                        raise
                    except ProviderError as exc:
                        deadline.check()
                        latency_ms = _latency_ms(started, self._clock())
                        record_operational_attempt_best_effort(
                            self._operational_recorder,
                            utc_clock=self._utc_clock,
                            request=request,
                            deployment_id=deployment_id,
                            attempt_number=attempt_number,
                            fallback_index=len(fallback_sequence) - 1,
                            latency_ms=latency_ms,
                            provider_error=exc,
                        )
                        await self._health.record_failure(
                            deployment_id, exc, latency_ms=latency_ms, admission=admission
                        )
                        transient = is_transient_provider_error(exc)
                        retry_delay: float | None = None
                        can_retry = (
                            transient
                            and attempt_number < self._retry_policy.max_attempts_per_deployment
                            and (await self._health.snapshot(deployment_id)).circuit_state
                            is not CircuitState.OPEN
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
                            span.set_attributes(failure_attributes)
                            span.mark_failure(exc.code.value)
                            if can_retry and retry_delay is not None:
                                span.add_event(
                                    GatewaySpanEventName.RETRY.value,
                                    {
                                        "retry_count": attempt_number,
                                        "llm.retry_delay_ms": int(retry_delay * 1000),
                                        "llm.deployment": deployment_id,
                                    },
                                )
                            elif transient and candidate_index + 1 < len(bounded_candidates):
                                span.add_event(
                                    GatewaySpanEventName.FALLBACK.value,
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
                            retry_delay_after_span = retry_delay
                        else:
                            break
                    except Exception:
                        invalidate_operational_completeness_best_effort(
                            self._operational_recorder,
                            utc_clock=self._utc_clock,
                        )
                        raise
                    else:
                        latency_ms = _latency_ms(started, self._clock())
                        record_operational_attempt_best_effort(
                            self._operational_recorder,
                            utc_clock=self._utc_clock,
                            request=request,
                            deployment_id=deployment_id,
                            attempt_number=attempt_number,
                            fallback_index=len(fallback_sequence) - 1,
                            latency_ms=latency_ms,
                        )
                        if span is not None:
                            span.set_attributes(
                                {
                                    "llm.latency_ms": latency_ms,
                                    "llm.usage.input_count": response.usage.input_tokens,
                                    "llm.usage.output_count": response.usage.output_tokens,
                                },
                            )
                            span.mark_success()
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

                if retry_delay_after_span is not None:
                    deadline.check()
                    await self._sleeper(retry_delay_after_span)
                    continue

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
