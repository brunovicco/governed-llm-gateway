import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, dataclass, field, fields
from typing import cast

import pytest
from governed_llm_gateway_contracts import Message, MessageRole
from governed_llm_gateway_core.adapters.http_json import JsonHttpResponse
from governed_llm_gateway_core.adapters.http_sse import PreparedSseRequest, SseEvent, SseStream
from governed_llm_gateway_core.adapters.openai_responses import OpenAIResponsesAdapter
from governed_llm_gateway_core.adapters.openai_responses_streaming import (
    OpenAIResponsesStreamingAdapter,
)
from governed_llm_gateway_core.adapters.openai_responses_usage import (
    OpenAIResponsesUsageCounters,
    parse_openai_responses_usage_counters,
)
from governed_llm_gateway_core.application.provider import (
    ProviderContentDelta,
    ProviderRequest,
    ProviderResponseCompleted,
    ProviderResponseStarted,
    ProviderUsage,
    ProviderUsageCompleted,
)
from governed_llm_gateway_core.application.spend_cost_evidence import (
    SpendCostEvidenceError,
    SpendCostEvidenceErrorCode,
)

_MAX_INTEGER = 2**63 - 1
_FIELDS = tuple(item.name for item in fields(OpenAIResponsesUsageCounters))
_PATHS = (
    ("input_tokens",),
    ("input_tokens_details", "cached_tokens"),
    ("input_tokens_details", "cache_write_tokens"),
    ("output_tokens",),
    ("output_tokens_details", "reasoning_tokens"),
    ("total_tokens",),
)


class _IntegerSubclass(int):
    pass


class _BytesSubclass(bytes):
    pass


def _usage(
    input_tokens: int = 11,
    cached_tokens: int = 4,
    cache_write_tokens: int = 3,
    output_tokens: int = 7,
    reasoning_tokens: int = 5,
    total_tokens: int = 18,
) -> dict[str, object]:
    return {
        "input_tokens": input_tokens,
        "input_tokens_details": {
            "cached_tokens": cached_tokens,
            "cache_write_tokens": cache_write_tokens,
        },
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": reasoning_tokens},
        "total_tokens": total_tokens,
    }


def _body(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def _container(usage: dict[str, object], path: tuple[str, ...]) -> dict[str, object]:
    return usage if len(path) == 1 else cast(dict[str, object], usage[path[0]])


def _assert_error(
    error: SpendCostEvidenceError,
    code: SpendCostEvidenceErrorCode = SpendCostEvidenceErrorCode.INVALID_STATE,
) -> None:
    assert error.code is code
    assert str(error) == "spend cost evidence failed"
    assert error.args == ("spend cost evidence failed",)
    assert error.__cause__ is None
    assert error.__suppress_context__
    assert "sensitive-fixture" not in repr(error)


@pytest.mark.parametrize(
    "counts",
    [
        (0, 0, 0, 0, 0, 0),
        (11, 4, 3, 7, 5, 18),
        (11, 11, 0, 0, 0, 11),
        (11, 0, 11, 7, 7, 18),
        (0, 0, 0, 7, 7, 7),
        (_MAX_INTEGER, _MAX_INTEGER, 0, 0, 0, _MAX_INTEGER),
        (0, 0, 0, _MAX_INTEGER, _MAX_INTEGER, _MAX_INTEGER),
        (_MAX_INTEGER - 1, 0, 0, 1, 0, _MAX_INTEGER),
        # Truthful output is not clamped to a hypothetical request cap.
        (11, 4, 3, 100_000, 99_999, 100_011),
    ],
)
def test_explicit_counters_are_preserved_without_derivation(counts: tuple[int, ...]) -> None:
    parsed = parse_openai_responses_usage_counters(body=_body(_usage(*counts)))
    assert tuple(getattr(parsed, name) for name in _FIELDS) == counts
    assert parsed.output_tokens + parsed.input_tokens == parsed.total_tokens
    assert not hasattr(parsed, "uncached_input_tokens")
    assert not hasattr(parsed, "finality")
    assert not hasattr(parsed, "projection")
    assert not hasattr(parsed, "body")
    assert repr(parsed) == "OpenAIResponsesUsageCounters()"


@pytest.mark.parametrize("name", _FIELDS)
@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        False,
        -1,
        1.0,
        "sensitive-fixture",
        [],
        {},
        _MAX_INTEGER + 1,
        _IntegerSubclass(0),
    ],
)
def test_direct_construction_revalidates_every_scalar(name: str, value: object) -> None:
    values: dict[str, object] = dict.fromkeys(_FIELDS, 0)
    values[name] = value
    with pytest.raises(SpendCostEvidenceError) as caught:
        OpenAIResponsesUsageCounters(**cast(dict[str, int], values))
    _assert_error(caught.value)


@pytest.mark.parametrize("path", _PATHS)
@pytest.mark.parametrize(
    "value", [None, True, False, -1, 1.0, "sensitive-fixture", [], {}, _MAX_INTEGER + 1]
)
def test_parser_rejects_invalid_scalar_without_zero_default(
    path: tuple[str, ...], value: object
) -> None:
    usage = _usage()
    _container(usage, path)[path[-1]] = value
    with pytest.raises(SpendCostEvidenceError) as caught:
        parse_openai_responses_usage_counters(body=_body(usage))
    _assert_error(caught.value)


@pytest.mark.parametrize("path", (*_PATHS, ("input_tokens_details",), ("output_tokens_details",)))
def test_every_native_count_and_details_object_is_mandatory(path: tuple[str, ...]) -> None:
    usage = _usage(0, 0, 0, 0, 0, 0)
    del _container(usage, path)[path[-1]]
    with pytest.raises(SpendCostEvidenceError) as caught:
        parse_openai_responses_usage_counters(body=_body(usage))
    _assert_error(caught.value)


@pytest.mark.parametrize("name", ["input_tokens_details", "output_tokens_details"])
@pytest.mark.parametrize("value", [None, True, 0, "sensitive-fixture", [], {}])
def test_details_require_closed_objects(name: str, value: object) -> None:
    usage = _usage()
    usage[name] = value
    with pytest.raises(SpendCostEvidenceError) as caught:
        parse_openai_responses_usage_counters(body=_body(usage))
    _assert_error(caught.value)


@pytest.mark.parametrize("container", [None, "input_tokens_details", "output_tokens_details"])
@pytest.mark.parametrize("value", [0, None, False, [], {}, "sensitive-fixture"])
def test_unknown_dimensions_are_unsupported_even_when_empty(
    container: str | None, value: object
) -> None:
    usage = _usage()
    target = usage if container is None else cast(dict[str, object], usage[container])
    target["unqualified_dimension"] = value
    with pytest.raises(SpendCostEvidenceError) as caught:
        parse_openai_responses_usage_counters(body=_body(usage))
    _assert_error(caught.value, SpendCostEvidenceErrorCode.UNSUPPORTED)


@pytest.mark.parametrize(
    "counts,code",
    [
        ((11, 4, 3, 7, 5, 0), SpendCostEvidenceErrorCode.INVALID_STATE),
        ((11, 4, 3, 7, 5, 23), SpendCostEvidenceErrorCode.INVALID_STATE),
        ((11, 12, 0, 7, 5, 18), SpendCostEvidenceErrorCode.INVALID_STATE),
        ((11, 0, 12, 7, 5, 18), SpendCostEvidenceErrorCode.INVALID_STATE),
        ((11, 4, 3, 7, 8, 18), SpendCostEvidenceErrorCode.INVALID_STATE),
        ((_MAX_INTEGER, 0, 0, 1, 0, _MAX_INTEGER), SpendCostEvidenceErrorCode.INVALID_STATE),
        ((11, 6, 6, 7, 5, 18), SpendCostEvidenceErrorCode.UNSUPPORTED),
    ],
)
def test_consistency_rules_apply_to_parser_and_direct_values(
    counts: tuple[int, ...], code: SpendCostEvidenceErrorCode
) -> None:
    with pytest.raises(SpendCostEvidenceError) as caught:
        parse_openai_responses_usage_counters(body=_body(_usage(*counts)))
    _assert_error(caught.value, code)
    with pytest.raises(SpendCostEvidenceError) as caught:
        OpenAIResponsesUsageCounters(**dict(zip(_FIELDS, counts, strict=True)))
    _assert_error(caught.value, code)


@pytest.mark.parametrize("name", _FIELDS)
def test_private_counters_are_frozen_and_slotted(name: str) -> None:
    parsed = parse_openai_responses_usage_counters(body=_body(_usage()))
    assert not hasattr(parsed, "__dict__")
    with pytest.raises(FrozenInstanceError):
        setattr(parsed, name, 0)


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"\xff",
        b"null",
        b"true",
        b"[]",
        b"0",
        b'"sensitive-fixture"',
        b"{",
        b"{} trailing-sensitive-fixture",
        b"[" * 2_000 + b"]" * 2_000,
        b" " * (64 * 1024 + 1),
        b'{"input_tokens":0,"input_tokens":0}',
        b'{"input_tokens_details":{"cached_tokens":0,"cached_tokens":0}}',
        b'{"output_tokens_details":{"reasoning_tokens":0,"reasoning_tokens":0}}',
        b'{"input_tokens":NaN}',
        b'{"input_tokens":Infinity}',
        b'{"input_tokens":-Infinity}',
        b'{"input_tokens":' + b"9" * 5_000 + b"}",
    ],
)
def test_malformed_ambiguous_and_unbounded_reports_fail_safely(body: bytes) -> None:
    with pytest.raises(SpendCostEvidenceError) as caught:
        parse_openai_responses_usage_counters(body=body)
    _assert_error(caught.value)


@pytest.mark.parametrize(
    "body", [None, "{}", bytearray(b"{}"), memoryview(b"{}"), _BytesSubclass(b"{}")]
)
def test_only_plain_bytes_enter_the_parser(body: object) -> None:
    with pytest.raises(SpendCostEvidenceError) as caught:
        parse_openai_responses_usage_counters(body=cast(bytes, body))
    _assert_error(caught.value)


@pytest.mark.parametrize(
    "report",
    [
        {"usage": _usage(), "id": "sensitive-fixture", "status": "completed"},
        {"type": "response.completed", "response": {"usage": _usage()}},
        {"object": "response.input_tokens", "input_tokens": 11},
        {"input_tokens": 11, "output_tokens": 7},
        {},
    ],
)
def test_full_events_count_observations_and_normalized_usage_are_not_native_usage(
    report: object,
) -> None:
    with pytest.raises(SpendCostEvidenceError) as caught:
        parse_openai_responses_usage_counters(body=_body(report))
    _assert_error(caught.value)


def test_parser_is_pure_and_keeps_no_shared_report_state() -> None:
    body = _body(_usage())
    with ThreadPoolExecutor(max_workers=4) as executor:
        parsed = list(
            executor.map(lambda _: parse_openai_responses_usage_counters(body=body), range(16))
        )
    assert all(item == parsed[0] for item in parsed)
    assert len({id(item) for item in parsed}) == len(parsed)


class _JsonTransport:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        self.calls += 1
        return JsonHttpResponse(status_code=200, headers={}, payload=self.payload)


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


class _SseTransport:
    def __init__(self, stream: _Stream) -> None:
        self.stream = stream
        self.calls: list[PreparedSseRequest] = []

    async def open_sse(self, request: PreparedSseRequest) -> SseStream:
        self.calls.append(request)
        return self.stream


def test_controlled_json_and_sse_keep_legacy_normalization_and_public_events() -> None:
    # Extraction here is a local fixture, not trusted production ingestion/finality.
    usage = _usage()
    original = _body(usage)
    payload: dict[str, object] = {
        "id": "fixture",
        "model": "fixture-model",
        "status": "completed",
        "usage": usage,
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "hello"}]}],
    }
    request = ProviderRequest(
        model="fixture-model",
        messages=(Message(role=MessageRole.USER, content="hello"),),
        max_output_tokens=64,
        timeout_seconds=5,
    )
    json_transport = _JsonTransport(payload)
    json_adapter = OpenAIResponsesAdapter(api_key="fixture-only", transport=json_transport)
    response = asyncio.run(json_adapter.generate(request))
    assert response.text == "hello"
    assert response.usage == ProviderUsage(input_tokens=11, output_tokens=7)
    assert json_transport.calls == 1
    parsed_json = parse_openai_responses_usage_counters(body=_body(payload["usage"]))

    completed = {"type": "response.completed", "response": payload}
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
            SseEvent(event=None, data=json.dumps(completed)),
        ]
    )
    sse_transport = _SseTransport(stream)
    sse_adapter = OpenAIResponsesStreamingAdapter(
        api_key="fixture-only", sse_transport=sse_transport
    )

    async def consume() -> list[object]:
        return [event async for event in sse_adapter.stream(request)]

    events = asyncio.run(consume())
    assert [type(event) for event in events] == [
        ProviderResponseStarted,
        ProviderContentDelta,
        ProviderUsageCompleted,
        ProviderResponseCompleted,
    ]
    assert cast(ProviderUsageCompleted, events[2]).usage == response.usage
    assert stream.closed
    assert len(sse_transport.calls) == 1
    completed_response = cast(dict[str, object], json.loads(stream.events[-1].data)["response"])
    parsed_sse = parse_openai_responses_usage_counters(body=_body(completed_response["usage"]))
    assert parsed_sse == parsed_json
    assert parsed_json.cached_input_tokens == 4
    assert parsed_json.cache_write_input_tokens == 3
    assert parsed_json.reasoning_output_tokens == 5
    assert _body(usage) == original
