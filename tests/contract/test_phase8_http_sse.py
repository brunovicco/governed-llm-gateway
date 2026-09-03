import asyncio
from collections.abc import AsyncIterable, AsyncIterator, Callable

import httpx
import pytest
from governed_llm_gateway_core.adapters.http_json import (
    TransportFailure,
    TransportFailureKind,
)
from governed_llm_gateway_core.adapters.http_sse import HttpxSseTransport, SseEvent


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, *chunks: bytes) -> None:
        self._chunks = chunks
        self.closed = False
        self.yield_count = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            self.yield_count += 1
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class FailingChunkStream(httpx.AsyncByteStream):
    def __init__(self, error: httpx.RequestError) -> None:
        self._error = error
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"data: partial\n"
        raise self._error

    async def aclose(self) -> None:
        self.closed = True


def _install_mock_client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> list[httpx.AsyncClient]:
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    clients: list[httpx.AsyncClient] = []

    def factory(*, timeout: httpx.Timeout) -> httpx.AsyncClient:
        client = original_client(transport=transport, timeout=timeout)
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    return clients


async def _collect(stream: AsyncIterable[SseEvent]) -> list[SseEvent]:
    return [event async for event in stream]


def test_httpx_sse_transport_frames_events_and_sanitizes_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = ChunkStream(
        b": keepalive\n\n",
        b"event: content.delta\n",
        b"data: hello\n",
        b"data: world\n\n",
        b"data: tail",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url == httpx.URL("https://provider.example/stream")
        return httpx.Response(
            200,
            headers={
                "content-type": "text/event-stream",
                "retry-after": "2",
                "x-provider-secret": "must-not-leak",
            },
            stream=body,
        )

    clients = _install_mock_client(monkeypatch, handler)

    async def scenario() -> tuple[list[SseEvent], int, dict[str, str]]:
        stream = await HttpxSseTransport().open_sse(
            url="https://provider.example/stream",
            headers={"authorization": "Bearer secret"},
            payload={"stream": True},
            timeout_seconds=2.0,
        )
        events = await _collect(stream)
        status = stream.status_code
        headers = dict(stream.headers)
        await stream.aclose()
        await stream.aclose()
        return events, status, headers

    events, status, headers = asyncio.run(scenario())

    assert events == [
        SseEvent(event="content.delta", data="hello\nworld"),
        SseEvent(event=None, data="tail"),
    ]
    assert status == 200
    assert headers == {
        "content-type": "text/event-stream",
        "retry-after": "2",
    }
    assert body.closed is True
    assert len(clients) == 1
    assert clients[0].is_closed is True


def test_httpx_sse_transport_accepts_crlf_and_cr_event_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = ChunkStream(
        b"event: first\r\ndata: one\r\n\r\n",
        b"event: second\rdata: two\r\r",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, stream=body)

    _install_mock_client(monkeypatch, handler)

    async def scenario() -> list[SseEvent]:
        stream = await HttpxSseTransport().open_sse(
            url="https://provider.example/stream",
            headers={},
            payload={},
            timeout_seconds=1.0,
        )
        try:
            return await _collect(stream)
        finally:
            await stream.aclose()

    assert asyncio.run(scenario()) == [
        SseEvent(event="first", data="one"),
        SseEvent(event="second", data="two"),
    ]


@pytest.mark.parametrize(
    ("url", "timeout_seconds"),
    [
        ("http://provider.example/stream", 1.0),
        ("https:///stream", 1.0),
        ("https://user@provider.example/stream", 1.0),
        ("https://user:pass@provider.example/stream", 1.0),
        ("https://provider.example/stream#fragment", 1.0),
        ("https://provider.example/stream", 0.0),
    ],
)
def test_httpx_sse_transport_rejects_unsafe_endpoint_or_timeout(
    url: str,
    timeout_seconds: float,
) -> None:
    with pytest.raises(ValueError):
        asyncio.run(
            HttpxSseTransport().open_sse(
                url=url,
                headers={},
                payload={},
                timeout_seconds=timeout_seconds,
            )
        )


@pytest.mark.parametrize(
    ("error_factory", "expected_kind"),
    [
        (
            lambda request: httpx.ReadTimeout("open timeout", request=request),
            TransportFailureKind.TIMEOUT,
        ),
        (
            lambda request: httpx.ConnectError("open network", request=request),
            TransportFailureKind.NETWORK,
        ),
    ],
)
def test_httpx_sse_transport_normalizes_open_failures_and_closes_client(
    monkeypatch: pytest.MonkeyPatch,
    error_factory: Callable[[httpx.Request], httpx.RequestError],
    expected_kind: TransportFailureKind,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error_factory(request)

    clients = _install_mock_client(monkeypatch, handler)

    with pytest.raises(TransportFailure) as captured:
        asyncio.run(
            HttpxSseTransport().open_sse(
                url="https://provider.example/stream",
                headers={},
                payload={},
                timeout_seconds=1.0,
            )
        )

    assert captured.value.kind is expected_kind
    assert len(clients) == 1
    assert clients[0].is_closed is True


@pytest.mark.parametrize(
    ("error_factory", "expected_kind"),
    [
        (
            lambda request: httpx.ReadTimeout("read timeout", request=request),
            TransportFailureKind.TIMEOUT,
        ),
        (
            lambda request: httpx.ReadError("read network", request=request),
            TransportFailureKind.NETWORK,
        ),
    ],
)
def test_httpx_sse_stream_normalizes_read_failures(
    monkeypatch: pytest.MonkeyPatch,
    error_factory: Callable[[httpx.Request], httpx.RequestError],
    expected_kind: TransportFailureKind,
) -> None:
    body: FailingChunkStream | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal body
        body = FailingChunkStream(error_factory(request))
        return httpx.Response(200, stream=body)

    _install_mock_client(monkeypatch, handler)

    async def scenario() -> None:
        stream = await HttpxSseTransport().open_sse(
            url="https://provider.example/stream",
            headers={},
            payload={},
            timeout_seconds=1.0,
        )
        try:
            with pytest.raises(TransportFailure) as captured:
                await anext(stream.__aiter__())
            assert captured.value.kind is expected_kind
        finally:
            await stream.aclose()

    asyncio.run(scenario())
    assert body is not None
    assert body.closed is True


def test_httpx_sse_stream_rejects_oversized_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = ChunkStream(b"data: " + (b"x" * (1024 * 1024)) + b"\n\n")

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, stream=body)

    _install_mock_client(monkeypatch, handler)

    async def scenario() -> None:
        stream = await HttpxSseTransport().open_sse(
            url="https://provider.example/stream",
            headers={},
            payload={},
            timeout_seconds=1.0,
        )
        try:
            with pytest.raises(TransportFailure) as captured:
                await anext(stream.__aiter__())
            assert captured.value.kind is TransportFailureKind.INVALID_RESPONSE
        finally:
            await stream.aclose()

    asyncio.run(scenario())
    assert body.closed is True


def test_httpx_sse_stream_bounds_unterminated_line_before_source_is_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fragment = b"x" * (64 * 1024)
    chunks = (b"data: " + fragment,) + (fragment,) * 20
    body = ChunkStream(*chunks)

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, stream=body)

    _install_mock_client(monkeypatch, handler)

    async def scenario() -> None:
        stream = await HttpxSseTransport().open_sse(
            url="https://provider.example/stream",
            headers={},
            payload={},
            timeout_seconds=1.0,
        )
        try:
            with pytest.raises(TransportFailure) as captured:
                await anext(stream.__aiter__())
            assert captured.value.kind is TransportFailureKind.INVALID_RESPONSE
        finally:
            await stream.aclose()

    asyncio.run(scenario())
    assert body.closed is True
    assert body.yield_count < len(chunks)
