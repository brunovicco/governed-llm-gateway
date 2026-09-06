"""Best-effort process-local recording for operational provider-attempt evidence."""

from datetime import UTC, datetime

from governed_llm_gateway_contracts import GatewayRequest

from .operational_evidence import (
    OperationalAttemptRecorder,
    OperationalAttemptSample,
    OperationalProviderErrorKind,
    OperationalSampleOutcome,
    UtcClock,
)
from .provider import ProviderError, ProviderErrorCode


def utc_now() -> datetime:
    """Return an offset-aware UTC completion timestamp."""
    return datetime.now(UTC)


def record_operational_attempt_best_effort(
    recorder: OperationalAttemptRecorder | None,
    *,
    utc_clock: UtcClock,
    request: GatewayRequest,
    deployment_id: str,
    attempt_number: int,
    fallback_index: int,
    latency_ms: int,
    provider_error: ProviderError | None = None,
) -> None:
    """Record one terminal attempt locally without affecting provider execution."""
    if recorder is None:
        return
    observed_at: datetime | None = None
    try:
        observed_at = utc_clock()
        error_kind = _provider_error_kind(provider_error)
        recorder.record(
            OperationalAttemptSample(
                observed_at=observed_at,
                gateway_request_id=request.request_id,
                runtime_workload=request.workload,
                deployment_id=deployment_id,
                attempt_number=attempt_number,
                fallback_index=fallback_index,
                outcome=(
                    OperationalSampleOutcome.PROVIDER_ERROR
                    if provider_error is not None
                    else OperationalSampleOutcome.SUCCEEDED
                ),
                error_kind=error_kind,
                latency_ms=latency_ms,
            )
        )
    except Exception:
        if observed_at is not None:
            _invalidate_at_best_effort(recorder, observed_at=observed_at)


def invalidate_operational_completeness_best_effort(
    recorder: OperationalAttemptRecorder | None,
    *,
    utc_clock: UtcClock,
) -> None:
    """Invalidate local completeness without replacing the original execution outcome."""
    if recorder is None:
        return
    try:
        observed_at = utc_clock()
    except Exception:
        return
    _invalidate_at_best_effort(recorder, observed_at=observed_at)


def _invalidate_at_best_effort(
    recorder: OperationalAttemptRecorder,
    *,
    observed_at: datetime,
) -> None:
    try:
        recorder.invalidate_completeness(observed_at=observed_at)
    except Exception:
        return


def _provider_error_kind(error: ProviderError | None) -> OperationalProviderErrorKind | None:
    if error is None:
        return None
    if error.code is ProviderErrorCode.RATE_LIMIT:
        return OperationalProviderErrorKind.RATE_LIMIT
    if error.code is ProviderErrorCode.TIMEOUT:
        return OperationalProviderErrorKind.TIMEOUT
    return OperationalProviderErrorKind.OTHER
