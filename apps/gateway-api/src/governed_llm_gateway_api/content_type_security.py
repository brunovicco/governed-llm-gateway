"""HTTP media-type hardening for governed JSON request bodies."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_GOVERNED_JSON_PATHS = frozenset({"/v1/generate", "/v1/route/explain"})
_HTTP_TOKEN_BYTES = frozenset(b"!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyz")


class GovernedJsonContentTypeMiddleware:
    """Require an explicit JSON-compatible media type before governed body parsing."""

    def __init__(self, app: ASGIApp) -> None:
        """Bind the downstream ASGI application."""
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reject ambiguous or non-JSON governed POST requests before downstream parsing."""
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope["path"] not in _GOVERNED_JSON_PATHS
        ):
            await self._app(scope, receive, send)
            return

        if not _has_single_json_content_type(scope):
            response = JSONResponse(
                status_code=415,
                content={"detail": {"code": "unsupported_media_type"}},
            )
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)


def _has_single_json_content_type(scope: Scope) -> bool:
    values = tuple(
        value for name, value in scope.get("headers", ()) if name.lower() == b"content-type"
    )
    if len(values) != 1:
        return False

    media_type = values[0].split(b";", 1)[0].strip().lower()
    prefix = b"application/"
    if not media_type.startswith(prefix):
        return False

    subtype = media_type[len(prefix) :]
    if subtype == b"json":
        return True
    if not subtype.endswith(b"+json"):
        return False

    structured_name = subtype[: -len(b"+json")]
    return bool(structured_name) and all(byte in _HTTP_TOKEN_BYTES for byte in structured_name)
