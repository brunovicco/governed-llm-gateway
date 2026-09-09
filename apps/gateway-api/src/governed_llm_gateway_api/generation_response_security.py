"""HTTP cache hardening scoped to governed generation responses."""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_GENERATION_PATH = "/v1/generate"


class GenerationNoStoreMiddleware:
    """Prevent storage of generation responses without changing their bodies."""

    def __init__(self, app: ASGIApp) -> None:
        """Bind the downstream ASGI application."""
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Attach no-store to responses for the exact governed generation path."""
        if scope["type"] != "http" or scope["path"] != _GENERATION_PATH:
            await self._app(scope, receive, send)
            return

        async def send_no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
            await send(message)

        await self._app(scope, receive, send_no_store)
