"""HTTP credential-header shape hardening for the Gateway root application."""

from starlette.types import ASGIApp, Receive, Scope, Send

from .credential_shape import is_valid_gateway_api_key
from .protocol_error import boundary_error_response

_GATEWAY_API_KEY_HEADER = b"x-gateway-api-key"
_PROTOCOL_ROUTES = frozenset({("POST", "/v1/messages"), ("POST", "/v1/responses")})
_GOVERNED_BODY_AUTH_ROUTES = frozenset(
    {
        ("POST", "/v1/generate"),
        ("POST", "/v1/route/explain"),
        ("POST", "/v1/chat/completions"),
        ("POST", "/v1/messages"),
        ("POST", "/v1/responses"),
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
            value for name, value in scope["headers"] if name.lower() == _GATEWAY_API_KEY_HEADER
        )
        if len(credential_values) > 1:
            response = boundary_error_response(
                scope["path"],
                status_code=400,
                code="ambiguous_gateway_credential",
            )
            await response(scope, receive, send)
            return

        if (
            len(credential_values) == 1
            and (scope["method"], scope["path"]) in _GOVERNED_BODY_AUTH_ROUTES
        ):
            try:
                api_key = credential_values[0].decode("ascii")
            except UnicodeDecodeError:
                api_key = None
            if not is_valid_gateway_api_key(api_key):
                response = boundary_error_response(
                    scope["path"],
                    status_code=401,
                    code="invalid_gateway_credential",
                )
                await response(scope, receive, send)
                return

        if (scope["method"], scope["path"]) in _PROTOCOL_ROUTES:
            for header_name in (b"authorization", b"x-api-key"):
                values = tuple(
                    value for name, value in scope["headers"] if name.lower() == header_name
                )
                if len(values) > 1:
                    response = boundary_error_response(
                        scope["path"],
                        status_code=400,
                        code="ambiguous_gateway_credential",
                    )
                    await response(scope, receive, send)
                    return
                if values and len(values[0]) > 4096:
                    response = boundary_error_response(
                        scope["path"],
                        status_code=401,
                        code="invalid_gateway_credential",
                    )
                    await response(scope, receive, send)
                    return

        await self._app(scope, receive, send)
