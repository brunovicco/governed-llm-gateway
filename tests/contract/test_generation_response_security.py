import asyncio
from typing import cast

import pytest
from governed_llm_gateway_api import GenerateCoordinator, RouteExplainCoordinator, create_gateway_app
from governed_llm_gateway_api.generation_response_security import GenerationNoStoreMiddleware
from governed_llm_gateway_api.generation_security import GenerationRequestBodyLimitMiddleware
from starlette.types import Message, Receive, Scope, Send


class RecordingResponseApp:
    def __init__(
        self,
        *,
        status: int = 204,
        headers: list[tuple[bytes, bytes]] | None = None,
        body: bytes = b"response-body",
    ) -> None:
        self.status = status
        self.headers = [] if headers is None else headers
        self.body = body
        self.calls = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive
        self.calls += 1
        await send(
            {
                "type": "http.response.start",
                "status": self.status,
                "headers": list(self.headers),
            }
        )
        await send({"type": "http.response.body", "body": self.body})


def _scope(
    *,
    path: str = "/v1/generate",
    method: str = "POST",
    content_length: int | None = None,
) -> Scope:
    headers: list[tuple[bytes, bytes]] = []
    if content_length is not None:
        headers.append((b"content-length", str(content_length).encode("ascii")))
    return cast(
        Scope,
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": headers,
            "client": None,
            "server": ("gateway.test", 443),
            "root_path": "",
        },
    )


def _run(app: object, scope: Scope, messages: list[Message] | None = None) -> list[Message]:
    pending = iter([] if messages is None else messages)
    sent: list[Message] = []

    async def receive() -> Message:
        try:
            return next(pending)
        except StopIteration:
            return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    async def scenario() -> None:
        await cast(GenerationNoStoreMiddleware, app)(scope, receive, send)

    asyncio.run(scenario())
    return sent


def _start(messages: list[Message]) -> Message:
    return next(message for message in messages if message["type"] == "http.response.start")


def _header_values(message: Message, name: bytes) -> list[bytes]:
    return [
        value
        for header_name, value in cast(list[tuple[bytes, bytes]], message.get("headers", []))
        if header_name.lower() == name.lower()
    ]


def _response_body(messages: list[Message]) -> bytes:
    return b"".join(
        cast(bytes, message.get("body", b""))
        for message in messages
        if message["type"] == "http.response.body"
    )


@pytest.mark.parametrize("status", [200, 401, 403, 422, 503])
def test_generation_responses_are_canonicalized_to_no_store(status: int) -> None:
    downstream = RecordingResponseApp(
        status=status,
        headers=[(b"cache-control", b"public, max-age=60"), (b"x-test", b"kept")],
    )
    middleware = GenerationNoStoreMiddleware(downstream)

    sent = _run(middleware, _scope())
    start = _start(sent)

    assert start["status"] == status
    assert _header_values(start, b"cache-control") == [b"no-store"]
    assert _header_values(start, b"x-test") == [b"kept"]
    assert _response_body(sent) == b"response-body"
    assert downstream.calls == 1


def test_generation_no_store_wraps_request_limit_rejection() -> None:
    downstream = RecordingResponseApp()
    body_limit = GenerationRequestBodyLimitMiddleware(downstream, max_body_bytes=8)
    middleware = GenerationNoStoreMiddleware(body_limit)

    sent = _run(
        middleware,
        _scope(content_length=9),
        [{"type": "http.request", "body": b"{}", "more_body": False}],
    )
    start = _start(sent)

    assert downstream.calls == 0
    assert start["status"] == 413
    assert _header_values(start, b"cache-control") == [b"no-store"]
    assert _response_body(sent) == b'{"detail":{"code":"generation_request_too_large"}}'


def test_non_generation_response_is_unchanged() -> None:
    downstream = RecordingResponseApp(headers=[(b"cache-control", b"public, max-age=60")])
    middleware = GenerationNoStoreMiddleware(downstream)

    sent = _run(middleware, _scope(path="/health"))
    start = _start(sent)

    assert _header_values(start, b"cache-control") == [b"public, max-age=60"]
    assert downstream.calls == 1


def test_gateway_composition_places_generation_no_store_outside_body_limit() -> None:
    app = create_gateway_app(
        cast(RouteExplainCoordinator, object()),
        cast(GenerateCoordinator, object()),
    )

    middleware_classes = tuple(cast(object, item.cls) for item in app.user_middleware)

    assert middleware_classes.count(GenerationNoStoreMiddleware) == 1
    assert middleware_classes.count(GenerationRequestBodyLimitMiddleware) == 1
    assert middleware_classes.index(GenerationNoStoreMiddleware) < middleware_classes.index(
        GenerationRequestBodyLimitMiddleware
    )
