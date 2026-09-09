"""HTTP request-size hardening scoped to route explanation."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_ROUTE_EXPLAIN_PATH = "/v1/route/explain"
MAX_ROUTE_EXPLAIN_REQUEST_BODY_BYTES = 8 * 1024 * 1024


class _RouteExplainRequestTooLarge(Exception):
    """Internal control-flow signal raised before route explanation can execute."""


class RouteExplainRequestBodyLimitMiddleware:
    """Reject oversized route-explanation JSON before request validation."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int = MAX_ROUTE_EXPLAIN_REQUEST_BODY_BYTES,
    ) -> None:
        """Bind one positive hard ceiling for the owned route-explanation endpoint."""
        if (
            isinstance(max_body_bytes, bool)
            or not isinstance(max_body_bytes, int)
            or max_body_bytes <= 0
        ):
            raise ValueError("route explanation request body limit must be a positive integer")
        self._app = app
        self._max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Enforce declared and actually received byte counts before parsing."""
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope["path"] != _ROUTE_EXPLAIN_PATH
        ):
            await self._app(scope, receive, send)
            return

        declared_length = _declared_content_length(scope)
        if declared_length is not None and declared_length > self._max_body_bytes:
            await _send_too_large(scope, receive, send)
            return

        received_bytes = 0
        response_started = False

        async def receive_limited() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self._max_body_bytes:
                    raise _RouteExplainRequestTooLarge
            return message

        async def send_tracked(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self._app(scope, receive_limited, send_tracked)
        except _RouteExplainRequestTooLarge:
            if response_started:
                raise
            await _send_too_large(scope, receive, send)


def _declared_content_length(scope: Scope) -> int | None:
    values = tuple(
        value for name, value in scope.get("headers", ()) if name.lower() == b"content-length"
    )
    if len(values) != 1:
        return None
    raw = values[0]
    if not raw or not raw.isdigit():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def _send_too_large(scope: Scope, receive: Receive, send: Send) -> None:
    response = JSONResponse(
        status_code=413,
        content={"detail": {"code": "route_explain_request_too_large"}},
    )
    await response(scope, receive, send)
