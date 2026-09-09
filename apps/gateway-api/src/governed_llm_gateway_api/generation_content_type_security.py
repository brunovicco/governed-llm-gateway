"""Request media-type hardening for governed generation."""

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_GENERATE_PATH = "/v1/generate"
_JSON_MEDIA_TYPE = "application/json"


class GenerationContentTypeMiddleware:
    """Require an explicit JSON media type before generation request parsing."""

    def __init__(self, app: ASGIApp) -> None:
        """Bind the downstream ASGI application."""
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reject unsupported generation media types before consuming the request body."""
        if (
            scope["type"] != "http"
            or scope["path"] != _GENERATE_PATH
            or scope["method"].upper() != "POST"
        ):
            await self._app(scope, receive, send)
            return

        content_type = Headers(scope=scope).get("content-type")
        if not _is_application_json(content_type):
            response = JSONResponse(
                status_code=415,
                content={"detail": {"code": "unsupported_generation_media_type"}},
            )
            await response(scope, receive, send)
            return

        await self._app(scope, receive, send)


def _is_application_json(content_type: str | None) -> bool:
    if content_type is None:
        return False
    media_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    return media_type == _JSON_MEDIA_TYPE
