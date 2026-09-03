"""Bounded asynchronous SSE-over-HTTPS transport for provider streaming adapters."""

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from a2a_otel_kit import inject_trace_context

from .http_json import TransportFailure, TransportFailureKind

_MAX_EVENT_BYTES = 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024
_SAFE_RESPONSE_HEADERS = frozenset({"content-type", "retry-after"})


@dataclass(frozen=True, slots=True)
class SseEvent:
    """One bounded SSE event after transport framing has been removed."""

    event: str | None
    data: str


class SseStream(Protocol):
    """Open provider SSE response whose resources can be closed explicitly."""

    status_code: int
    headers: Mapping[str, str]

    def __aiter__(self) -> AsyncIterator[SseEvent]:
        """Iterate bounded SSE events."""
        ...

    async def aclose(self) -> None:
        """Close the upstream response immediately."""
        ...


class SseTransport(Protocol):
    """Injectable streaming transport used by provider adapter contract tests."""

    async def open_sse(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> SseStream:
        """Open one HTTPS SSE response without buffering the body."""
        ...


class HttpxSseTransport:
    """HTTPX streaming transport with cancellation-safe response ownership."""

    async def open_sse(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> SseStream:
        """Open a bounded provider stream using a dedicated async client."""
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("provider streaming endpoint must be an absolute HTTPS URL")
        if parsed.fragment:
            raise ValueError("provider streaming endpoint must not contain a fragment")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        request_headers = dict(headers)
        inject_trace_context(request_headers)
        client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))
        request = client.build_request(
            "POST",
            url,
            headers=request_headers,
            json=dict(payload),
        )
        try:
            response = await client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            await client.aclose()
            raise TransportFailure(
                TransportFailureKind.TIMEOUT,
                "provider stream timed out while opening",
            ) from exc
        except httpx.RequestError as exc:
            await client.aclose()
            raise TransportFailure(
                TransportFailureKind.NETWORK,
                "provider stream transport failed while opening",
            ) from exc

        safe_headers = {
            name.lower(): value
            for name, value in response.headers.items()
            if name.lower() in _SAFE_RESPONSE_HEADERS
        }
        return _HttpxSseStream(
            response=response,
            client=client,
            headers=safe_headers,
        )


class _HttpxSseStream:
    def __init__(
        self,
        *,
        response: httpx.Response,
        client: httpx.AsyncClient,
        headers: Mapping[str, str],
    ) -> None:
        self.status_code: int = response.status_code
        self.headers: Mapping[str, str] = dict(headers)
        self._response = response
        self._client = client
        self._chunks = response.aiter_bytes(chunk_size=_READ_CHUNK_BYTES).__aiter__()
        self._buffer = bytearray()
        self._event_name: str | None = None
        self._data_lines: list[str] = []
        self._event_bytes = 0
        self._eof = False
        self._closed = False

    def __aiter__(self) -> AsyncIterator[SseEvent]:
        return self

    async def __anext__(self) -> SseEvent:
        while True:
            event = self._drain_complete_lines(final=self._eof)
            if event is not None:
                return event

            if self._eof:
                if self._buffer:
                    final_line = bytes(self._buffer)
                    self._buffer.clear()
                    event = self._consume_line(final_line, separator_bytes=0)
                    if event is not None:
                        return event
                if self._data_lines:
                    return self._dispatch()
                raise StopAsyncIteration

            try:
                chunk = await self._chunks.__anext__()
            except StopAsyncIteration:
                self._eof = True
                continue
            except httpx.TimeoutException as exc:
                raise TransportFailure(
                    TransportFailureKind.TIMEOUT,
                    "provider stream timed out while reading",
                ) from exc
            except httpx.RequestError as exc:
                raise TransportFailure(
                    TransportFailureKind.NETWORK,
                    "provider stream transport failed while reading",
                ) from exc

            if not chunk:
                continue
            self._buffer.extend(chunk)

            event = self._drain_complete_lines(final=False)
            if event is not None:
                return event
            self._ensure_partial_event_bound()

    def _drain_complete_lines(self, *, final: bool) -> SseEvent | None:
        while True:
            popped = self._pop_line(final=final)
            if popped is None:
                return None
            line, separator_bytes = popped
            event = self._consume_line(line, separator_bytes=separator_bytes)
            if event is not None:
                return event

    def _pop_line(self, *, final: bool) -> tuple[bytes, int] | None:
        lf_index = self._buffer.find(b"\n")
        cr_index = self._buffer.find(b"\r")
        indexes = [index for index in (lf_index, cr_index) if index >= 0]
        if not indexes:
            return None

        index = min(indexes)
        separator_bytes = 1
        if self._buffer[index] == 13:
            if index + 1 == len(self._buffer) and not final:
                return None
            if index + 1 < len(self._buffer) and self._buffer[index + 1] == 10:
                separator_bytes = 2

        line = bytes(self._buffer[:index])
        del self._buffer[: index + separator_bytes]
        return line, separator_bytes

    def _consume_line(self, line: bytes, *, separator_bytes: int) -> SseEvent | None:
        self._event_bytes += len(line) + separator_bytes
        self._ensure_event_bound()

        if not line:
            if self._data_lines:
                return self._dispatch()
            self._event_name = None
            self._event_bytes = 0
            return None

        try:
            decoded = line.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TransportFailure(
                TransportFailureKind.INVALID_RESPONSE,
                "provider SSE event contained invalid UTF-8",
            ) from exc

        if decoded.startswith(":"):
            return None

        field, separator, raw_value = decoded.partition(":")
        if not separator:
            raw_value = ""
        value = raw_value[1:] if raw_value.startswith(" ") else raw_value
        if field == "event":
            self._event_name = value or None
        elif field == "data":
            self._data_lines.append(value)
        return None

    def _ensure_partial_event_bound(self) -> None:
        if self._event_bytes + len(self._buffer) > _MAX_EVENT_BYTES:
            raise TransportFailure(
                TransportFailureKind.INVALID_RESPONSE,
                "provider SSE event exceeded the bounded event size",
            )

    def _ensure_event_bound(self) -> None:
        if self._event_bytes > _MAX_EVENT_BYTES:
            raise TransportFailure(
                TransportFailureKind.INVALID_RESPONSE,
                "provider SSE event exceeded the bounded event size",
            )

    def _dispatch(self) -> SseEvent:
        event = SseEvent(event=self._event_name, data="\n".join(self._data_lines))
        self._event_name = None
        self._data_lines = []
        self._event_bytes = 0
        return event

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._response.aclose()
        finally:
            await self._client.aclose()
