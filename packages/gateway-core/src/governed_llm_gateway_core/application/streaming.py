"""Phase 8 normalized streaming orchestration with explicit replay boundaries."""

import asyncio
import hashlib
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing
from dataclasses import replace

from governed_llm_gateway_contracts import (
    Capability,
    GatewayError,
    GatewayRequest,
    GatewayStreamEvent,
    RoutingProvenance,
    StreamEventType,
    Usage,
)

from governed_llm_gateway_core.domain.resilience import RetryPolicy

from .provider import (
    ProviderContentDelta,
    ProviderError,
    ProviderErrorCode,
    ProviderRequest,
    ProviderResponseCompleted,
    ProviderResponseStarted,
    ProviderStreamingPort,
    ProviderToolCallArgumentsDelta,
    ProviderToolCallCompleted,
    ProviderToolCallStarted,
    ProviderUsageCompleted,
)
from .ranking import RankedCandidate, RankingDecision, RankingInvariantViolation
from .resilience import InMemoryHealthTracker, ProviderResolutionError, ProviderResolver

Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]


class StreamingExecutionService:
    """Execute one ranked request as a normalized stream without unsafe post-output replay."""

    def __init__(
        self,
        *,
        health: InMemoryHealthTracker,
        resolver: ProviderResolver,
        retry_policy: RetryPolicy | None = None,
        clock: Clock = time.monotonic,
        sleeper: Sleeper = asyncio.sleep,
    ) -> None:
        """Bind runtime health, provider resolution, and bounded retry controls."""
        self._health = health
        self._resolver = resolver
        self._retry_policy = retry_policy or RetryPolicy()
        self._clock = clock
        self._sleeper = sleeper

    async def stream(
        self,
        request: GatewayRequest,
        decision: RankingDecision,
        *,
        max_output_tokens: int,
        provider_timeout_seconds: float = 30.0,
    ) -> AsyncGenerator[GatewayStreamEvent]:
        """Yield a deterministic gateway stream and stop replay once semantic output is visible."""
        if not request.requirements.streaming:
            raise ValueError("streaming execution requires WorkloadRequirements.streaming")
        if max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if provider_timeout_seconds <= 0:
            raise ValueError("provider_timeout_seconds must be positive")
        if decision.selected is None:
            yield _failed_event(
                request=request,
                sequence_number=1,
                routing=decision.routing,
                code="no_eligible_streaming_deployment",
                message="no eligible authorized streaming deployment is available",
                retryable=False,
                partial=False,
            )
            return

        candidates = (decision.selected, *decision.alternatives)
        bounded = candidates[: self._retry_policy.max_fallbacks + 1]
        for candidate in bounded:
            _validate_streaming_candidate(candidate, decision)

        fallback_sequence: list[str] = []
        last_error: ProviderError | None = None
        last_routing = decision.routing

        for candidate in bounded:
            deployment = candidate.deployment
            deployment_id = deployment.deployment_id
            if not self._health.allow_request(deployment_id):
                continue
            fallback_sequence.append(deployment_id)
            routing = _routing_for_candidate(decision, candidate, fallback_sequence)
            last_routing = routing

            try:
                resolved = self._resolver.resolve(deployment)
            except ProviderResolutionError:
                yield _failed_event(
                    request=request,
                    sequence_number=1,
                    routing=routing,
                    code="provider_adapter_unavailable",
                    message="selected deployment has no configured provider adapter",
                    retryable=False,
                    partial=False,
                )
                return
            if not isinstance(resolved, ProviderStreamingPort):
                yield _failed_event(
                    request=request,
                    sequence_number=1,
                    routing=routing,
                    code="streaming_not_supported",
                    message="selected provider adapter does not implement streaming",
                    retryable=False,
                    partial=False,
                )
                return
            if not resolved.feature_support.native_streaming:
                yield _failed_event(
                    request=request,
                    sequence_number=1,
                    routing=routing,
                    code="streaming_not_supported",
                    message="selected provider API family has no verified streaming support",
                    retryable=False,
                    partial=False,
                )
                return
            if not resolved.feature_support.streaming_usage:
                yield _failed_event(
                    request=request,
                    sequence_number=1,
                    routing=routing,
                    code="streaming_usage_unavailable",
                    message="selected provider cannot finalize normalized streaming usage",
                    retryable=False,
                    partial=False,
                )
                return

            for attempt_number in range(1, self._retry_policy.max_attempts_per_deployment + 1):
                if not self._health.allow_request(deployment_id):
                    break

                provider_request = _provider_request(
                    request,
                    model=deployment.model_id,
                    max_output_tokens=max_output_tokens,
                    timeout_seconds=provider_timeout_seconds,
                )
                provider_started = False
                public_started = False
                semantic_output = False
                usage_seen = False
                sequence = 0
                started_at = self._clock()

                try:
                    provider_stream = resolved.stream(provider_request)
                    async with aclosing(provider_stream) as events:
                        async for event in events:
                            if isinstance(event, ProviderResponseStarted):
                                if provider_started:
                                    raise _invalid_stream_event(
                                        deployment.provider,
                                        "provider emitted response start more than once",
                                    )
                                provider_started = True
                                continue
                            if not provider_started:
                                raise _invalid_stream_event(
                                    deployment.provider,
                                    "provider emitted stream data before response start",
                                )

                            if isinstance(
                                event,
                                ProviderContentDelta
                                | ProviderToolCallStarted
                                | ProviderToolCallArgumentsDelta
                                | ProviderToolCallCompleted,
                            ):
                                semantic_output = True
                                if not public_started:
                                    sequence += 1
                                    public_started = True
                                    yield GatewayStreamEvent(
                                        event_type=StreamEventType.RESPONSE_STARTED,
                                        request_id=request.request_id,
                                        sequence_number=sequence,
                                        routing=routing,
                                    )
                                sequence += 1
                                yield _semantic_gateway_event(
                                    request=request,
                                    sequence_number=sequence,
                                    event=event,
                                )
                                continue

                            if isinstance(event, ProviderUsageCompleted):
                                if usage_seen:
                                    raise _invalid_stream_event(
                                        deployment.provider,
                                        "provider emitted final usage more than once",
                                    )
                                if not semantic_output:
                                    raise _invalid_stream_event(
                                        deployment.provider,
                                        "provider emitted final usage before semantic output",
                                    )
                                usage_seen = True
                                sequence += 1
                                yield GatewayStreamEvent(
                                    event_type=StreamEventType.USAGE_COMPLETED,
                                    request_id=request.request_id,
                                    sequence_number=sequence,
                                    usage=Usage(
                                        input_tokens=event.usage.input_tokens,
                                        output_tokens=event.usage.output_tokens,
                                    ),
                                )
                                continue

                            if isinstance(event, ProviderResponseCompleted):
                                if not semantic_output or not usage_seen or not public_started:
                                    raise _invalid_stream_event(
                                        deployment.provider,
                                        "provider completed before semantic output and final usage",
                                    )
                                latency_ms = _latency_ms(started_at, self._clock())
                                self._health.record_success(
                                    deployment_id,
                                    latency_ms=latency_ms,
                                )
                                sequence += 1
                                yield GatewayStreamEvent(
                                    event_type=StreamEventType.RESPONSE_COMPLETED,
                                    request_id=request.request_id,
                                    sequence_number=sequence,
                                    routing=routing,
                                    finish_reason=event.finish_reason,
                                )
                                return

                            raise _invalid_stream_event(
                                deployment.provider,
                                "provider emitted an unknown normalized stream event",
                            )

                    raise _invalid_stream_event(
                        deployment.provider,
                        "provider stream ended without normalized completion",
                    )
                except asyncio.CancelledError:
                    raise
                except ProviderError as exc:
                    latency_ms = _latency_ms(started_at, self._clock())
                    self._health.record_failure(deployment_id, exc, latency_ms=latency_ms)
                    last_error = exc

                    if semantic_output:
                        sequence += 1
                        yield _failed_event(
                            request=request,
                            sequence_number=sequence,
                            routing=routing,
                            code=exc.code.value,
                            message="provider stream failed after partial output",
                            retryable=False,
                            partial=True,
                        )
                        return

                    transient = _is_transient(exc)
                    can_retry = (
                        transient
                        and attempt_number < self._retry_policy.max_attempts_per_deployment
                        and self._health.allow_request(deployment_id)
                    )
                    if can_retry:
                        delay = _retry_delay_seconds(
                            self._retry_policy,
                            request_id=str(request.request_id),
                            deployment_id=deployment_id,
                            attempt_number=attempt_number,
                            retry_after_seconds=exc.retry_after_seconds,
                        )
                        await self._sleeper(delay)
                        continue
                    if transient:
                        break
                    yield _failed_event(
                        request=request,
                        sequence_number=1,
                        routing=routing,
                        code=exc.code.value,
                        message="provider stream failed before output",
                        retryable=False,
                        partial=False,
                    )
                    return

        retryable = last_error.retryable if last_error is not None else False
        code = last_error.code.value if last_error is not None else "streaming_candidates_exhausted"
        yield _failed_event(
            request=request,
            sequence_number=1,
            routing=last_routing,
            code=code,
            message="all bounded authorized streaming candidates were exhausted",
            retryable=retryable,
            partial=False,
        )


def _provider_request(
    request: GatewayRequest,
    *,
    model: str,
    max_output_tokens: int,
    timeout_seconds: float,
) -> ProviderRequest:
    return ProviderRequest(
        model=model,
        messages=request.messages,
        max_output_tokens=max_output_tokens,
        timeout_seconds=timeout_seconds,
        structured_output=request.structured_output,
        tools=request.tools,
    )


def _validate_streaming_candidate(candidate: RankedCandidate, decision: RankingDecision) -> None:
    if candidate.deployment.model_group != decision.routing.authorized_model_group:
        raise RankingInvariantViolation(
            "streaming candidate is outside the PDP-authorized logical model group"
        )
    if Capability.STREAMING not in candidate.deployment.capabilities:
        raise RankingInvariantViolation(
            "ranked streaming candidate does not advertise the streaming capability"
        )


def _routing_for_candidate(
    decision: RankingDecision,
    candidate: RankedCandidate,
    fallback_sequence: list[str],
) -> RoutingProvenance:
    return replace(
        decision.routing,
        provider=candidate.deployment.provider,
        model=candidate.deployment.model_id,
        deployment=candidate.deployment.deployment_id,
        fallback_sequence=tuple(fallback_sequence),
    )


def _semantic_gateway_event(
    *,
    request: GatewayRequest,
    sequence_number: int,
    event: (
        ProviderContentDelta
        | ProviderToolCallStarted
        | ProviderToolCallArgumentsDelta
        | ProviderToolCallCompleted
    ),
) -> GatewayStreamEvent:
    if isinstance(event, ProviderContentDelta):
        return GatewayStreamEvent(
            event_type=StreamEventType.CONTENT_DELTA,
            request_id=request.request_id,
            sequence_number=sequence_number,
            delta=event.delta,
        )
    if isinstance(event, ProviderToolCallStarted):
        return GatewayStreamEvent(
            event_type=StreamEventType.TOOL_CALL_STARTED,
            request_id=request.request_id,
            sequence_number=sequence_number,
            tool_call_id=event.call_id,
            tool_name=event.name,
        )
    if isinstance(event, ProviderToolCallArgumentsDelta):
        return GatewayStreamEvent(
            event_type=StreamEventType.TOOL_CALL_ARGUMENTS_DELTA,
            request_id=request.request_id,
            sequence_number=sequence_number,
            tool_call_id=event.call_id,
            delta=event.delta,
        )
    return GatewayStreamEvent(
        event_type=StreamEventType.TOOL_CALL_COMPLETED,
        request_id=request.request_id,
        sequence_number=sequence_number,
        tool_call=event.call,
    )


def _failed_event(
    *,
    request: GatewayRequest,
    sequence_number: int,
    routing: RoutingProvenance,
    code: str,
    message: str,
    retryable: bool,
    partial: bool,
) -> GatewayStreamEvent:
    return GatewayStreamEvent(
        event_type=StreamEventType.RESPONSE_FAILED,
        request_id=request.request_id,
        sequence_number=sequence_number,
        routing=routing,
        error=GatewayError(code=code, message=message, retryable=retryable),
        partial=partial,
    )


def _invalid_stream_event(provider: str, message: str) -> ProviderError:
    return ProviderError(
        provider=provider,
        code=ProviderErrorCode.INVALID_RESPONSE,
        message=message,
        retryable=False,
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
    exponent = max(0, attempt_number - 1)
    exponential = min(
        policy.max_delay_seconds,
        policy.base_delay_seconds * (2.0**exponent),
    )
    seed = f"{request_id}:{deployment_id}:{attempt_number}".encode()
    unit = int.from_bytes(hashlib.sha256(seed).digest()[:8], "big") / float(2**64)
    jittered = exponential + (exponential * policy.jitter_ratio * unit)
    requested = retry_after_seconds if retry_after_seconds is not None else 0.0
    return min(policy.max_delay_seconds, max(jittered, requested))


def _latency_ms(started: float, finished: float) -> int:
    return max(0, int((finished - started) * 1000))
