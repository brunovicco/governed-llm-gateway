import asyncio
from typing import cast

from governed_llm_gateway_api import (
    GenerateCoordinator,
    RouteExplainCoordinator,
    create_gateway_app,
)
from governed_llm_gateway_api.route_explain_security import RouteExplainNoStoreMiddleware
from starlette.types import Message, Receive, Scope, Send


class RecordingResponseApp:
    def __init__(self, status: int) -> None:
        self.status = status
        self.calls = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive
        self.calls += 1
        await send(
            {
                "type": "http.response.start",
                "status": self.status,
                "headers": [(b"cache-control", b"public, max-age=60")],
            }
        )
        await send({"type": "http.response.body", "body": b'{"stable":true}'})


def _scope(path: str = "/v1/route/explain") -> Scope:
    return cast(
        Scope,
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": [],
            "client": None,
            "server": ("gateway.test", 443),
            "root_path": "",
        },
    )


def _run(
    middleware: RouteExplainNoStoreMiddleware,
    scope: Scope,
) -> list[Message]:
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))
    return sent


def _cache_control(messages: list[Message]) -> bytes | None:
    start = next(message for message in messages if message["type"] == "http.response.start")
    headers = cast(list[tuple[bytes, bytes]], start.get("headers", []))
    return next((value for name, value in headers if name.lower() == b"cache-control"), None)


def _body(messages: list[Message]) -> bytes:
    return b"".join(
        cast(bytes, message.get("body", b""))
        for message in messages
        if message["type"] == "http.response.body"
    )


def test_route_explain_responses_are_no_store_without_body_changes() -> None:
    for status in (200, 401, 422, 503):
        app = RecordingResponseApp(status)
        sent = _run(RouteExplainNoStoreMiddleware(app), _scope())

        assert app.calls == 1
        assert _cache_control(sent) == b"no-store"
        assert _body(sent) == b'{"stable":true}'


def test_unrelated_route_preserves_existing_cache_policy() -> None:
    app = RecordingResponseApp(200)
    sent = _run(RouteExplainNoStoreMiddleware(app), _scope("/health"))

    assert app.calls == 1
    assert _cache_control(sent) == b"public, max-age=60"
    assert _body(sent) == b'{"stable":true}'


def test_gateway_composition_installs_route_explain_no_store_once() -> None:
    app = create_gateway_app(
        cast(RouteExplainCoordinator, object()),
        cast(GenerateCoordinator, object()),
    )

    middleware_classes = tuple(cast(object, item.cls) for item in app.user_middleware)

    assert middleware_classes.count(RouteExplainNoStoreMiddleware) == 1
