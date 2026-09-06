from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one marker, found {count}")
    target.write_text(text.replace(old, new, 1))


# Application recorder port.
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/application/operational_evidence.py",
    "\n\nclass OperationalSampleSource(Protocol):\n",
    """

class OperationalAttemptRecorder(Protocol):
    \"\"\"Record process-local attempt evidence without remote I/O authority.\"\"\"

    def record(self, sample: OperationalAttemptSample) -> None:
        \"\"\"Persist one schema-compatible provider-attempt sample locally.\"\"\"
        ...

    def invalidate_completeness(self, *, observed_at: datetime) -> None:
        \"\"\"Advance a conservative boundary when complete evidence cannot be proven.\"\"\"
        ...


class OperationalSampleSource(Protocol):
""",
)

# Process-local completeness invalidation.
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/adapters/operational_samples_memory.py",
    "        self._evicted_through: datetime | None = None\n",
    "        self._evicted_through: datetime | None = None\n        self._incomplete_through: datetime | None = None\n",
)
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/adapters/operational_samples_memory.py",
    """    @property
    def evicted_through(self) -> datetime | None:
        \"\"\"Return the latest timestamp whose history may have been truncated by capacity.\"\"\"
        return self._evicted_through

    def record(self, sample: OperationalAttemptSample) -> None:
""",
    """    @property
    def evicted_through(self) -> datetime | None:
        \"\"\"Return the latest timestamp whose history may have been truncated by capacity.\"\"\"
        return self._evicted_through

    @property
    def incomplete_through(self) -> datetime | None:
        \"\"\"Return the latest timestamp through which complete runtime history is uncertain.\"\"\"
        return self._incomplete_through

    def invalidate_completeness(self, *, observed_at: datetime) -> None:
        \"\"\"Conservatively invalidate history through one unrepresentable attempt outcome.\"\"\"
        now = self._clock()
        _validate_utc(now, \"source clock\")
        _validate_utc(observed_at, \"observed_at\")
        if observed_at < self._coverage_start:
            raise OperationalEvidenceMaterializationError(
                \"operational completeness gap predates process-local source coverage\"
            )
        if observed_at > now:
            raise OperationalEvidenceMaterializationError(
                \"operational completeness gap cannot be recorded from the future\"
            )
        if self._incomplete_through is None or observed_at > self._incomplete_through:
            self._incomplete_through = observed_at

    def record(self, sample: OperationalAttemptSample) -> None:
""",
)
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/adapters/operational_samples_memory.py",
    """        if self._evicted_through is not None and window_start <= self._evicted_through:
            raise OperationalEvidenceMaterializationError(
                \"operational sample window may intersect capacity-evicted history\"
            )
        return tuple(
""",
    """        if self._evicted_through is not None and window_start <= self._evicted_through:
            raise OperationalEvidenceMaterializationError(
                \"operational sample window may intersect capacity-evicted history\"
            )
        if self._incomplete_through is not None and window_start <= self._incomplete_through:
            raise OperationalEvidenceMaterializationError(
                \"operational sample window may intersect incomplete runtime history\"
            )
        return tuple(
""",
)

# Shared best-effort local recorder helper.
helper = Path(
    "packages/gateway-core/src/governed_llm_gateway_core/application/operational_recording.py"
)
if helper.exists():
    raise SystemExit(f"{helper}: file already exists")
helper.write_text(
    '''\"\"\"Best-effort process-local recording for operational provider-attempt evidence.\"\"\"\n\nfrom datetime import UTC, datetime\n\nfrom governed_llm_gateway_contracts import GatewayRequest\n\nfrom .operational_evidence import (\n    OperationalAttemptRecorder,\n    OperationalAttemptSample,\n    OperationalProviderErrorKind,\n    OperationalSampleOutcome,\n    UtcClock,\n)\nfrom .provider import ProviderError, ProviderErrorCode\n\n\ndef utc_now() -> datetime:\n    \"\"\"Return an offset-aware UTC completion timestamp.\"\"\"\n    return datetime.now(UTC)\n\n\ndef record_operational_attempt_best_effort(\n    recorder: OperationalAttemptRecorder | None,\n    *,\n    utc_clock: UtcClock,\n    request: GatewayRequest,\n    deployment_id: str,\n    attempt_number: int,\n    fallback_index: int,\n    latency_ms: int,\n    provider_error: ProviderError | None = None,\n) -> None:\n    \"\"\"Record one terminal attempt locally without affecting provider execution.\"\"\"\n    if recorder is None:\n        return\n    observed_at: datetime | None = None\n    try:\n        observed_at = utc_clock()\n        error_kind = _provider_error_kind(provider_error)\n        recorder.record(\n            OperationalAttemptSample(\n                observed_at=observed_at,\n                gateway_request_id=request.request_id,\n                runtime_workload=request.workload,\n                deployment_id=deployment_id,\n                attempt_number=attempt_number,\n                fallback_index=fallback_index,\n                outcome=(\n                    OperationalSampleOutcome.PROVIDER_ERROR\n                    if provider_error is not None\n                    else OperationalSampleOutcome.SUCCEEDED\n                ),\n                error_kind=error_kind,\n                latency_ms=latency_ms,\n            )\n        )\n    except Exception:\n        if observed_at is not None:\n            _invalidate_at_best_effort(recorder, observed_at=observed_at)\n\n\ndef invalidate_operational_completeness_best_effort(\n    recorder: OperationalAttemptRecorder | None,\n    *,\n    utc_clock: UtcClock,\n) -> None:\n    \"\"\"Invalidate local completeness without replacing the original execution outcome.\"\"\"\n    if recorder is None:\n        return\n    try:\n        observed_at = utc_clock()\n    except Exception:\n        return\n    _invalidate_at_best_effort(recorder, observed_at=observed_at)\n\n\ndef _invalidate_at_best_effort(\n    recorder: OperationalAttemptRecorder,\n    *,\n    observed_at: datetime,\n) -> None:\n    try:\n        recorder.invalidate_completeness(observed_at=observed_at)\n    except Exception:\n        return\n\n\ndef _provider_error_kind(error: ProviderError | None) -> OperationalProviderErrorKind | None:\n    if error is None:\n        return None\n    if error.code is ProviderErrorCode.RATE_LIMIT:\n        return OperationalProviderErrorKind.RATE_LIMIT\n    if error.code is ProviderErrorCode.TIMEOUT:\n        return OperationalProviderErrorKind.TIMEOUT\n    return OperationalProviderErrorKind.OTHER\n'''
)

# Non-streaming executor imports and constructor.
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/application/resilience.py",
    "from dataclasses import dataclass, replace\n",
    "from dataclasses import dataclass, replace\n",
)
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/application/resilience.py",
    """from .provider import (
""",
    """from .operational_evidence import OperationalAttemptRecorder, UtcClock
from .operational_recording import (
    invalidate_operational_completeness_best_effort,
    record_operational_attempt_best_effort,
    utc_now,
)
from .provider import (
""",
)
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/application/resilience.py",
    """        sleeper: Sleeper = asyncio.sleep,
        observability: Observability | None = None,
    ) -> None:
        \"\"\"Bind health, resolver, retry controls, and optional Phase 9 telemetry.\"\"\"
        self._health = health
        self._resolver = resolver
        self._retry_policy = retry_policy or RetryPolicy()
        self._clock = clock
        self._sleeper = sleeper
        self._observability = observability
""",
    """        sleeper: Sleeper = asyncio.sleep,
        observability: Observability | None = None,
        operational_recorder: OperationalAttemptRecorder | None = None,
        utc_clock: UtcClock = utc_now,
    ) -> None:
        \"\"\"Bind resilience controls plus optional local telemetry/evidence recording.\"\"\"
        self._health = health
        self._resolver = resolver
        self._retry_policy = retry_policy or RetryPolicy()
        self._clock = clock
        self._sleeper = sleeper
        self._observability = observability
        self._operational_recorder = operational_recorder
        self._utc_clock = utc_clock
""",
)
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/application/resilience.py",
    """                    try:
                        response = await provider.generate(provider_request)
                    except ProviderError as exc:
                        latency_ms = _latency_ms(started, self._clock())
                        self._health.record_failure(deployment_id, exc, latency_ms=latency_ms)
""",
    """                    try:
                        response = await provider.generate(provider_request)
                    except asyncio.CancelledError:
                        invalidate_operational_completeness_best_effort(
                            self._operational_recorder,
                            utc_clock=self._utc_clock,
                        )
                        raise
                    except ProviderError as exc:
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
                        self._health.record_failure(deployment_id, exc, latency_ms=latency_ms)
""",
)
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/application/resilience.py",
    """                        if can_retry and retry_delay is not None:
                            retry_delay_after_span = retry_delay
                        else:
                            break
                    else:
                        latency_ms = _latency_ms(started, self._clock())
                        self._health.record_success(deployment_id, latency_ms=latency_ms)
""",
    """                        if can_retry and retry_delay is not None:
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
                        self._health.record_success(deployment_id, latency_ms=latency_ms)
""",
)

# Streaming executor imports and constructor.
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/application/streaming.py",
    """from .provider import (
""",
    """from .operational_evidence import OperationalAttemptRecorder, UtcClock
from .operational_recording import (
    invalidate_operational_completeness_best_effort,
    record_operational_attempt_best_effort,
    utc_now,
)
from .provider import (
""",
)
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/application/streaming.py",
    """        sleeper: Sleeper = asyncio.sleep,
        observability: Observability | None = None,
    ) -> None:
        \"\"\"Bind runtime health, provider resolution, retry controls, and optional telemetry.\"\"\"
        self._health = health
        self._resolver = resolver
        self._retry_policy = retry_policy or RetryPolicy()
        self._clock = clock
        self._sleeper = sleeper
        self._observability = observability
""",
    """        sleeper: Sleeper = asyncio.sleep,
        observability: Observability | None = None,
        operational_recorder: OperationalAttemptRecorder | None = None,
        utc_clock: UtcClock = utc_now,
    ) -> None:
        \"\"\"Bind resilience controls plus optional local telemetry/evidence recording.\"\"\"
        self._health = health
        self._resolver = resolver
        self._retry_policy = retry_policy or RetryPolicy()
        self._clock = clock
        self._sleeper = sleeper
        self._observability = observability
        self._operational_recorder = operational_recorder
        self._utc_clock = utc_clock
""",
)
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/application/streaming.py",
    """                sequence = 0
                started_at = self._clock()
                span_context = (
""",
    """                sequence = 0
                started_at = self._clock()
                provider_attempt_started = False
                attempt_terminal_recorded = False
                span_context = (
""",
)
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/application/streaming.py",
    """                    try:
                        provider_stream = resolved.stream(provider_request)
                        async with aclosing(provider_stream) as events:
""",
    """                    try:
                        provider_attempt_started = True
                        provider_stream = resolved.stream(provider_request)
                        async with aclosing(provider_stream) as events:
""",
)
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/application/streaming.py",
    """                                    latency_ms = _latency_ms(started_at, self._clock())
                                    self._health.record_success(
                                        deployment_id,
                                        latency_ms=latency_ms,
                                    )
""",
    """                                    latency_ms = _latency_ms(started_at, self._clock())
                                    record_operational_attempt_best_effort(
                                        self._operational_recorder,
                                        utc_clock=self._utc_clock,
                                        request=request,
                                        deployment_id=deployment_id,
                                        attempt_number=attempt_number,
                                        fallback_index=len(fallback_sequence) - 1,
                                        latency_ms=latency_ms,
                                    )
                                    attempt_terminal_recorded = True
                                    self._health.record_success(
                                        deployment_id,
                                        latency_ms=latency_ms,
                                    )
""",
)
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/application/streaming.py",
    """                    except asyncio.CancelledError:
                        if span is not None:
                            mark_span_cancelled(span)
                        raise
                    except ProviderError as exc:
                        latency_ms = _latency_ms(started_at, self._clock())
                        self._health.record_failure(deployment_id, exc, latency_ms=latency_ms)
""",
    """                    except asyncio.CancelledError:
                        if provider_attempt_started and not attempt_terminal_recorded:
                            invalidate_operational_completeness_best_effort(
                                self._operational_recorder,
                                utc_clock=self._utc_clock,
                            )
                        if span is not None:
                            mark_span_cancelled(span)
                        raise
                    except GeneratorExit:
                        if provider_attempt_started and not attempt_terminal_recorded:
                            invalidate_operational_completeness_best_effort(
                                self._operational_recorder,
                                utc_clock=self._utc_clock,
                            )
                        raise
                    except ProviderError as exc:
                        latency_ms = _latency_ms(started_at, self._clock())
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
                        attempt_terminal_recorded = True
                        self._health.record_failure(deployment_id, exc, latency_ms=latency_ms)
""",
)
replace_once(
    "packages/gateway-core/src/governed_llm_gateway_core/application/streaming.py",
    """                        else:
                            yield _failed_event(
                                request=request,
                                sequence_number=1,
                                routing=routing,
                                code=exc.code.value,
                                message=\"provider stream failed before output\",
                                retryable=False,
                                partial=False,
                                execution=last_execution,
                            )
                            return

                if retry_delay_after_span is not None:
""",
    """                        else:
                            yield _failed_event(
                                request=request,
                                sequence_number=1,
                                routing=routing,
                                code=exc.code.value,
                                message=\"provider stream failed before output\",
                                retryable=False,
                                partial=False,
                                execution=last_execution,
                            )
                            return
                    except Exception:
                        if provider_attempt_started and not attempt_terminal_recorded:
                            invalidate_operational_completeness_best_effort(
                                self._operational_recorder,
                                utc_clock=self._utc_clock,
                            )
                        raise

                if retry_delay_after_span is not None:
""",
)
