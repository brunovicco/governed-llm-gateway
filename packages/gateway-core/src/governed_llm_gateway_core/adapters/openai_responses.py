"""Native OpenAI Responses API adapter."""

import json
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

_DEFAULT_ENDPOINT = "https://api.openai.com/v1/responses"


class OpenAIResponsesAdapter:
    """Execute native OpenAI Responses requests without provider-specific types escaping."""

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
        transport: JsonTransport | None = None,
    ) -> None:
        """Configure the native Responses endpoint and credential."""
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        self._api_key = api_key
        self._endpoint = endpoint
        self._transport = transport or StdlibJsonTransport()

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate text, structured output, image analysis, or client-side tool calls."""
        require_supported_request_features("openai", request, self.feature_support)
        instructions = "\n\n".join(
            message.content for message in request.messages if message.role is MessageRole.SYSTEM
        )
        input_messages = _openai_input_messages(request)
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
        if request.structured_output is not None:
            _require_openai_strict_schema(
                request.structured_output.schema,
                label="structured output",
            )
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": request.structured_output.name,
                    "strict": True,
                    "schema": dict(request.structured_output.schema),
                }
            }
        if request.tools:
            for tool in request.tools:
                _require_openai_strict_schema(tool.input_schema, label=f"tool {tool.name}")
            payload["tools"] = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": dict(tool.input_schema),
                    "strict": True,
                }
                for tool in request.tools
            ]

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
        tool_calls = _extract_tool_calls(data, request)
        structured_output: object | None = None
        if request.structured_output is not None and not tool_calls:
            if not text:
                raise _invalid_structured_output("openai response did not contain structured text")
            try:
                structured_output = parse_and_validate_structured_output(
                    text,
                    request.structured_output,
                )
            except StructuredOutputValidationError as exc:
                raise _invalid_structured_output(str(exc)) from exc
        if not text and not tool_calls:
            raise ProviderError(
                provider="openai",
                code=ProviderErrorCode.INVALID_RESPONSE,
                message="openai response did not contain output text or tool calls",
                retryable=False,
            )
        usage = _extract_usage(data)
        return ProviderResponse(
            text=text or None,
            usage=usage,
            response_id=_optional_string(data.get("id")),
            finish_reason=_finish_reason(data),
            structured_output=structured_output,
            tool_calls=tool_calls,
        )


def _openai_input_messages(request: ProviderRequest) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    for message in request.messages:
        if message.role is MessageRole.SYSTEM:
            continue
        if not message.images:
            messages.append({"role": message.role.value, "content": message.content})
            continue
        content: list[dict[str, object]] = [{"type": "input_text", "text": message.content}]
        content.extend(
            {"type": "input_image", "image_url": image.url} for image in message.images
        )
        messages.append({"role": message.role.value, "content": content})
    return messages


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


def _extract_tool_calls(
    data: Mapping[str, object],
    request: ProviderRequest,
) -> tuple[ToolCall, ...]:
    output = data.get("output")
    if not isinstance(output, list):
        return ()
    calls: list[ToolCall] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "function_call":
            continue
        call_id = item.get("call_id")
        name = item.get("name")
        arguments = item.get("arguments")
        if (
            not isinstance(call_id, str)
            or not isinstance(name, str)
            or not isinstance(arguments, str)
        ):
            raise _invalid_tool_call("openai function_call contained invalid fields")
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise _invalid_tool_call("openai function_call arguments were not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise _invalid_tool_call("openai function_call arguments must be a JSON object")
        try:
            call = ToolCall(call_id=call_id, name=name, arguments=parsed)
            validate_tool_call(call, request.tools)
        except (ValueError, ToolCallValidationError) as exc:
            raise _invalid_tool_call(str(exc)) from exc
        calls.append(call)
    return tuple(calls)


def _require_openai_strict_schema(schema: Mapping[str, object], *, label: str) -> None:
    """Enforce documented OpenAI strict-mode object requirements before network I/O."""
    _check_openai_schema_node(schema, label=label)


def _check_openai_schema_node(value: object, *, label: str) -> None:
    if isinstance(value, Mapping):
        if value.get("type") == "object":
            properties = value.get("properties", {})
            required = value.get("required")
            if value.get("additionalProperties") is not False:
                raise ProviderError(
                    provider="openai",
                    code=ProviderErrorCode.INVALID_REQUEST,
                    message=f"openai strict {label} schema requires additionalProperties=false",
                    retryable=False,
                )
            if isinstance(properties, Mapping):
                property_names = set(properties)
                required_names = set(required) if isinstance(required, list) else set()
                if property_names != required_names:
                    raise ProviderError(
                        provider="openai",
                        code=ProviderErrorCode.INVALID_REQUEST,
                        message=f"openai strict {label} schema requires every property",
                        retryable=False,
                    )
        for child in value.values():
            _check_openai_schema_node(child, label=label)
    elif isinstance(value, list | tuple):
        for child in value:
            _check_openai_schema_node(child, label=label)


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


def _invalid_structured_output(message: str) -> ProviderError:
    return ProviderError(
        provider="openai",
        code=ProviderErrorCode.INVALID_STRUCTURED_OUTPUT,
        message=message,
        retryable=False,
    )


def _invalid_tool_call(message: str) -> ProviderError:
    return ProviderError(
        provider="openai",
        code=ProviderErrorCode.INVALID_TOOL_CALL,
        message=message,
        retryable=False,
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
