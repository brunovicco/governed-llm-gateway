"""HTTP security hardening scoped to authenticated Operations surfaces."""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_OPERATIONS_PATH_PREFIX = "/v1/ops/"
_OPERATIONS_CACHE_CONTROL = "no-store"


class OperationsNoStoreMiddleware:
    """Prevent authenticated Operations responses from being stored by HTTP caches."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap one ASGI application without changing non-Operations responses."""
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Attach no-store to every response under the owned Operations namespace."""
        if scope["type"] != "http" or not scope["path"].startswith(_OPERATIONS_PATH_PREFIX):
            await self._app(scope, receive, send)
            return

        async def send_no_store(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = _OPERATIONS_CACHE_CONTROL
            await send(message)

        await self._app(scope, receive, send_no_store)
