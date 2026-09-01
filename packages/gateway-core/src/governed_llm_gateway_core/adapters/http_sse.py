"""Bounded asynchronous SSE-over-HTTPS transport for provider streaming adapters."""

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from .http_json import TransportFailure, TransportFailureKind

_MAX_EVENT_BYTES = 1024 * 1024
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

        client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds))
        request = client.build_request(
            "POST",
            url,
            headers=dict(headers),
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
        self._lines = response.aiter_lines().__aiter__()
        self._event_name: str | None = None
        self._data_lines: list[str] = []
        self._event_bytes = 0
        self._closed = False

    def __aiter__(self) -> AsyncIterator[SseEvent]:
        return self

    async def __anext__(self) -> SseEvent:
        while True:
            try:
                line = await self._lines.__anext__()
            except StopAsyncIteration:
                if self._data_lines:
                    return self._dispatch()
                raise
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

            self._event_bytes += len(line.encode("utf-8")) + 1
            if self._event_bytes > _MAX_EVENT_BYTES:
                raise TransportFailure(
                    TransportFailureKind.INVALID_RESPONSE,
                    "provider SSE event exceeded the bounded event size",
                )

            if line == "":
                if self._data_lines:
                    return self._dispatch()
                self._event_name = None
                self._event_bytes = 0
                continue
            if line.startswith(":"):
                continue

            field, separator, raw_value = line.partition(":")
            if not separator:
                raw_value = ""
            value = raw_value[1:] if raw_value.startswith(" ") else raw_value
            if field == "event":
                self._event_name = value or None
            elif field == "data":
                self._data_lines.append(value)

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
