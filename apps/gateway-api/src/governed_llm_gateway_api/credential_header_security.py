"""HTTP credential-header shape hardening for the Gateway root application."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_GATEWAY_API_KEY_HEADER = b"x-gateway-api-key"


class GatewayCredentialHeaderMiddleware:
    """Reject ambiguous duplicate Gateway credential headers before request parsing."""

    def __init__(self, app: ASGIApp) -> None:
        """Bind the downstream ASGI application."""
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Allow zero or one credential header and reject two or more occurrences."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        occurrences = sum(
            1 for name, _value in scope["headers"] if name.lower() == _GATEWAY_API_KEY_HEADER
        )
        if occurrences <= 1:
            await self._app(scope, receive, send)
            return

        response = JSONResponse(
            status_code=400,
            content={"detail": {"code": "ambiguous_gateway_credential"}},
        )
        await response(scope, receive, send)
