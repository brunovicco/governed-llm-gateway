"""Native Anthropic Messages API adapter."""

from collections.abc import Mapping

from governed_llm_gateway_contracts import MessageRole, ToolCall

from governed_llm_gateway_core.adapters.http_json import (
    JsonTransport,
    StdlibJsonTransport,
    TransportFailure,
)
from governed_llm_gateway_core.adapters.provider_common import (
    normalize_transport_failure,
    require_non_negative_int,
    require_success_payload,
    require_supported_request_features,
)
from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderFeatureSupport,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)
from governed_llm_gateway_core.domain.structured import (
    StructuredOutputValidationError,
    ToolCallValidationError,
    parse_and_validate_structured_output,
    validate_tool_call,
)

_DEFAULT_ENDPOINT = "https://api.anthropic.com/v1/messages"
_DEFAULT_API_VERSION = "2023-06-01"


class AnthropicMessagesAdapter:
    """Execute native Anthropic Messages requests without leaking provider response types."""

    feature_support = ProviderFeatureSupport(
        native_structured_output=True,
        native_tool_calling=True,
        native_image_input=True,
    )

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
        """Generate text, image analysis, structured output, or client-side tool calls."""
        require_supported_request_features("anthropic", request, self.feature_support)
        system = "\n\n".join(
            message.content for message in request.messages if message.role is MessageRole.SYSTEM
        )
        messages = _anthropic_messages(request)
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
        if request.structured_output is not None:
            payload["output_config"] = {
                "format": {
                    "type": "json_schema",
                    "schema": dict(request.structured_output.schema),
                }
            }
        if request.tools:
            payload["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": dict(tool.input_schema),
                    "strict": True,
                }
                for tool in request.tools
            ]

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
        text, tool_calls = _extract_content(data, request)
        structured_output: object | None = None
        if request.structured_output is not None and not tool_calls:
            if not text:
                raise _invalid_structured_output(
                    "anthropic response did not contain structured text"
                )
            try:
                structured_output = parse_and_validate_structured_output(
                    text,
                    request.structured_output,
                )
            except StructuredOutputValidationError as exc:
                raise _invalid_structured_output(str(exc)) from exc
        if not text and not tool_calls:
            raise _invalid_response("anthropic response did not contain text or tool calls")
        return ProviderResponse(
            text=text or None,
            usage=_extract_usage(data),
            response_id=_optional_string(data.get("id")),
            finish_reason=_optional_string(data.get("stop_reason")),
            structured_output=structured_output,
            tool_calls=tool_calls,
        )


def _anthropic_messages(request: ProviderRequest) -> list[dict[str, object]]:
    """Translate provider-neutral messages into native Anthropic content blocks."""
    messages: list[dict[str, object]] = []
    for message in request.messages:
        if message.role is MessageRole.SYSTEM:
            continue
        if not message.images:
            messages.append({"role": message.role.value, "content": message.content})
            continue
        content: list[dict[str, object]] = [
            {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": image.url,
                },
            }
            for image in message.images
        ]
        content.append({"type": "text", "text": message.content})
        messages.append({"role": message.role.value, "content": content})
    return messages


def _extract_content(
    data: Mapping[str, object],
    request: ProviderRequest,
) -> tuple[str, tuple[ToolCall, ...]]:
    content = data.get("content")
    if not isinstance(content, list):
        raise _invalid_response("anthropic response did not contain content")
    text_parts: list[str] = []
    calls: list[ToolCall] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                text_parts.append(text.strip())
        elif block.get("type") == "tool_use":
            call_id = block.get("id")
            name = block.get("name")
            arguments = block.get("input")
            if (
                not isinstance(call_id, str)
                or not isinstance(name, str)
                or not isinstance(arguments, dict)
            ):
                raise _invalid_tool_call("anthropic tool_use contained invalid fields")
            try:
                call = ToolCall(call_id=call_id, name=name, arguments=arguments)
                validate_tool_call(call, request.tools)
            except (ValueError, ToolCallValidationError) as exc:
                raise _invalid_tool_call(str(exc)) from exc
            calls.append(call)
    return "\n".join(text_parts), tuple(calls)


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


def _invalid_structured_output(message: str) -> ProviderError:
    return ProviderError(
        provider="anthropic",
        code=ProviderErrorCode.INVALID_STRUCTURED_OUTPUT,
        message=message,
        retryable=False,
    )


def _invalid_tool_call(message: str) -> ProviderError:
    return ProviderError(
        provider="anthropic",
        code=ProviderErrorCode.INVALID_TOOL_CALL,
        message=message,
        retryable=False,
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
