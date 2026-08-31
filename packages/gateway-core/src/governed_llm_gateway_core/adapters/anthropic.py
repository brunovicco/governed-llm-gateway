"""Native Anthropic Messages API adapter for Phase 3 text generation."""

from collections.abc import Mapping

from governed_llm_gateway_contracts import MessageRole

from governed_llm_gateway_core.adapters.http_json import (
    JsonTransport,
    StdlibJsonTransport,
    TransportFailure,
)
from governed_llm_gateway_core.adapters.provider_common import (
    normalize_transport_failure,
    require_non_negative_int,
    require_success_payload,
)
from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)

_DEFAULT_ENDPOINT = "https://api.anthropic.com/v1/messages"
_DEFAULT_API_VERSION = "2023-06-01"


class AnthropicMessagesAdapter:
    """Execute native Anthropic Messages requests without leaking provider response types."""

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = _DEFAULT_ENDPOINT,
        api_version: str = _DEFAULT_API_VERSION,
        transport: JsonTransport | None = None,
    ) -> None:
        """Configure the native Anthropic Messages endpoint and credential."""
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        if not api_version.strip():
            raise ValueError("api_version must not be empty")
        self._api_key = api_key
        self._endpoint = endpoint
        self._api_version = api_version
        self._transport = transport or StdlibJsonTransport()

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate one text response through the native Messages endpoint."""
        system = "\n\n".join(
            message.content for message in request.messages if message.role is MessageRole.SYSTEM
        )
        messages = [
            {"role": message.role.value, "content": message.content}
            for message in request.messages
            if message.role is not MessageRole.SYSTEM
        ]
        if not messages:
            raise ProviderError(
                provider="anthropic",
                code=ProviderErrorCode.INVALID_REQUEST,
                message="anthropic request requires at least one non-system message",
                retryable=False,
            )

        payload: dict[str, object] = {
            "model": request.model,
            "max_tokens": request.max_output_tokens,
            "messages": messages,
        }
        if system:
            payload["system"] = system

        try:
            response = await self._transport.post_json(
                url=self._endpoint,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": self._api_version,
                    "content-type": "application/json",
                },
                payload=payload,
                timeout_seconds=request.timeout_seconds,
            )
        except TransportFailure as exc:
            raise normalize_transport_failure("anthropic", exc) from exc

        data = require_success_payload("anthropic", response)
        return ProviderResponse(
            text=_extract_text(data),
            usage=_extract_usage(data),
            response_id=_optional_string(data.get("id")),
            finish_reason=_optional_string(data.get("stop_reason")),
        )


def _extract_text(data: Mapping[str, object]) -> str:
    content = data.get("content")
    if not isinstance(content, list):
        raise _invalid_response("anthropic response did not contain content")
    text_parts = [
        block["text"].strip()
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
        and block["text"].strip()
    ]
    if not text_parts:
        raise _invalid_response("anthropic response did not contain text")
    return "\n".join(text_parts)


def _extract_usage(data: Mapping[str, object]) -> ProviderUsage:
    usage = data.get("usage")
    if usage is None:
        return ProviderUsage()
    if not isinstance(usage, dict):
        raise _invalid_response("anthropic response contained invalid usage metadata")
    return ProviderUsage(
        input_tokens=require_non_negative_int(
            usage.get("input_tokens", 0), provider="anthropic", field="input_tokens"
        ),
        output_tokens=require_non_negative_int(
            usage.get("output_tokens", 0), provider="anthropic", field="output_tokens"
        ),
    )


def _invalid_response(message: str) -> ProviderError:
    return ProviderError(
        provider="anthropic",
        code=ProviderErrorCode.INVALID_RESPONSE,
        message=message,
        retryable=False,
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
