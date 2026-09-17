import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import FrozenInstanceError, dataclass, field
from typing import cast

import pytest
from governed_llm_gateway_contracts import Message, MessageRole
from governed_llm_gateway_core.adapters import openai_responses_streaming
from governed_llm_gateway_core.adapters.http_sse import (
    PreparedSseRequest,
    SseEvent,
    SseStream,
    prepare_sse_request,
)
from governed_llm_gateway_core.adapters.openai_responses_input_count import (
    OpenAIResponsesInputCountObservation,
    OpenAIResponsesTextCountProjection,
    parse_openai_responses_input_count,
    prepare_openai_responses_text_count,
)
from governed_llm_gateway_core.application.provider import (
    ProviderContentDelta,
    ProviderRequest,
    ProviderResponseCompleted,
    ProviderResponseStarted,
    ProviderUsageCompleted,
)
from governed_llm_gateway_core.application.spend_cost_evidence import (
    SpendCostEvidenceError,
    SpendCostEvidenceErrorCode,
)


def _native() -> dict[str, object]:
    return {
        "model": "fixture-model-1",
        "store": False,
        "stream": True,
        "max_output_tokens": 64,
        "instructions": "  precise\n\n系统  ",
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": " first ☕  "}]},
            {"role": "assistant", "content": [{"type": "input_text", "text": " history\n"}]},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": " next "},
                    {"type": "input_text", "text": ""},
                ],
            },
        ],
    }


def _body(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _projection() -> OpenAIResponsesTextCountProjection:
    return OpenAIResponsesTextCountProjection(native_body=_body(_native()))


def _assert_error(
    action: object, code: SpendCostEvidenceErrorCode = SpendCostEvidenceErrorCode.INVALID_STATE
) -> None:
    # Separate tests invoke the real functions; this assertion checks sanitized failures.
    assert isinstance(action, SpendCostEvidenceError)
    assert action.code is code
    assert str(action) == "spend cost evidence failed"
    assert action.__cause__ is None
    assert action.__suppress_context__


@pytest.mark.parametrize("stream", [None, False, True])
def test_projection_preserves_native_text_and_omissions(stream: bool | None) -> None:
    native = _native()
    if stream is None:
        del native["stream"]
    else:
        native["stream"] = stream
    body = _body(native)
    projection = OpenAIResponsesTextCountProjection(native_body=body)
    assert projection.native_body is body
    assert json.loads(projection.count_body) == {
        key: native[key] for key in ("model", "input", "instructions")
    }
    assert json.loads(projection.native_body) == native
    assert "reasoning" not in json.loads(projection.count_body)
    assert "truncation" not in json.loads(projection.count_body)


def test_projection_copies_explicit_review_subset_without_rewriting_generation() -> None:
    native = _native()
    native.update(
        {"reasoning": {"effort": "none"}, "truncation": "disabled", "service_tier": "default"}
    )
    projection = OpenAIResponsesTextCountProjection(native_body=_body(native))
    assert json.loads(projection.count_body) == {
        key: native[key] for key in ("model", "input", "instructions", "reasoning", "truncation")
    }
    assert json.loads(projection.native_body) == native
    assert "service_tier" not in json.loads(projection.count_body)


def test_projection_does_not_add_instructions() -> None:
    native = _native()
    del native["instructions"]
    assert set(json.loads(OpenAIResponsesTextCountProjection(_body(native)).count_body)) == {
        "model",
        "input",
    }


@pytest.mark.parametrize("key,value", [("model", "fixture-model-2"), ("instructions", "changed")])
def test_native_input_drift_changes_the_projection(key: str, value: object) -> None:
    original = _projection()
    native = _native()
    native[key] = value
    changed = OpenAIResponsesTextCountProjection(_body(native))
    assert changed.native_body != original.native_body
    assert changed.count_body != original.count_body


def test_same_count_body_does_not_erase_generation_limit_correlation() -> None:
    original = _projection()
    native = _native()
    native["max_output_tokens"] = 65
    changed = OpenAIResponsesTextCountProjection(_body(native))
    assert changed.count_body == original.count_body
    assert changed.native_body != original.native_body
    assert OpenAIResponsesInputCountObservation(changed, 0) != (
        OpenAIResponsesInputCountObservation(original, 0)
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("text", {"format": {"type": "text"}}),
        ("tools", []),
        ("tool_choice", "none"),
        ("parallel_tool_calls", False),
        ("conversation", None),
        ("previous_response_id", None),
        ("background", False),
        ("metadata", {}),
        ("prompt_cache_key", "fixture-only"),
        ("prompt_cache_retention", "in_memory"),
        ("context_management", []),
        ("personality", "default"),
        ("include", []),
        ("unknown_option", None),
        ("reasoning", {"effort": "medium"}),
        ("reasoning", {"effort": "none", "summary": "auto"}),
        ("reasoning", None),
        ("service_tier", "auto"),
        ("service_tier", None),
        ("truncation", "auto"),
        ("store", True),
        ("store", 0),
        ("model", ""),
        ("model", " unsafe model "),
        ("model", "m" * 129),
        ("model", None),
    ],
)
def test_projection_rejects_unsupported_native_options(key: str, value: object) -> None:
    native = _native()
    native[key] = value
    with pytest.raises(SpendCostEvidenceError) as caught:
        OpenAIResponsesTextCountProjection(_body(native))
    _assert_error(caught.value, SpendCostEvidenceErrorCode.UNSUPPORTED)


@pytest.mark.parametrize("key", ["model", "store", "input", "max_output_tokens"])
def test_projection_rejects_missing_required_members(key: str) -> None:
    native = _native()
    del native[key]
    with pytest.raises(SpendCostEvidenceError) as caught:
        OpenAIResponsesTextCountProjection(_body(native))
    _assert_error(caught.value)


@pytest.mark.parametrize(
    "key,value",
    [
        ("max_output_tokens", None),
        ("max_output_tokens", True),
        ("max_output_tokens", 0),
        ("max_output_tokens", -1),
        ("max_output_tokens", 1.0),
        ("max_output_tokens", 2**63),
        ("stream", 1),
        ("stream", None),
        ("instructions", []),
        ("instructions", None),
    ],
)
def test_projection_rejects_invalid_required_types(key: str, value: object) -> None:
    native = _native()
    native[key] = value
    with pytest.raises(SpendCostEvidenceError) as caught:
        OpenAIResponsesTextCountProjection(_body(native))
    _assert_error(caught.value)


@pytest.mark.parametrize(
    "messages",
    [
        None,
        [],
        "caller text",
        [None],
        [{"role": "system", "content": [{"type": "input_text", "text": "x"}]}],
        [{"role": "developer", "content": [{"type": "input_text", "text": "x"}]}],
        [{"role": "tool", "content": [{"type": "input_text", "text": "x"}]}],
        [{"role": "user", "content": "x"}],
        [{"role": "user", "content": []}],
        [{"role": "user", "content": [None]}],
        [{"role": "user", "content": [{"type": "input_image", "image_url": "fixture"}]}],
        [{"role": "assistant", "content": [{"type": "output_text", "text": "x"}]}],
        [{"role": "user", "content": [{"type": "input_text", "text": None}]}],
        [{"role": "user", "content": [{"type": "input_text", "text": "x", "extra": 0}]}],
        [{"role": "user", "content": [{"type": "input_text", "text": "x"}], "extra": 0}],
        [{"type": "function_call_output", "call_id": "fixture", "output": "x"}],
    ],
)
def test_projection_rejects_nonlocal_plain_text_input(messages: object) -> None:
    native = _native()
    native["input"] = messages
    with pytest.raises(SpendCostEvidenceError) as caught:
        OpenAIResponsesTextCountProjection(_body(native))
    _assert_error(caught.value, SpendCostEvidenceErrorCode.UNSUPPORTED)


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not JSON",
        b"\xff",
        b"[]",
        b"null",
        b'{"model":"fixture","model":"other"}',
        b'{"input":[{"role":"user","role":"assistant"}]}',
        b'{"input":[{"content":[{"text":"secret fixture","text":"other"}]}]}',
        b'{"input":NaN}',
        b'{"input":Infinity}',
        b'{"input":-Infinity}',
        b'{"input":' + b"[" * 1500 + b"0" + b"]" * 1500 + b"}",
        pytest.param(b" " * (8 * 1024 * 1024 + 1), id="oversized_native_body"),
    ],
)
def test_projection_rejects_malformed_or_unbounded_bytes(body: bytes) -> None:
    with pytest.raises(SpendCostEvidenceError) as caught:
        OpenAIResponsesTextCountProjection(body)
    _assert_error(caught.value)


def test_projection_rejects_unencodable_native_text_without_exposing_it() -> None:
    native = _native()
    native["instructions"] = "\ud800"
    body = json.dumps(native, ensure_ascii=True).encode("utf-8")
    with pytest.raises(SpendCostEvidenceError) as caught:
        OpenAIResponsesTextCountProjection(body)
    _assert_error(caught.value)


@pytest.mark.parametrize("count", [0, 1, 2**63 - 1])
def test_count_observation_is_explicit_and_keeps_exact_projection(count: int) -> None:
    projection = _projection()
    result = parse_openai_responses_input_count(
        projection, body=_body({"object": "response.input_tokens", "input_tokens": count})
    )
    assert result.projection is projection
    assert result.input_tokens == count
    assert not hasattr(result, "body")
    assert not hasattr(result, "bound")
    assert not hasattr(result, "settlement")


@pytest.mark.parametrize(
    "report",
    [
        {},
        {"object": "response.input_tokens"},
        {"input_tokens": 0},
        {"object": "response.input_tokens", "input_tokens": None},
        {"object": "response.input_tokens", "input_tokens": True},
        {"object": "response.input_tokens", "input_tokens": 0.0},
        {"object": "response.input_tokens", "input_tokens": -1},
        {"object": "response.input_tokens", "input_tokens": 2**63},
        {"object": "response.input_tokens", "input_tokens": "0"},
        {"object": None, "input_tokens": 0},
        {"object": "response", "input_tokens": 0},
        {"object": "response.input_tokens", "input_tokens": 0, "payload": "fixture-only"},
    ],
)
def test_count_missing_invalid_or_foreign_fields_never_become_zero(report: object) -> None:
    with pytest.raises(SpendCostEvidenceError) as caught:
        parse_openai_responses_input_count(_projection(), body=_body(report))
    _assert_error(caught.value)


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"\xff",
        b"[]",
        b'{"object":"response.input_tokens","input_tokens":0,"input_tokens":1}',
        b'{"object":"response.input_tokens","input_tokens":NaN}',
        b'{"object":"response.input_tokens","input_tokens":1e999}',
        pytest.param(b" " * (64 * 1024 + 1), id="oversized_count_body"),
    ],
)
def test_count_parser_rejects_malformed_or_unbounded_report(body: bytes) -> None:
    with pytest.raises(SpendCostEvidenceError) as caught:
        parse_openai_responses_input_count(_projection(), body=body)
    _assert_error(caught.value)


class _BytesSubclass(bytes):
    pass


class _ProjectionSubclass(OpenAIResponsesTextCountProjection):
    pass


class _IntSubclass(int):
    pass


@pytest.mark.parametrize("body", [bytearray(b"{}"), memoryview(b"{}"), "{}", _BytesSubclass(b"{}")])
def test_private_bytes_reject_mutability_or_subclass_substitution(body: object) -> None:
    with pytest.raises(SpendCostEvidenceError) as caught:
        OpenAIResponsesTextCountProjection(cast(bytes, body))
    _assert_error(caught.value)
    with pytest.raises(SpendCostEvidenceError) as caught:
        parse_openai_responses_input_count(_projection(), body=cast(bytes, body))
    _assert_error(caught.value)


@pytest.mark.parametrize("projection", [None, object(), _ProjectionSubclass(_body(_native()))])
def test_count_rejects_foreign_projection_types(projection: object) -> None:
    with pytest.raises(SpendCostEvidenceError) as caught:
        parse_openai_responses_input_count(
            cast(OpenAIResponsesTextCountProjection, projection),
            body=_body({"object": "response.input_tokens", "input_tokens": 0}),
        )
    _assert_error(caught.value)
    with pytest.raises(SpendCostEvidenceError) as caught:
        OpenAIResponsesInputCountObservation(
            cast(OpenAIResponsesTextCountProjection, projection), 0
        )
    _assert_error(caught.value)


@pytest.mark.parametrize("count", [True, -1, 0.0, 2**63, _IntSubclass(0)])
def test_observation_constructor_enforces_plain_bounded_counts(count: object) -> None:
    with pytest.raises(SpendCostEvidenceError) as caught:
        OpenAIResponsesInputCountObservation(_projection(), cast(int, count))
    _assert_error(caught.value)


def test_private_values_are_frozen_and_do_not_print_native_text() -> None:
    projection = _projection()
    observation = OpenAIResponsesInputCountObservation(projection, 0)
    assert repr(projection) == "OpenAIResponsesTextCountProjection()"
    assert repr(observation) == "OpenAIResponsesInputCountObservation()"
    for instance, name, value in (
        (projection, "count_body", b"forged"),
        (observation, "input_tokens", 1),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(instance, name, value)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://compatible.fixture/v1/responses",
        "https://api.openai.com/v1/chat/completions",
        "https://api.openai.com/v1/responses?fixture=1",
        "https://api.openai.com/v1/responses#fixture",
        "http://api.openai.com/v1/responses",
    ],
)
def test_sse_projection_rejects_nonliteral_routes(endpoint: str) -> None:
    source = PreparedSseRequest(endpoint, (), _body(_native()), 5)
    with pytest.raises(SpendCostEvidenceError) as caught:
        prepare_openai_responses_text_count(source)
    _assert_error(caught.value, SpendCostEvidenceErrorCode.UNSUPPORTED)


@pytest.mark.parametrize("stream", [None, False])
def test_sse_helper_requires_actual_stream_preparation(stream: bool | None) -> None:
    native = _native()
    if stream is None:
        del native["stream"]
    else:
        native["stream"] = stream
    source = PreparedSseRequest("https://api.openai.com/v1/responses", (), _body(native), 5)
    with pytest.raises(SpendCostEvidenceError) as caught:
        prepare_openai_responses_text_count(source)
    _assert_error(caught.value, SpendCostEvidenceErrorCode.UNSUPPORTED)


def test_sse_helper_rejects_foreign_source() -> None:
    with pytest.raises(SpendCostEvidenceError) as caught:
        prepare_openai_responses_text_count(cast(PreparedSseRequest, object()))
    _assert_error(caught.value)


@dataclass
class _Stream:
    events: list[SseEvent]
    status_code: int = 200
    headers: Mapping[str, str] = field(
        default_factory=lambda: {"content-type": "text/event-stream"}
    )
    closed: bool = False
    index: int = 0

    def __aiter__(self) -> AsyncIterator[SseEvent]:
        return self

    async def __anext__(self) -> SseEvent:
        if self.index == len(self.events):
            raise StopAsyncIteration
        event = self.events[self.index]
        self.index += 1
        return event

    async def aclose(self) -> None:
        self.closed = True


class _Transport:
    def __init__(self, stream: _Stream) -> None:
        self.stream = stream
        self.calls: list[PreparedSseRequest] = []

    async def open_sse(self, request: PreparedSseRequest) -> SseStream:
        self.calls.append(request)
        return self.stream


def test_projection_uses_actual_native_preparation_and_preserves_controlled_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[PreparedSseRequest] = []

    def capture(
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> PreparedSseRequest:
        source = prepare_sse_request(
            url=url, headers=headers, payload=payload, timeout_seconds=timeout_seconds
        )
        captured.append(source)
        return source

    monkeypatch.setattr(openai_responses_streaming, "prepare_sse_request", capture)
    stream = _Stream(
        [
            SseEvent(
                event=None,
                data=json.dumps({"type": "response.created", "response": {"id": "fixture"}}),
            ),
            SseEvent(
                event=None,
                data=json.dumps({"type": "response.output_text.delta", "delta": "hello"}),
            ),
            SseEvent(
                event=None,
                data=json.dumps(
                    {
                        "type": "response.completed",
                        "response": {
                            "id": "fixture",
                            "status": "completed",
                            "usage": {"input_tokens": 5, "output_tokens": 2},
                        },
                    }
                ),
            ),
        ]
    )
    transport = _Transport(stream)
    adapter = openai_responses_streaming.OpenAIResponsesStreamingAdapter(
        api_key="fixture-only", sse_transport=transport
    )
    request = ProviderRequest(
        model="fixture-model-1",
        messages=(
            Message(role=MessageRole.SYSTEM, content=" first system "),
            Message(role=MessageRole.SYSTEM, content="第二"),
            Message(role=MessageRole.USER, content="hello ☕ "),
            Message(role=MessageRole.ASSISTANT, content=" local history "),
            Message(role=MessageRole.USER, content="next"),
        ),
        max_output_tokens=64,
        timeout_seconds=5,
    )
    prepared = adapter.prepare_stream(request)
    assert len(captured) == 1
    assert transport.calls == []
    source = captured[0]
    original_headers = source.headers
    projection = prepare_openai_responses_text_count(source)
    assert projection.native_body is source.body
    assert source.headers is original_headers
    assert transport.calls == []
    native = json.loads(source.body)
    assert json.loads(projection.count_body) == {
        "model": request.model,
        "instructions": " first system \n\n第二",
        "input": native["input"],
    }

    async def consume() -> list[object]:
        return [event async for event in prepared.stream()]

    events = asyncio.run(consume())
    assert [type(event) for event in events] == [
        ProviderResponseStarted,
        ProviderContentDelta,
        ProviderUsageCompleted,
        ProviderResponseCompleted,
    ]
    assert transport.calls == [source]
    assert transport.calls[0] is source
    assert transport.calls[0].body is projection.native_body
    assert stream.closed
