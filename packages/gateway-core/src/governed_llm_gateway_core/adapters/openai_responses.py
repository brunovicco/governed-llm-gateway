"""Native OpenAI Responses API adapter for bounded Phase 3 text generation."""

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

_DEFAULT_ENDPOINT = "https://api.openai.com/v1/responses"


class OpenAIResponsesAdapter:
    """Execute native OpenAI Responses requests without provider-specific types escaping."""

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = _DEFAULT_ENDPOINT,
        transport: JsonTransport | None = None,
    ) -> None:
        """Configure the native Responses endpoint and credential."""
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        self._api_key = api_key
        self._endpoint = endpoint
        self._transport = transport or StdlibJsonTransport()

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate one text response through the native Responses endpoint."""
        instructions = "\n\n".join(
            message.content for message in request.messages if message.role is MessageRole.SYSTEM
        )
        input_messages = [
            {"role": message.role.value, "content": message.content}
            for message in request.messages
            if message.role is not MessageRole.SYSTEM
        ]
        if not input_messages:
            raise ProviderError(
                provider="openai",
                code=ProviderErrorCode.INVALID_REQUEST,
                message="openai request requires at least one non-system message",
                retryable=False,
            )

        payload: dict[str, object] = {
            "model": request.model,
            "store": False,
            "max_output_tokens": request.max_output_tokens,
            "input": input_messages,
        }
        if instructions:
            payload["instructions"] = instructions

        try:
            response = await self._transport.post_json(
                url=self._endpoint,
                headers={
                    "authorization": f"Bearer {self._api_key}",
                    "content-type": "application/json",
                },
                payload=payload,
                timeout_seconds=request.timeout_seconds,
            )
        except TransportFailure as exc:
            raise normalize_transport_failure("openai", exc) from exc

        data = require_success_payload("openai", response)
        text = _extract_text(data)
        if not text:
            raise ProviderError(
                provider="openai",
                code=ProviderErrorCode.INVALID_RESPONSE,
                message="openai response did not contain output text",
                retryable=False,
            )
        usage = _extract_usage(data)
        return ProviderResponse(
            text=text,
            usage=usage,
            response_id=_optional_string(data.get("id")),
            finish_reason=_finish_reason(data),
        )


def _extract_text(data: Mapping[str, object]) -> str:
    output = data.get("output")
    if not isinstance(output, list):
        return ""
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "output_text":
                continue
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n".join(parts)


def _extract_usage(data: Mapping[str, object]) -> ProviderUsage:
    usage = data.get("usage")
    if usage is None:
        return ProviderUsage()
    if not isinstance(usage, dict):
        raise ProviderError(
            provider="openai",
            code=ProviderErrorCode.INVALID_RESPONSE,
            message="openai response contained invalid usage metadata",
            retryable=False,
        )
    return ProviderUsage(
        input_tokens=require_non_negative_int(
            usage.get("input_tokens", 0), provider="openai", field="input_tokens"
        ),
        output_tokens=require_non_negative_int(
            usage.get("output_tokens", 0), provider="openai", field="output_tokens"
        ),
    )


def _finish_reason(data: Mapping[str, object]) -> str | None:
    status = data.get("status")
    if status == "incomplete":
        details = data.get("incomplete_details")
        if isinstance(details, dict):
            reason = details.get("reason")
            if isinstance(reason, str) and reason:
                return reason
    return _optional_string(status)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
