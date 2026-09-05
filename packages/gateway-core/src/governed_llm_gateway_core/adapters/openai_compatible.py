"""Explicit OpenAI-compatible chat-completions adapter."""

import json
from collections.abc import Mapping

from governed_llm_gateway_contracts import ToolCall

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


class OpenAICompatibleAdapter:
    """Execute one explicitly configured chat-completions-compatible API family."""

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        endpoint: str,
        max_tokens_field: str = "max_tokens",
        supports_native_structured_output: bool = False,
        supports_native_tool_calling: bool = False,
        transport: JsonTransport | None = None,
    ) -> None:
        """Configure endpoint quirks and opt into only verified native features."""
        if not provider.strip():
            raise ValueError("provider must not be empty")
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        if max_tokens_field not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError("unsupported max_tokens_field")
        self._provider = provider
        self._api_key = api_key
        self._endpoint = endpoint
        self._max_tokens_field = max_tokens_field
        self._transport = transport or StdlibJsonTransport()
        self.feature_support = ProviderFeatureSupport(
            native_structured_output=supports_native_structured_output,
            native_tool_calling=supports_native_tool_calling,
        )

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate through an endpoint whose optional features were explicitly verified."""
        require_supported_request_features(self._provider, request, self.feature_support)
        structured_unsupported = (
            request.structured_output is not None
            and not self.feature_support.native_structured_output
        )
        if structured_unsupported:
            raise self._invalid_request("native structured output is not enabled for this endpoint")
        if request.tools and not self.feature_support.native_tool_calling:
            raise self._invalid_request("native tool calling is not enabled for this endpoint")

        payload: dict[str, object] = {
            "model": request.model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            self._max_tokens_field: request.max_output_tokens,
        }
        if request.structured_output is not None:
            _require_openai_strict_schema(
                request.structured_output.schema,
                label="structured output",
                provider=self._provider,
            )
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.structured_output.name,
                    "strict": True,
                    "schema": dict(request.structured_output.schema),
                },
            }
        if request.tools:
            for tool in request.tools:
                _require_openai_strict_schema(
                    tool.input_schema,
                    label=f"tool {tool.name}",
                    provider=self._provider,
                )
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": dict(tool.input_schema),
                        "strict": True,
                    },
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
            raise normalize_transport_failure(self._provider, exc) from exc

        data = require_success_payload(self._provider, response)
        text, tool_calls, finish_reason = self._extract_choice(data, request)
        structured_output: object | None = None
        if request.structured_output is not None and not tool_calls:
            if not text:
                raise self._invalid_structured_output("response did not contain structured text")
            try:
                structured_output = parse_and_validate_structured_output(
                    text,
                    request.structured_output,
                )
            except StructuredOutputValidationError as exc:
                raise self._invalid_structured_output(str(exc)) from exc
        if not text and not tool_calls:
            raise self._invalid_response("response message did not contain text or tool calls")
        return ProviderResponse(
            text=text or None,
            usage=self._extract_usage(data),
            response_id=_optional_string(data.get("id")),
            finish_reason=finish_reason,
            structured_output=structured_output,
            tool_calls=tool_calls,
        )

    def _extract_choice(
        self,
        data: Mapping[str, object],
        request: ProviderRequest,
    ) -> tuple[str, tuple[ToolCall, ...], str | None]:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise self._invalid_response("response did not contain a valid first choice")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict):
            raise self._invalid_response("response choice did not contain a message")
        content = message.get("content")
        text = content.strip() if isinstance(content, str) and content.strip() else ""
        calls = self._extract_tool_calls(message, request)
        return text, calls, _optional_string(choice.get("finish_reason"))

    def _extract_tool_calls(
        self,
        message: Mapping[str, object],
        request: ProviderRequest,
    ) -> tuple[ToolCall, ...]:
        raw_calls = message.get("tool_calls")
        if raw_calls is None:
            return ()
        if not isinstance(raw_calls, list):
            raise self._invalid_tool_call("tool_calls was not a list")
        calls: list[ToolCall] = []
        for raw in raw_calls:
            if not isinstance(raw, dict):
                raise self._invalid_tool_call("tool call was not an object")
            call_id = raw.get("id")
            function = raw.get("function")
            if not isinstance(call_id, str) or not isinstance(function, dict):
                raise self._invalid_tool_call("tool call contained invalid fields")
            name = function.get("name")
            arguments = function.get("arguments")
            if not isinstance(name, str) or not isinstance(arguments, str):
                raise self._invalid_tool_call("tool function contained invalid fields")
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise self._invalid_tool_call("tool arguments were not valid JSON") from exc
            if not isinstance(parsed, dict):
                raise self._invalid_tool_call("tool arguments must be a JSON object")
            try:
                call = ToolCall(call_id=call_id, name=name, arguments=parsed)
                validate_tool_call(call, request.tools)
            except (ValueError, ToolCallValidationError) as exc:
                raise self._invalid_tool_call(str(exc)) from exc
            calls.append(call)
        return tuple(calls)

    def _extract_usage(self, data: Mapping[str, object]) -> ProviderUsage:
        usage = data.get("usage")
        if usage is None:
            return ProviderUsage()
        if not isinstance(usage, dict):
            raise self._invalid_response("response contained invalid usage metadata")
        return ProviderUsage(
            input_tokens=require_non_negative_int(
                usage.get("prompt_tokens", 0),
                provider=self._provider,
                field="prompt_tokens",
            ),
            output_tokens=require_non_negative_int(
                usage.get("completion_tokens", 0),
                provider=self._provider,
                field="completion_tokens",
            ),
        )

    def _invalid_request(self, detail: str) -> ProviderError:
        return ProviderError(
            provider=self._provider,
            code=ProviderErrorCode.INVALID_REQUEST,
            message=f"{self._provider} {detail}",
            retryable=False,
        )

    def _invalid_response(self, detail: str) -> ProviderError:
        return ProviderError(
            provider=self._provider,
            code=ProviderErrorCode.INVALID_RESPONSE,
            message=f"{self._provider} {detail}",
            retryable=False,
        )

    def _invalid_structured_output(self, detail: str) -> ProviderError:
        return ProviderError(
            provider=self._provider,
            code=ProviderErrorCode.INVALID_STRUCTURED_OUTPUT,
            message=f"{self._provider} {detail}",
            retryable=False,
        )

    def _invalid_tool_call(self, detail: str) -> ProviderError:
        return ProviderError(
            provider=self._provider,
            code=ProviderErrorCode.INVALID_TOOL_CALL,
            message=f"{self._provider} {detail}",
            retryable=False,
        )


def _require_openai_strict_schema(
    schema: Mapping[str, object],
    *,
    label: str,
    provider: str,
) -> None:
    _check_openai_schema_node(schema, label=label, provider=provider)


def _check_openai_schema_node(value: object, *, label: str, provider: str) -> None:
    if isinstance(value, Mapping):
        if value.get("type") == "object":
            properties = value.get("properties", {})
            required = value.get("required")
            if value.get("additionalProperties") is not False:
                raise ProviderError(
                    provider=provider,
                    code=ProviderErrorCode.INVALID_REQUEST,
                    message=f"{provider} strict {label} schema requires additionalProperties=false",
                    retryable=False,
                )
            if isinstance(properties, Mapping):
                property_names = set(properties)
                required_names = set(required) if isinstance(required, list) else set()
                if property_names != required_names:
                    raise ProviderError(
                        provider=provider,
                        code=ProviderErrorCode.INVALID_REQUEST,
                        message=f"{provider} strict {label} schema requires every property",
                        retryable=False,
                    )
        for child in value.values():
            _check_openai_schema_node(child, label=label, provider=provider)
    elif isinstance(value, list | tuple):
        for child in value:
            _check_openai_schema_node(child, label=label, provider=provider)


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
