"""Streaming variant for explicitly verified OpenAI-compatible chat-completions endpoints."""

import json
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from dataclasses import dataclass

from governed_llm_gateway_contracts import ToolCall

from governed_llm_gateway_core.application.provider import (
    ProviderContentDelta,
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

from .http_json import JsonTransport, TransportFailure
from .http_sse import HttpxSseTransport, SseTransport
from .openai_compatible import OpenAICompatibleAdapter, _require_openai_strict_schema
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


class OpenAICompatibleStreamingAdapter(OpenAICompatibleAdapter):
    """Stream only from endpoints whose optional compatibility features were verified explicitly."""

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        endpoint: str,
        max_tokens_field: str = "max_tokens",
        supports_native_structured_output: bool = False,
        supports_native_tool_calling: bool = False,
        supports_streaming: bool = False,
        supports_stream_usage: bool = False,
        transport: JsonTransport | None = None,
        sse_transport: SseTransport | None = None,
    ) -> None:
        """Configure only explicitly verified compatible streaming capabilities."""
        super().__init__(
            provider=provider,
            api_key=api_key,
            endpoint=endpoint,
            max_tokens_field=max_tokens_field,
            supports_native_structured_output=supports_native_structured_output,
            supports_native_tool_calling=supports_native_tool_calling,
            transport=transport,
        )
        self.feature_support = ProviderFeatureSupport(
            native_structured_output=supports_native_structured_output,
            native_tool_calling=supports_native_tool_calling,
            native_streaming=supports_streaming,
            streaming_usage=supports_stream_usage,
        )
        self._sse_transport = sse_transport or HttpxSseTransport()

    async def stream(self, request: ProviderRequest) -> AsyncGenerator[ProviderStreamEvent]:
        """Yield normalized chat-completion chunks for an explicitly verified endpoint."""
        require_supported_request_features(self._provider, request, self.feature_support)
        if not self.feature_support.native_streaming:
            raise self._invalid_request("streaming is not enabled for this endpoint")
        if not self.feature_support.streaming_usage:
            raise self._invalid_request(
                "streaming usage finalization is not enabled for this endpoint"
            )
        if (
            request.structured_output is not None
            and not self.feature_support.native_structured_output
        ):
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
            "stream": True,
            "stream_options": {"include_usage": True},
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

        upstream = await open_provider_sse(
            provider=self._provider,
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
        usage: ProviderUsage | None = None
        text_parts: list[str] = []
        tool_states: dict[int, _ToolState] = {}
        semantic_output = False
        started = False
        saw_done = False

        try:
            async for raw_event in upstream:
                if raw_event.data == "[DONE]":
                    saw_done = True
                    break
                data = parse_sse_json(self._provider, raw_event)
                candidate_id = data.get("id")
                if isinstance(candidate_id, str) and candidate_id:
                    response_id = candidate_id
                if not started:
                    started = True
                    yield ProviderResponseStarted(response_id=response_id)

                usage_payload = data.get("usage")
                choices = data.get("choices")
                if usage_payload is not None:
                    if not isinstance(usage_payload, dict):
                        raise self._invalid_response("stream usage metadata was invalid")
                    usage = ProviderUsage(
                        input_tokens=require_non_negative_int(
                            usage_payload.get("prompt_tokens", 0),
                            provider=self._provider,
                            field="prompt_tokens",
                        ),
                        output_tokens=require_non_negative_int(
                            usage_payload.get("completion_tokens", 0),
                            provider=self._provider,
                            field="completion_tokens",
                        ),
                    )
                if choices is None:
                    continue
                if not isinstance(choices, list):
                    raise self._invalid_response("stream choices was not a list")
                for choice in choices:
                    if not isinstance(choice, dict):
                        raise self._invalid_response("stream choice was invalid")
                    reason = choice.get("finish_reason")
                    if isinstance(reason, str) and reason:
                        finish_reason = reason
                    delta = choice.get("delta")
                    if not isinstance(delta, dict):
                        continue
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        semantic_output = True
                        text_parts.append(content)
                        yield ProviderContentDelta(delta=content)
                    raw_tools = delta.get("tool_calls")
                    if raw_tools is None:
                        continue
                    if not isinstance(raw_tools, list):
                        raise self._invalid_tool_call("stream tool_calls was not a list")
                    for raw_tool in raw_tools:
                        if not isinstance(raw_tool, dict):
                            raise self._invalid_tool_call("stream tool-call delta was invalid")
                        async for event in self._tool_delta_events(raw_tool, tool_states):
                            semantic_output = True
                            yield event
        except TransportFailure as exc:
            raise normalize_transport_failure(self._provider, exc) from exc
        finally:
            await upstream.aclose()

        if not saw_done:
            raise self._invalid_response("stream ended without the [DONE] sentinel")
        if not started:
            raise self._invalid_response("stream ended before the first response chunk")
        if not semantic_output:
            raise self._invalid_response("stream completed without semantic output")
        if finish_reason is None:
            raise self._invalid_response("stream ended without a finish reason")

        completed_calls: list[ToolCall] = []
        for index in sorted(tool_states):
            state = tool_states[index]
            try:
                arguments = json.loads(state.arguments or "{}")
            except json.JSONDecodeError as exc:
                raise self._invalid_tool_call("stream tool arguments were not valid JSON") from exc
            if not isinstance(arguments, dict):
                raise self._invalid_tool_call("stream tool arguments must be a JSON object")
            try:
                call = ToolCall(
                    call_id=state.call_id,
                    name=state.name,
                    arguments=arguments,
                )
                validate_tool_call(call, request.tools)
            except (ValueError, ToolCallValidationError) as exc:
                raise self._invalid_tool_call(str(exc)) from exc
            completed_calls.append(call)
            yield ProviderToolCallCompleted(call=call)

        if request.structured_output is not None and not completed_calls:
            try:
                parse_and_validate_structured_output(
                    "".join(text_parts),
                    request.structured_output,
                )
            except StructuredOutputValidationError as exc:
                raise self._invalid_structured_output(str(exc)) from exc
        if usage is None:
            raise self._invalid_response("stream ended without final usage metadata")
        yield ProviderUsageCompleted(usage=usage)
        yield ProviderResponseCompleted(
            response_id=response_id,
            finish_reason=finish_reason,
        )

    async def _tool_delta_events(
        self,
        raw_tool: Mapping[str, object],
        states: dict[int, _ToolState],
    ) -> AsyncIterator[ProviderStreamEvent]:
        index = raw_tool.get("index")
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise self._invalid_tool_call("stream tool-call index was invalid")
        call_id = raw_tool.get("id")
        function = raw_tool.get("function")
        if function is not None and not isinstance(function, dict):
            raise self._invalid_tool_call("stream tool function delta was invalid")
        function = function if isinstance(function, dict) else {}
        name = function.get("name")
        arguments_delta = function.get("arguments")

        state = states.get(index)
        if state is None:
            if not isinstance(call_id, str) or not call_id:
                raise self._invalid_tool_call("stream tool call did not provide a correlation id")
            if not isinstance(name, str) or not name:
                raise self._invalid_tool_call("stream tool call did not provide a function name")
            state = _ToolState(call_id=call_id, name=name)
            states[index] = state
            yield ProviderToolCallStarted(call_id=call_id, name=name)
        else:
            if call_id is not None and call_id != state.call_id:
                raise self._invalid_tool_call("stream tool-call correlation id changed")
            if name is not None and name != state.name:
                raise self._invalid_tool_call("stream tool-call function name changed")

        if arguments_delta is not None:
            if not isinstance(arguments_delta, str):
                raise self._invalid_tool_call("stream tool argument delta was invalid")
            if arguments_delta:
                state.arguments += arguments_delta
                yield ProviderToolCallArgumentsDelta(
                    call_id=state.call_id,
                    delta=arguments_delta,
                )
