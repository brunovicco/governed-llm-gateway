"""Shared provider-adapter normalization helpers."""

from collections.abc import Mapping

from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderFeatureSupport,
    ProviderRequest,
)

from .http_json import JsonHttpResponse, TransportFailure, TransportFailureKind


def require_supported_request_features(
    provider: str,
    request: ProviderRequest,
    support: ProviderFeatureSupport,
) -> None:
    """Reject provider-neutral features this API family cannot translate safely."""
    if request.has_image_input and not support.native_image_input:
        raise ProviderError(
            provider=provider,
            code=ProviderErrorCode.INVALID_REQUEST,
            message=f"{provider} API family does not support provider-neutral image input",
            retryable=False,
        )


def require_success_payload(provider: str, response: JsonHttpResponse) -> Mapping[str, object]:
    """Return a successful JSON payload or raise a sanitized typed provider error."""
    if 200 <= response.status_code < 300:
        if response.payload is None:
            raise ProviderError(
                provider=provider,
                code=ProviderErrorCode.INVALID_RESPONSE,
                message=f"{provider} returned an empty successful response",
                retryable=False,
                status_code=response.status_code,
            )
        return response.payload

    status = response.status_code
    retry_after = _retry_after_seconds(response.headers.get("retry-after"))
    if status in {401, 403}:
        code = ProviderErrorCode.AUTHENTICATION
        retryable = False
    elif status == 429:
        code = ProviderErrorCode.RATE_LIMIT
        retryable = True
    elif status in {408, 504}:
        code = ProviderErrorCode.TIMEOUT
        retryable = True
    elif 400 <= status < 500:
        code = ProviderErrorCode.INVALID_REQUEST
        retryable = False
    elif status >= 500:
        code = ProviderErrorCode.UNAVAILABLE
        retryable = True
    else:
        code = ProviderErrorCode.UNKNOWN
        retryable = False

    raise ProviderError(
        provider=provider,
        code=code,
        message=f"{provider} request failed with HTTP {status}",
        retryable=retryable,
        status_code=status,
        retry_after_seconds=retry_after,
    )


def normalize_transport_failure(provider: str, exc: TransportFailure) -> ProviderError:
    """Translate transport-only failures without exposing URLs, bodies, or credentials."""
    if exc.kind is TransportFailureKind.TIMEOUT:
        return ProviderError(
            provider=provider,
            code=ProviderErrorCode.TIMEOUT,
            message=f"{provider} request timed out",
            retryable=True,
        )
    if exc.kind is TransportFailureKind.INVALID_RESPONSE:
        return ProviderError(
            provider=provider,
            code=ProviderErrorCode.INVALID_RESPONSE,
            message=f"{provider} returned an invalid response",
            retryable=False,
        )
    return ProviderError(
        provider=provider,
        code=ProviderErrorCode.TRANSPORT,
        message=f"{provider} transport failed",
        retryable=True,
    )


def require_non_negative_int(value: object, *, provider: str, field: str) -> int:
    """Validate provider usage counters without coercing malformed response values."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderError(
            provider=provider,
            code=ProviderErrorCode.INVALID_RESPONSE,
            message=f"{provider} returned invalid {field}",
            retryable=False,
        )
    return value


def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None
