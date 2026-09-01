"""Streaming variant of the native OpenAI Responses API adapter."""

import json
from collections.abc import AsyncGenerator
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
    ProviderUsageCompleted,
)
from governed_llm_gateway_core.domain.structured import (
    StructuredOutputValidationError,
    ToolCallValidationError,
    parse_and_validate_structured_output,
    validate_tool_call,
)

from .http_json import JsonTransport, TransportFailure
from .http_sse import HttpxSseTransport, SseTransport
from .openai_responses import OpenAIResponsesAdapter, _require_openai_strict_schema
from .provider_common import normalize_transport_failure
from .streaming_common import (
    in_stream_unavailable,
    open_provider_sse,
    parse_sse_json,
    provider_usage,
)


@dataclass(slots=True)
class _ToolState:
    call_id: str
    name: str
    arguments: str = ""


class OpenAIResponsesStreamingAdapter(OpenAIResponsesAdapter):
    """OpenAI Responses adapter with normalized cancel-safe SSE streaming."""

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
        endpoint: str = "https://api.openai.com/v1/responses",
        transport: JsonTransport | None = None,
        sse_transport: SseTransport | None = None,
    ) -> None:
        """Configure native OpenAI Responses streaming and transport boundaries."""
        super().__init__(api_key=api_key, endpoint=endpoint, transport=transport)
        self._sse_transport = sse_transport or HttpxSseTransport()

    async def stream(self, request: ProviderRequest) -> AsyncGenerator[ProviderStreamEvent]:
        """Yield provider-neutral Responses events and close the upstream stream on cancellation."""
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
            "stream": True,
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

        stream = await open_provider_sse(
            provider="openai",
            transport=self._sse_transport,
            url=self._endpoint,
            headers={
                "authorization": f"Bearer {self._api_key}",
                "accept": "text/event-stream",
                "content-type": "application/json",
            },
            payload=payload,
            timeout_seconds=request.timeout_seconds,
        )

        response_id: str | None = None
        finish_reason: str | None = None
        text_parts: list[str] = []
        tool_states: dict[str, _ToolState] = {}
        completed_calls: list[ToolCall] = []
        semantic_output = False
        terminal = False
        usage_emitted = False

        try:
            async for raw_event in stream:
                data = parse_sse_json("openai", raw_event)
                event_type = data.get("type")
                if not isinstance(event_type, str):
                    event_type = raw_event.event

                if event_type == "response.created":
                    response = data.get("response")
                    if isinstance(response, dict):
                        candidate_id = response.get("id")
                        if isinstance(candidate_id, str) and candidate_id:
                            response_id = candidate_id
                    yield ProviderResponseStarted(response_id=response_id)
                    continue

                if event_type == "response.output_text.delta":
                    delta = data.get("delta")
                    if not isinstance(delta, str) or not delta:
                        raise _invalid_response("openai output_text delta was invalid")
                    semantic_output = True
                    text_parts.append(delta)
                    yield ProviderContentDelta(delta=delta)
                    continue

                if event_type == "response.output_item.added":
                    item = data.get("item")
                    if not isinstance(item, dict) or item.get("type") != "function_call":
                        continue
                    item_id = item.get("id")
                    call_id = item.get("call_id")
                    name = item.get("name")
                    if not isinstance(item_id, str) or not item_id:
                        raise _invalid_tool_call("openai function call item id was invalid")
                    if not isinstance(call_id, str) or not call_id:
                        raise _invalid_tool_call("openai function call correlation id was invalid")
                    if not isinstance(name, str) or not name:
                        raise _invalid_tool_call("openai function call name was invalid")
                    if item_id in tool_states:
                        raise _invalid_tool_call("openai repeated a function-call item id")
                    tool_states[item_id] = _ToolState(call_id=call_id, name=name)
                    semantic_output = True
                    yield ProviderToolCallStarted(call_id=call_id, name=name)
                    continue

                if event_type == "response.function_call_arguments.delta":
                    item_id = data.get("item_id")
                    delta = data.get("delta")
                    if not isinstance(item_id, str) or not isinstance(delta, str) or not delta:
                        raise _invalid_tool_call("openai function-call argument delta was invalid")
                    state = tool_states.get(item_id)
                    if state is None:
                        raise _invalid_tool_call(
                            "openai argument delta preceded function-call identity"
                        )
                    semantic_output = True
                    state.arguments += delta
                    yield ProviderToolCallArgumentsDelta(call_id=state.call_id, delta=delta)
                    continue

                if event_type == "response.function_call_arguments.done":
                    item_id = data.get("item_id")
                    arguments = data.get("arguments")
                    if not isinstance(item_id, str) or not isinstance(arguments, str):
                        raise _invalid_tool_call("openai function-call completion was invalid")
                    state = tool_states.get(item_id)
                    if state is None:
                        raise _invalid_tool_call(
                            "openai function-call completion lacked start identity"
                        )
                    try:
                        parsed = json.loads(arguments)
                    except json.JSONDecodeError as exc:
                        raise _invalid_tool_call(
                            "openai function-call arguments were not valid JSON"
                        ) from exc
                    if not isinstance(parsed, dict):
                        raise _invalid_tool_call("openai function-call arguments must be an object")
                    try:
                        call = ToolCall(call_id=state.call_id, name=state.name, arguments=parsed)
                        validate_tool_call(call, request.tools)
                    except (ValueError, ToolCallValidationError) as exc:
                        raise _invalid_tool_call(str(exc)) from exc
                    completed_calls.append(call)
                    semantic_output = True
                    yield ProviderToolCallCompleted(call=call)
                    continue

                if event_type == "response.failed" or event_type == "error":
                    raise in_stream_unavailable(
                        "openai",
                        message="openai stream terminated with a provider-side error",
                    )

                if event_type == "response.completed":
                    response = data.get("response")
                    if not isinstance(response, dict):
                        raise _invalid_response(
                            "openai response.completed lacked response metadata"
                        )
                    candidate_id = response.get("id")
                    if isinstance(candidate_id, str) and candidate_id:
                        response_id = candidate_id
                    status = response.get("status")
                    if isinstance(status, str) and status:
                        finish_reason = status
                    if not semantic_output:
                        raise _invalid_response("openai stream completed without semantic output")
                    if request.structured_output is not None and not completed_calls:
                        try:
                            parse_and_validate_structured_output(
                                "".join(text_parts),
                                request.structured_output,
                            )
                        except StructuredOutputValidationError as exc:
                            raise ProviderError(
                                provider="openai",
                                code=ProviderErrorCode.INVALID_STRUCTURED_OUTPUT,
                                message=str(exc),
                                retryable=False,
                            ) from exc
                    usage = response.get("usage")
                    if not isinstance(usage, dict):
                        raise _invalid_response("openai stream completed without usage metadata")
                    yield ProviderUsageCompleted(
                        usage=provider_usage(
                            "openai",
                            usage,
                            input_field="input_tokens",
                            output_field="output_tokens",
                        )
                    )
                    usage_emitted = True
                    yield ProviderResponseCompleted(
                        response_id=response_id,
                        finish_reason=finish_reason,
                    )
                    terminal = True
                    break
        except TransportFailure as exc:
            raise normalize_transport_failure("openai", exc) from exc
        finally:
            await stream.aclose()

        if not terminal:
            raise _invalid_response("openai stream ended without response.completed")
        if not usage_emitted:
            raise _invalid_response("openai stream ended without final usage")


def _invalid_response(message: str) -> ProviderError:
    return ProviderError(
        provider="openai",
        code=ProviderErrorCode.INVALID_RESPONSE,
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
