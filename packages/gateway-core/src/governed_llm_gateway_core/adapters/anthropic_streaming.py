"""Streaming variant of the native Anthropic Messages API adapter."""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

from governed_llm_gateway_contracts import MessageRole, ToolCall

from governed_llm_gateway_core.application.provider import (
    ProviderContentDelta,
    ProviderError,
    ProviderErrorCode,
    ProviderFeatureSupport,
    ProviderRequest,
    ProviderResponseCompleted,
    ProviderResponseStarted,
    ProviderStreamEvent,
    ProviderToolCallArgumentsDelta,
    ProviderToolCallCompleted,
    ProviderToolCallStarted,
    ProviderUsage,
    ProviderUsageCompleted,
)
from governed_llm_gateway_core.domain.structured import (
    StructuredOutputValidationError,
    ToolCallValidationError,
    parse_and_validate_structured_output,
    validate_tool_call,
)

from .anthropic import AnthropicMessagesAdapter
from .http_json import JsonTransport, TransportFailure
from .http_sse import HttpxSseTransport, SseTransport
from .provider_common import (
    normalize_transport_failure,
    require_non_negative_int,
    require_supported_request_features,
)
from .streaming_common import open_provider_sse, parse_sse_json


@dataclass(slots=True)
class _ToolState:
    call_id: str
    name: str
    arguments: str = ""


class AnthropicMessagesStreamingAdapter(AnthropicMessagesAdapter):
    """Anthropic Messages adapter with normalized cancel-safe SSE streaming."""

    feature_support = ProviderFeatureSupport(
        native_structured_output=True,
        native_tool_calling=True,
        native_streaming=True,
        streaming_usage=True,
    )

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "https://api.anthropic.com/v1/messages",
        api_version: str = "2023-06-01",
        transport: JsonTransport | None = None,
        sse_transport: SseTransport | None = None,
    ) -> None:
        """Configure native Anthropic streaming with an injectable SSE transport."""
        super().__init__(
            api_key=api_key,
            endpoint=endpoint,
            api_version=api_version,
            transport=transport,
        )
        self._sse_transport = sse_transport or HttpxSseTransport()

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        """Yield normalized Messages events and close upstream resources on cancellation."""
        require_supported_request_features("anthropic", request, self.feature_support)
        system = "\n\n".join(
            message.content for message in request.messages if message.role is MessageRole.SYSTEM
        )
        messages = [
            {"role": message.role.value, "content": message.content}
            for message in request.messages
            if message.role is not MessageRole.SYSTEM
        ]
        if not messages:
            raise _invalid_request("anthropic request requires at least one non-system message")

        payload: dict[str, object] = {
            "model": request.model,
            "max_tokens": request.max_output_tokens,
            "messages": messages,
            "stream": True,
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

        upstream = await open_provider_sse(
            provider="anthropic",
            transport=self._sse_transport,
            url=self._endpoint,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": self._api_version,
                "accept": "text/event-stream",
                "content-type": "application/json",
            },
            payload=payload,
            timeout_seconds=request.timeout_seconds,
        )

        response_id: str | None = None
        finish_reason: str | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        text_parts: list[str] = []
        tools_by_index: dict[int, _ToolState] = {}
        completed_calls: list[ToolCall] = []
        semantic_output = False
        terminal = False

        try:
            async for raw_event in upstream:
                data = parse_sse_json("anthropic", raw_event)
                event_type = data.get("type")
                if not isinstance(event_type, str):
                    event_type = raw_event.event

                if event_type == "ping":
                    continue

                if event_type == "message_start":
                    message = data.get("message")
                    if not isinstance(message, dict):
                        raise _invalid_response("anthropic message_start lacked message metadata")
                    candidate_id = message.get("id")
                    if isinstance(candidate_id, str) and candidate_id:
                        response_id = candidate_id
                    usage = message.get("usage")
                    if isinstance(usage, dict) and "input_tokens" in usage:
                        input_tokens = require_non_negative_int(
                            usage.get("input_tokens"),
                            provider="anthropic",
                            field="input_tokens",
                        )
                    yield ProviderResponseStarted(response_id=response_id)
                    continue

                if event_type == "content_block_start":
                    index = data.get("index")
                    block = data.get("content_block")
                    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
                        raise _invalid_response("anthropic content block index was invalid")
                    if not isinstance(block, dict):
                        raise _invalid_response("anthropic content block was invalid")
                    block_type = block.get("type")
                    if block_type == "tool_use":
                        call_id = block.get("id")
                        name = block.get("name")
                        initial_input = block.get("input", {})
                        if (
                            not isinstance(call_id, str)
                            or not call_id
                            or not isinstance(name, str)
                            or not name
                            or not isinstance(initial_input, dict)
                        ):
                            raise _invalid_tool_call("anthropic tool_use start was invalid")
                        if index in tools_by_index:
                            raise _invalid_tool_call("anthropic repeated a tool-use block index")
                        initial = (
                            ""
                            if not initial_input
                            else json.dumps(
                                initial_input,
                                sort_keys=True,
                                separators=(",", ":"),
                            )
                        )
                        tools_by_index[index] = _ToolState(
                            call_id=call_id,
                            name=name,
                            arguments=initial,
                        )
                        semantic_output = True
                        yield ProviderToolCallStarted(call_id=call_id, name=name)
                    elif block_type in {"server_tool_use", "web_search_tool_result"}:
                        raise _invalid_response(
                            "anthropic emitted undeclared provider-side tool activity"
                        )
                    continue

                if event_type == "content_block_delta":
                    index = data.get("index")
                    delta = data.get("delta")
                    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
                        raise _invalid_response("anthropic content delta index was invalid")
                    if not isinstance(delta, dict):
                        raise _invalid_response("anthropic content delta was invalid")
                    delta_type = delta.get("type")
                    if delta_type == "text_delta":
                        text = delta.get("text")
                        if not isinstance(text, str) or not text:
                            raise _invalid_response("anthropic text delta was invalid")
                        semantic_output = True
                        text_parts.append(text)
                        yield ProviderContentDelta(delta=text)
                    elif delta_type == "input_json_delta":
                        partial_json = delta.get("partial_json")
                        state = tools_by_index.get(index)
                        if state is None:
                            raise _invalid_tool_call(
                                "anthropic tool arguments preceded tool identity"
                            )
                        if not isinstance(partial_json, str):
                            raise _invalid_tool_call("anthropic tool argument delta was invalid")
                        if partial_json:
                            semantic_output = True
                            state.arguments += partial_json
                            yield ProviderToolCallArgumentsDelta(
                                call_id=state.call_id,
                                delta=partial_json,
                            )
                    continue

                if event_type == "content_block_stop":
                    index = data.get("index")
                    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
                        raise _invalid_response("anthropic content block stop index was invalid")
                    state = tools_by_index.pop(index, None)
                    if state is None:
                        continue
                    raw_arguments = state.arguments or "{}"
                    try:
                        arguments = json.loads(raw_arguments)
                    except json.JSONDecodeError as exc:
                        raise _invalid_tool_call(
                            "anthropic tool arguments were not valid JSON"
                        ) from exc
                    if not isinstance(arguments, dict):
                        raise _invalid_tool_call("anthropic tool arguments must be an object")
                    try:
                        call = ToolCall(
                            call_id=state.call_id,
                            name=state.name,
                            arguments=arguments,
                        )
                        validate_tool_call(call, request.tools)
                    except (ValueError, ToolCallValidationError) as exc:
                        raise _invalid_tool_call(str(exc)) from exc
                    completed_calls.append(call)
                    semantic_output = True
                    yield ProviderToolCallCompleted(call=call)
                    continue

                if event_type == "message_delta":
                    delta = data.get("delta")
                    if isinstance(delta, dict):
                        stop_reason = delta.get("stop_reason")
                        if isinstance(stop_reason, str) and stop_reason:
                            finish_reason = stop_reason
                    usage = data.get("usage")
                    if isinstance(usage, dict):
                        if "input_tokens" in usage:
                            input_tokens = require_non_negative_int(
                                usage.get("input_tokens"),
                                provider="anthropic",
                                field="input_tokens",
                            )
                        if "output_tokens" in usage:
                            output_tokens = require_non_negative_int(
                                usage.get("output_tokens"),
                                provider="anthropic",
                                field="output_tokens",
                            )
                    continue

                if event_type == "error":
                    error = data.get("error")
                    error_type = error.get("type") if isinstance(error, dict) else None
                    if error_type == "overloaded_error":
                        raise ProviderError(
                            provider="anthropic",
                            code=ProviderErrorCode.UNAVAILABLE,
                            message="anthropic stream is temporarily overloaded",
                            retryable=True,
                        )
                    raise _invalid_response("anthropic stream terminated with an error event")

                if event_type == "message_stop":
                    if tools_by_index:
                        raise _invalid_tool_call(
                            "anthropic stream ended with incomplete tool arguments"
                        )
                    if not semantic_output:
                        raise _invalid_response(
                            "anthropic stream completed without semantic output"
                        )
                    if request.structured_output is not None and not completed_calls:
                        try:
                            parse_and_validate_structured_output(
                                "".join(text_parts),
                                request.structured_output,
                            )
                        except StructuredOutputValidationError as exc:
                            raise ProviderError(
                                provider="anthropic",
                                code=ProviderErrorCode.INVALID_STRUCTURED_OUTPUT,
                                message=str(exc),
                                retryable=False,
                            ) from exc
                    if input_tokens is None or output_tokens is None:
                        raise _invalid_response("anthropic stream ended without final usage")
                    yield ProviderUsageCompleted(
                        usage=ProviderUsage(
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                        )
                    )
                    yield ProviderResponseCompleted(
                        response_id=response_id,
                        finish_reason=finish_reason,
                    )
                    terminal = True
                    break
                # Unknown future event types are ignored according to Anthropic's versioning policy.
        except TransportFailure as exc:
            raise normalize_transport_failure("anthropic", exc) from exc
        finally:
            await upstream.aclose()

        if not terminal:
            raise _invalid_response("anthropic stream ended without message_stop")


def _invalid_request(message: str) -> ProviderError:
    return ProviderError(
        provider="anthropic",
        code=ProviderErrorCode.INVALID_REQUEST,
        message=message,
        retryable=False,
    )


def _invalid_response(message: str) -> ProviderError:
    return ProviderError(
        provider="anthropic",
        code=ProviderErrorCode.INVALID_RESPONSE,
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
