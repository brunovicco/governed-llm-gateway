import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field

import pytest
from governed_llm_gateway_contracts import (
    Message,
    MessageRole,
    StructuredOutputSchema,
    ToolDefinition,
)
from governed_llm_gateway_core.adapters.anthropic_streaming import (
    AnthropicMessagesStreamingAdapter,
)
from governed_llm_gateway_core.adapters.gemini_streaming import GeminiStreamingAdapter
from governed_llm_gateway_core.adapters.http_sse import SseEvent, SseStream
from governed_llm_gateway_core.adapters.openai_compatible_streaming import (
    OpenAICompatibleStreamingAdapter,
)
from governed_llm_gateway_core.adapters.openai_responses_streaming import (
    OpenAIResponsesStreamingAdapter,
)
from governed_llm_gateway_core.adapters.streaming_common import (
    open_provider_sse,
    parse_sse_json,
)
from governed_llm_gateway_core.application.provider import (
    ProviderContentDelta,
    ProviderError,
    ProviderErrorCode,
    ProviderRequest,
    ProviderResponseCompleted,
    ProviderResponseStarted,
    ProviderStreamEvent,
    ProviderToolCallArgumentsDelta,
    ProviderToolCallCompleted,
    ProviderToolCallStarted,
    ProviderUsageCompleted,
)


@dataclass
class FakeSseStream:
    events: list[SseEvent]
    status_code: int = 200
    headers: Mapping[str, str] = field(
        default_factory=lambda: {"content-type": "text/event-stream"}
    )
    closed: bool = False

    def __post_init__(self) -> None:
        self._index = 0

    def __aiter__(self) -> AsyncIterator[SseEvent]:
        return self

    async def __anext__(self) -> SseEvent:
        if self._index >= len(self.events):
            raise StopAsyncIteration
        event = self.events[self._index]
        self._index += 1
        return event

    async def aclose(self) -> None:
        self.closed = True


class FakeSseTransport:
    def __init__(self, stream: FakeSseStream) -> None:
        self.stream = stream
        self.calls: list[tuple[str, Mapping[str, str], Mapping[str, object], float]] = []

    async def open_sse(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> SseStream:
        self.calls.append((url, dict(headers), dict(payload), timeout_seconds))
        return self.stream


def _event(payload: Mapping[str, object], event: str | None = None) -> SseEvent:
    return SseEvent(
        event=event,
        data=json.dumps(payload, separators=(",", ":")),
    )


def _request(
    *,
    structured_output: StructuredOutputSchema | None = None,
    tools: tuple[ToolDefinition, ...] = (),
) -> ProviderRequest:
    return ProviderRequest(
        model="model-1",
        messages=(
            Message(role=MessageRole.SYSTEM, content="Be precise."),
            Message(role=MessageRole.USER, content="hello"),
        ),
        max_output_tokens=64,
        timeout_seconds=5.0,
        structured_output=structured_output,
        tools=tools,
    )


def _strict_schema() -> StructuredOutputSchema:
    return StructuredOutputSchema(
        name="answer",
        schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
    )


def _tool() -> ToolDefinition:
    return ToolDefinition(
        name="lookup",
        description="Look up a value",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    )


async def _collect(stream: AsyncIterator[ProviderStreamEvent]) -> list[ProviderStreamEvent]:
    return [event async for event in stream]


def _types(events: list[ProviderStreamEvent]) -> list[type[ProviderStreamEvent]]:
    return [type(event) for event in events]


def test_openai_text_stream_normalizes_lifecycle_and_payload() -> None:
    upstream = FakeSseStream(
        [
            _event({"type": "response.created", "response": {"id": "resp-1"}}),
            _event({"type": "response.output_text.delta", "delta": "hello"}),
            _event(
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp-1",
                        "status": "completed",
                        "usage": {"input_tokens": 5, "output_tokens": 2},
                    },
                }
            ),
        ]
    )
    transport = FakeSseTransport(upstream)
    adapter = OpenAIResponsesStreamingAdapter(api_key="secret", sse_transport=transport)

    events = asyncio.run(_collect(adapter.stream(_request())))

    assert _types(events) == [
        ProviderResponseStarted,
        ProviderContentDelta,
        ProviderUsageCompleted,
        ProviderResponseCompleted,
    ]
    assert events[1].delta == "hello"  # type: ignore[union-attr]
    assert events[2].usage.input_tokens == 5  # type: ignore[union-attr]
    assert upstream.closed is True
    _, headers, payload, timeout = transport.calls[0]
    assert headers["accept"] == "text/event-stream"
    assert payload["stream"] is True
    assert payload["store"] is False
    assert payload["instructions"] == "Be precise."
    assert timeout == 5.0


def test_openai_function_call_is_correlated_and_schema_validated() -> None:
    upstream = FakeSseStream(
        [
            _event({"type": "response.created", "response": {"id": "resp-tool"}}),
            _event(
                {
                    "type": "response.output_item.added",
                    "item": {
                        "type": "function_call",
                        "id": "item-1",
                        "call_id": "call-1",
                        "name": "lookup",
                    },
                }
            ),
            _event(
                {
                    "type": "response.function_call_arguments.delta",
                    "item_id": "item-1",
                    "delta": '{"query":"abc"}',
                }
            ),
            _event(
                {
                    "type": "response.function_call_arguments.done",
                    "item_id": "item-1",
                    "arguments": '{"query":"abc"}',
                }
            ),
            _event(
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp-tool",
                        "status": "completed",
                        "usage": {"input_tokens": 7, "output_tokens": 3},
                    },
                }
            ),
        ]
    )
    adapter = OpenAIResponsesStreamingAdapter(
        api_key="secret",
        sse_transport=FakeSseTransport(upstream),
    )

    events = asyncio.run(_collect(adapter.stream(_request(tools=(_tool(),)))))

    assert _types(events) == [
        ProviderResponseStarted,
        ProviderToolCallStarted,
        ProviderToolCallArgumentsDelta,
        ProviderToolCallCompleted,
        ProviderUsageCompleted,
        ProviderResponseCompleted,
    ]
    completed = events[3]
    assert isinstance(completed, ProviderToolCallCompleted)
    assert completed.call.call_id == "call-1"
    assert completed.call.arguments == {"query": "abc"}


def test_openai_structured_output_is_revalidated_after_streaming() -> None:
    upstream = FakeSseStream(
        [
            _event({"type": "response.created", "response": {"id": "resp-json"}}),
            _event({"type": "response.output_text.delta", "delta": '{"answer":"ok"}'}),
            _event(
                {
                    "type": "response.completed",
                    "response": {
                        "status": "completed",
                        "usage": {"input_tokens": 4, "output_tokens": 4},
                    },
                }
            ),
        ]
    )
    transport = FakeSseTransport(upstream)
    adapter = OpenAIResponsesStreamingAdapter(api_key="secret", sse_transport=transport)

    asyncio.run(_collect(adapter.stream(_request(structured_output=_strict_schema()))))

    payload = transport.calls[0][2]
    text = payload["text"]
    assert isinstance(text, dict)
    assert text["format"]["type"] == "json_schema"


def test_openai_invalid_streamed_structured_output_fails_closed() -> None:
    upstream = FakeSseStream(
        [
            _event({"type": "response.created", "response": {"id": "resp-json"}}),
            _event({"type": "response.output_text.delta", "delta": '{"wrong":1}'}),
            _event(
                {
                    "type": "response.completed",
                    "response": {
                        "status": "completed",
                        "usage": {"input_tokens": 4, "output_tokens": 4},
                    },
                }
            ),
        ]
    )
    adapter = OpenAIResponsesStreamingAdapter(
        api_key="secret",
        sse_transport=FakeSseTransport(upstream),
    )

    with pytest.raises(ProviderError) as captured:
        asyncio.run(_collect(adapter.stream(_request(structured_output=_strict_schema()))))
    assert captured.value.code is ProviderErrorCode.INVALID_STRUCTURED_OUTPUT
    assert upstream.closed is True


def test_anthropic_text_stream_normalizes_usage_and_stop_reason() -> None:
    upstream = FakeSseStream(
        [
            _event(
                {
                    "type": "message_start",
                    "message": {"id": "msg-1", "usage": {"input_tokens": 6}},
                }
            ),
            _event(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": "hello"},
                }
            ),
            _event(
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn"},
                    "usage": {"output_tokens": 2},
                }
            ),
            _event({"type": "message_stop"}),
        ]
    )
    transport = FakeSseTransport(upstream)
    adapter = AnthropicMessagesStreamingAdapter(api_key="secret", sse_transport=transport)

    events = asyncio.run(_collect(adapter.stream(_request())))

    assert _types(events) == [
        ProviderResponseStarted,
        ProviderContentDelta,
        ProviderUsageCompleted,
        ProviderResponseCompleted,
    ]
    assert events[-1].finish_reason == "end_turn"  # type: ignore[union-attr]
    assert upstream.closed is True
    assert transport.calls[0][2]["system"] == "Be precise."


def test_anthropic_tool_arguments_are_completed_only_after_block_stop() -> None:
    upstream = FakeSseStream(
        [
            _event(
                {
                    "type": "message_start",
                    "message": {"id": "msg-tool", "usage": {"input_tokens": 8}},
                }
            ),
            _event(
                {
                    "type": "content_block_start",
                    "index": 1,
                    "content_block": {
                        "type": "tool_use",
                        "id": "call-a",
                        "name": "lookup",
                        "input": {},
                    },
                }
            ),
            _event(
                {
                    "type": "content_block_delta",
                    "index": 1,
                    "delta": {"type": "input_json_delta", "partial_json": '{"query":"abc"}'},
                }
            ),
            _event({"type": "content_block_stop", "index": 1}),
            _event(
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "tool_use"},
                    "usage": {"output_tokens": 3},
                }
            ),
            _event({"type": "message_stop"}),
        ]
    )
    adapter = AnthropicMessagesStreamingAdapter(
        api_key="secret",
        sse_transport=FakeSseTransport(upstream),
    )

    events = asyncio.run(_collect(adapter.stream(_request(tools=(_tool(),)))))

    assert ProviderToolCallStarted in _types(events)
    assert ProviderToolCallArgumentsDelta in _types(events)
    completed = next(event for event in events if isinstance(event, ProviderToolCallCompleted))
    assert completed.call.arguments == {"query": "abc"}


def test_anthropic_overload_is_retryable_and_closes_upstream() -> None:
    upstream = FakeSseStream(
        [
            _event(
                {
                    "type": "error",
                    "error": {"type": "overloaded_error"},
                }
            )
        ]
    )
    adapter = AnthropicMessagesStreamingAdapter(
        api_key="secret",
        sse_transport=FakeSseTransport(upstream),
    )

    with pytest.raises(ProviderError) as captured:
        asyncio.run(_collect(adapter.stream(_request())))
    assert captured.value.code is ProviderErrorCode.UNAVAILABLE
    assert captured.value.retryable is True
    assert upstream.closed is True


def test_gemini_text_stream_normalizes_candidate_and_usage() -> None:
    upstream = FakeSseStream(
        [
            _event(
                {
                    "responseId": "gem-1",
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {"parts": [{"text": "hello"}]},
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 9,
                        "candidatesTokenCount": 2,
                    },
                }
            )
        ]
    )
    transport = FakeSseTransport(upstream)
    adapter = GeminiStreamingAdapter(api_key="secret", sse_transport=transport)

    events = asyncio.run(_collect(adapter.stream(_request())))

    assert _types(events) == [
        ProviderResponseStarted,
        ProviderContentDelta,
        ProviderUsageCompleted,
        ProviderResponseCompleted,
    ]
    assert events[-1].finish_reason == "STOP"  # type: ignore[union-attr]
    url, headers, payload, _ = transport.calls[0]
    assert ":streamGenerateContent?alt=sse" in url
    assert headers["x-goog-api-key"] == "secret"
    assert payload["systemInstruction"] == {"parts": [{"text": "Be precise."}]}


def test_gemini_function_call_requires_real_id_and_validates_tool() -> None:
    upstream = FakeSseStream(
        [
            _event(
                {
                    "responseId": "gem-tool",
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {
                                "parts": [
                                    {
                                        "functionCall": {
                                            "id": "call-g",
                                            "name": "lookup",
                                            "args": {"query": "abc"},
                                        }
                                    }
                                ]
                            },
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 5,
                        "candidatesTokenCount": 3,
                    },
                }
            )
        ]
    )
    adapter = GeminiStreamingAdapter(
        api_key="secret",
        sse_transport=FakeSseTransport(upstream),
    )

    events = asyncio.run(_collect(adapter.stream(_request(tools=(_tool(),)))))

    assert _types(events) == [
        ProviderResponseStarted,
        ProviderToolCallStarted,
        ProviderToolCallArgumentsDelta,
        ProviderToolCallCompleted,
        ProviderUsageCompleted,
        ProviderResponseCompleted,
    ]
    completed = events[3]
    assert isinstance(completed, ProviderToolCallCompleted)
    assert completed.call.call_id == "call-g"


def test_gemini_missing_function_call_id_fails_closed() -> None:
    upstream = FakeSseStream(
        [
            _event(
                {
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {
                                "parts": [
                                    {"functionCall": {"name": "lookup", "args": {"query": "abc"}}}
                                ]
                            },
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 5,
                        "candidatesTokenCount": 3,
                    },
                }
            )
        ]
    )
    adapter = GeminiStreamingAdapter(
        api_key="secret",
        sse_transport=FakeSseTransport(upstream),
    )

    with pytest.raises(ProviderError) as captured:
        asyncio.run(_collect(adapter.stream(_request(tools=(_tool(),)))))
    assert captured.value.code is ProviderErrorCode.INVALID_TOOL_CALL


def test_openai_compatible_streaming_requires_explicit_opt_in() -> None:
    adapter = OpenAICompatibleStreamingAdapter(
        provider="compatible",
        api_key="secret",
        endpoint="https://provider.example/v1/chat/completions",
        sse_transport=FakeSseTransport(FakeSseStream([])),
    )

    with pytest.raises(ProviderError) as captured:
        asyncio.run(_collect(adapter.stream(_request())))
    assert captured.value.code is ProviderErrorCode.INVALID_REQUEST


def test_openai_compatible_text_stream_requires_done_and_final_usage() -> None:
    upstream = FakeSseStream(
        [
            _event(
                {
                    "id": "chat-1",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "delta": {"content": "hello"},
                        }
                    ],
                }
            ),
            _event(
                {
                    "id": "chat-1",
                    "choices": [],
                    "usage": {"prompt_tokens": 4, "completion_tokens": 2},
                }
            ),
            SseEvent(event=None, data="[DONE]"),
        ]
    )
    transport = FakeSseTransport(upstream)
    adapter = OpenAICompatibleStreamingAdapter(
        provider="compatible",
        api_key="secret",
        endpoint="https://provider.example/v1/chat/completions",
        supports_streaming=True,
        supports_stream_usage=True,
        sse_transport=transport,
    )

    events = asyncio.run(_collect(adapter.stream(_request())))

    assert _types(events) == [
        ProviderResponseStarted,
        ProviderContentDelta,
        ProviderUsageCompleted,
        ProviderResponseCompleted,
    ]
    payload = transport.calls[0][2]
    assert payload["stream_options"] == {"include_usage": True}


def test_openai_compatible_tool_deltas_are_assembled_and_validated() -> None:
    upstream = FakeSseStream(
        [
            _event(
                {
                    "id": "chat-tool",
                    "choices": [
                        {
                            "finish_reason": None,
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call-c",
                                        "function": {
                                            "name": "lookup",
                                            "arguments": '{"query":"',
                                        },
                                    }
                                ]
                            },
                        }
                    ],
                }
            ),
            _event(
                {
                    "id": "chat-tool",
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "function": {"arguments": 'abc"}'},
                                    }
                                ]
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 6, "completion_tokens": 3},
                }
            ),
            SseEvent(event=None, data="[DONE]"),
        ]
    )
    adapter = OpenAICompatibleStreamingAdapter(
        provider="compatible",
        api_key="secret",
        endpoint="https://provider.example/v1/chat/completions",
        supports_native_tool_calling=True,
        supports_streaming=True,
        supports_stream_usage=True,
        sse_transport=FakeSseTransport(upstream),
    )

    events = asyncio.run(_collect(adapter.stream(_request(tools=(_tool(),)))))

    assert ProviderToolCallStarted in _types(events)
    assert _types(events).count(ProviderToolCallArgumentsDelta) == 2
    completed = next(event for event in events if isinstance(event, ProviderToolCallCompleted))
    assert completed.call.arguments == {"query": "abc"}


def test_open_provider_sse_normalizes_non_success_and_closes_stream() -> None:
    upstream = FakeSseStream([], status_code=429, headers={"retry-after": "1"})
    transport = FakeSseTransport(upstream)

    with pytest.raises(ProviderError) as captured:
        asyncio.run(
            open_provider_sse(
                provider="example",
                transport=transport,
                url="https://provider.example/stream",
                headers={"authorization": "secret"},
                payload={"stream": True},
                timeout_seconds=3.0,
            )
        )
    assert captured.value.code is ProviderErrorCode.RATE_LIMIT
    assert captured.value.retryable is True
    assert upstream.closed is True


def test_parse_sse_json_rejects_non_object_and_malformed_data() -> None:
    with pytest.raises(ProviderError):
        parse_sse_json("example", SseEvent(event=None, data="[]"))
    with pytest.raises(ProviderError):
        parse_sse_json("example", SseEvent(event=None, data="{"))
