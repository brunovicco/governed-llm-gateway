"""Shared helpers for provider-native SSE adapters."""

import json
from collections.abc import Mapping

from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderUsage,
)

from .http_json import JsonHttpResponse, TransportFailure
from .http_sse import SseEvent, SseStream, SseTransport
from .provider_common import (
    normalize_transport_failure,
    require_non_negative_int,
    require_success_payload,
)


async def open_provider_sse(
    *,
    provider: str,
    transport: SseTransport,
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, object],
    timeout_seconds: float,
) -> SseStream:
    """Open a provider stream and fail closed on non-success HTTP status."""
    try:
        stream = await transport.open_sse(
            url=url,
            headers=headers,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
    except TransportFailure as exc:
        raise normalize_transport_failure(provider, exc) from exc

    if 200 <= stream.status_code < 300:
        return stream

    try:
        require_success_payload(
            provider,
            JsonHttpResponse(
                status_code=stream.status_code,
                headers=stream.headers,
                payload=None,
            ),
        )
    finally:
        await stream.aclose()

    raise ProviderError(
        provider=provider,
        code=ProviderErrorCode.INVALID_RESPONSE,
        message=f"{provider} stream status normalization returned unexpectedly",
        retryable=False,
    )


def parse_sse_json(provider: str, event: SseEvent) -> Mapping[str, object]:
    """Parse one bounded SSE data payload without retaining raw provider content on failure."""
    try:
        value = json.loads(event.data)
    except json.JSONDecodeError as exc:
        raise ProviderError(
            provider=provider,
            code=ProviderErrorCode.INVALID_RESPONSE,
            message=f"{provider} stream returned invalid JSON",
            retryable=False,
        ) from exc
    if not isinstance(value, dict):
        raise ProviderError(
            provider=provider,
            code=ProviderErrorCode.INVALID_RESPONSE,
            message=f"{provider} stream event must be a JSON object",
            retryable=False,
        )
    return value


def provider_usage(
    provider: str,
    payload: Mapping[str, object],
    *,
    input_field: str,
    output_field: str,
) -> ProviderUsage:
    """Build final provider usage from a mapping with strict non-negative counters."""
    return ProviderUsage(
        input_tokens=require_non_negative_int(
            payload.get(input_field, 0),
            provider=provider,
            field=input_field,
        ),
        output_tokens=require_non_negative_int(
            payload.get(output_field, 0),
            provider=provider,
            field=output_field,
        ),
    )


def in_stream_unavailable(provider: str, *, message: str) -> ProviderError:
    """Normalize a provider-side runtime stream failure without copying raw provider text."""
    return ProviderError(
        provider=provider,
        code=ProviderErrorCode.UNAVAILABLE,
        message=message,
        retryable=True,
    )
