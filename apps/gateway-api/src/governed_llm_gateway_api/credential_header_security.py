"""HTTP credential-header shape hardening for the Gateway root application."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .credential_shape import is_valid_gateway_api_key

_GATEWAY_API_KEY_HEADER = b"x-gateway-api-key"
_GOVERNED_BODY_AUTH_ROUTES = frozenset(
    {
        ("POST", "/v1/generate"),
        ("POST", "/v1/route/explain"),
    }
)


class GatewayCredentialHeaderMiddleware:
    """Reject ambiguous or structurally invalid governed request credentials early."""

    def __init__(self, app: ASGIApp) -> None:
        """Bind the downstream ASGI application."""
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Validate credential-header shape without resolving authentication authority."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        credential_values = tuple(
            value
            for name, value in scope["headers"]
            if name.lower() == _GATEWAY_API_KEY_HEADER
        )
        if len(credential_values) > 1:
            response = JSONResponse(
                status_code=400,
                content={"detail": {"code": "ambiguous_gateway_credential"}},
            )
            await response(scope, receive, send)
            return

        if len(credential_values) == 1 and (
            scope["method"],
            scope["path"],
        ) in _GOVERNED_BODY_AUTH_ROUTES:
            try:
                api_key = credential_values[0].decode("ascii")
            except UnicodeDecodeError:
                api_key = None
            if not is_valid_gateway_api_key(api_key):
                response = JSONResponse(
                    status_code=401,
                    content={"detail": {"code": "invalid_gateway_credential"}},
                )
                await response(scope, receive, send)
                return

        await self._app(scope, receive, send)
