"""Explicit PDP-only connection reuse, independent of authorization decision state."""

import asyncio
import json
import math
import ssl
import sys
from collections.abc import Mapping
from types import TracebackType
from typing import cast
from urllib.parse import urlsplit

import httpx

from .policy_router import (
    _MAX_RESPONSE_BYTES,
    PolicyHttpResponse,
    PolicyTransportFailure,
    PolicyTransportFailureKind,
)

_CLEANUP_SECONDS = 1.0


class HttpxPolicyTransport:
    """Own one bounded HTTPS pool on one event loop; never replay a policy POST."""

    def __init__(
        self,
        *,
        endpoint: str,
        max_connections: int = 8,
        max_keepalive_connections: int = 8,
        keepalive_expiry_seconds: float = 30.0,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        """Validate trusted configuration without opening a connection or reading secrets."""
        _validate_endpoint(endpoint)
        if type(max_connections) is not int or not 1 <= max_connections <= 64:
            raise ValueError("policy max_connections must be an integer in 1..64")
        if (
            type(max_keepalive_connections) is not int
            or not 0 <= max_keepalive_connections <= max_connections
        ):
            raise ValueError("policy keepalive connections must be in 0..max_connections")
        _validate_seconds(keepalive_expiry_seconds, "keepalive expiry")
        if ssl_context is not None and (
            not isinstance(ssl_context, ssl.SSLContext)
            or not ssl_context.check_hostname
            or ssl_context.verify_mode != ssl.CERT_REQUIRED
        ):
            raise ValueError("policy TLS context must verify certificates and hostname")
        self._endpoint = endpoint
        self._ssl_context = ssl_context
        self._limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            keepalive_expiry=float(keepalive_expiry_seconds),
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._transport: httpx.AsyncBaseTransport | None = None
        self._active: set[asyncio.Task[PolicyHttpResponse]] = set()
        self._closed = False
        self._close_task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "HttpxPolicyTransport":
        """Bind the owner loop without eagerly opening a socket."""
        self._bind_loop()
        self._check_open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close owned work without replacing an existing failure or cancellation."""
        try:
            await self.aclose()
        except Exception:
            if exc_type is None:
                raise

    def _bind_loop(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise RuntimeError("policy transport belongs to another event loop")

    def _check_open(self) -> None:
        if self._closed:
            raise RuntimeError("policy transport is closed")

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> PolicyHttpResponse:
        """Make one fresh policy exchange; pool wait uses the finite request timeout."""
        if url != self._endpoint:
            raise ValueError("policy transport endpoint does not match its bound endpoint")
        _validate_seconds(timeout_seconds, "timeout")
        self._bind_loop()
        self._check_open()
        request = httpx.Request(
            "POST",
            self._endpoint,
            headers=dict(headers),
            content=json.dumps(dict(payload), separators=(",", ":")).encode("utf-8"),
            extensions={"timeout": httpx.Timeout(float(timeout_seconds)).as_dict()},
        )
        # Only this request's owned await is cancelled, never an unrelated caller task.
        task = asyncio.create_task(self._post(request))
        self._active.add(task)
        try:
            return await task
        finally:
            self._active.discard(task)

    async def _post(self, request: httpx.Request) -> PolicyHttpResponse:
        response: httpx.Response | None = None
        try:
            if self._transport is None:
                context = self._ssl_context or ssl.create_default_context()
                # Low-level transport has no cookie jar, redirects, client credentials,
                # environment proxy routing or automatic connection retries.
                self._transport = httpx.AsyncHTTPTransport(
                    verify=context,
                    trust_env=False,
                    retries=0,
                    http1=True,
                    http2=False,
                    limits=self._limits,
                )
            response = await self._transport.handle_async_request(request)
            raw = bytearray()
            if not isinstance(response.stream, httpx.AsyncByteStream):
                raise _failure(
                    PolicyTransportFailureKind.INVALID_RESPONSE,
                    "policy router response must use an asynchronous byte stream",
                )
            # Iterate raw transport bytes directly: Response.aiter_raw() closes implicitly
            # at EOF, which would put that close outside our finite cleanup scope.
            async for chunk in response.stream:
                if len(raw) + len(chunk) > _MAX_RESPONSE_BYTES:
                    raise _failure(
                        PolicyTransportFailureKind.INVALID_RESPONSE,
                        "policy router response exceeded the bounded response size",
                    )
                raw.extend(chunk)
            payload_out: Mapping[str, object] | None = None
            if response.status_code in {200, 422}:
                try:
                    decoded = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    raise _failure(
                        PolicyTransportFailureKind.INVALID_RESPONSE,
                        "policy router returned invalid JSON",
                    ) from None
                if not isinstance(decoded, dict):
                    raise _failure(
                        PolicyTransportFailureKind.INVALID_RESPONSE,
                        "policy router response must be a JSON object",
                    )
                payload_out = cast(dict[str, object], decoded)
            return PolicyHttpResponse(
                status_code=response.status_code,
                retry_after=response.headers.get("retry-after"),
                payload=payload_out,
            )
        except httpx.TimeoutException:
            raise _failure(
                PolicyTransportFailureKind.TIMEOUT, "policy router request timed out"
            ) from None
        except (httpx.RequestError, OSError):
            raise _failure(
                PolicyTransportFailureKind.NETWORK, "policy router transport failed"
            ) from None
        except httpx.StreamError:
            raise _failure(
                PolicyTransportFailureKind.INVALID_RESPONSE, "policy router response stream failed"
            ) from None
        finally:
            if response is not None:
                await _bounded_close(response, preserve_error=sys.exception() is not None)

    async def aclose(self) -> None:
        """Stop admission, cancel only owned exchanges and close the pool exactly once."""
        self._bind_loop()
        if self._close_task is None:
            self._closed = True
            self._close_task = asyncio.create_task(self._shutdown())
            self._close_task.add_done_callback(_observe_close)
        # Caller cancellation cannot strand the finite, independently owned shutdown.
        await asyncio.shield(self._close_task)

    async def _shutdown(self) -> None:
        active = tuple(self._active)
        for task in active:
            task.cancel()
        try:
            async with asyncio.timeout(_CLEANUP_SECONDS):
                await asyncio.gather(*active, return_exceptions=True)
        except TimeoutError:
            raise _failure(
                PolicyTransportFailureKind.TIMEOUT, "policy transport shutdown timed out"
            ) from None
        finally:
            if self._transport is not None:
                await _bounded_close(self._transport, preserve_error=sys.exception() is not None)


def _observe_close(task: asyncio.Task[None]) -> None:
    """Retrieve a background close error without logging transport internals."""
    if not task.cancelled():
        task.exception()


async def _bounded_close(
    resource: httpx.Response | httpx.AsyncBaseTransport, *, preserve_error: bool
) -> None:
    try:
        async with asyncio.timeout(_CLEANUP_SECONDS):
            await resource.aclose()
    except Exception:
        if not preserve_error:
            raise _failure(
                PolicyTransportFailureKind.NETWORK, "policy transport cleanup failed"
            ) from None


def _failure(kind: PolicyTransportFailureKind, message: str) -> PolicyTransportFailure:
    return PolicyTransportFailure(kind, message)


def _validate_seconds(value: float, label: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not 0 < value <= 300
        or not math.isfinite(value)
    ):
        raise ValueError(f"policy {label} must be finite, positive and at most 300 seconds")


def _validate_endpoint(endpoint: str) -> None:
    if not isinstance(endpoint, str) or any(char.isspace() for char in endpoint):
        raise ValueError("policy endpoint must be a normalized HTTPS URL")
    try:
        parsed = urlsplit(endpoint)
        _ = parsed.port
        httpx.URL(endpoint)
    except (ValueError, httpx.InvalidURL):
        raise ValueError("policy endpoint is invalid") from None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("policy endpoint must use HTTPS without userinfo, query or fragment")
