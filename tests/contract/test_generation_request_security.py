import asyncio
from typing import cast

from governed_llm_gateway_api import GenerateCoordinator, RouteExplainCoordinator, create_gateway_app
from governed_llm_gateway_api.generation_security import (
    MAX_GENERATION_REQUEST_BODY_BYTES,
    GenerationRequestBodyLimitMiddleware,
)
from starlette.types import Message, Receive, Scope, Send


class RecordingApp:
    def __init__(self) -> None:
        self.calls = 0
        self.completed = 0
        self.bodies: list[bytes] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        del scope
        self.calls += 1
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        self.bodies.append(bytes(body))
        self.completed += 1
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


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


def _request(body: bytes, *, more_body: bool = False) -> Message:
    return {
        "type": "http.request",
        "body": body,
        "more_body": more_body,
    }


def _run(
    middleware: GenerationRequestBodyLimitMiddleware,
    scope: Scope,
    messages: list[Message],
) -> list[Message]:
    pending = iter(messages)
    sent: list[Message] = []

    async def receive() -> Message:
        try:
            return next(pending)
        except StopIteration:
            return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))
    return sent


def _status(messages: list[Message]) -> int:
    return next(
        cast(int, message["status"])
        for message in messages
        if message["type"] == "http.response.start"
    )


def _response_body(messages: list[Message]) -> bytes:
    return b"".join(
        cast(bytes, message.get("body", b""))
        for message in messages
        if message["type"] == "http.response.body"
    )


def test_declared_oversize_is_rejected_before_downstream_request_parsing() -> None:
    app = RecordingApp()
    middleware = GenerationRequestBodyLimitMiddleware(app, max_body_bytes=8)

    sent = _run(
        middleware,
        _scope(content_length=9),
        [_request(b"{}")],
    )

    assert app.calls == 0
    assert _status(sent) == 413
    assert _response_body(sent) == b'{"detail":{"code":"generation_request_too_large"}}'


def test_actual_streamed_bytes_cannot_bypass_missing_content_length() -> None:
    app = RecordingApp()
    middleware = GenerationRequestBodyLimitMiddleware(app, max_body_bytes=8)

    sent = _run(
        middleware,
        _scope(),
        [
            _request(b"1234", more_body=True),
            _request(b"56789"),
        ],
    )

    assert app.calls == 1
    assert app.completed == 0
    assert _status(sent) == 413
    assert _response_body(sent) == b'{"detail":{"code":"generation_request_too_large"}}'


def test_body_at_limit_reaches_downstream_unchanged() -> None:
    app = RecordingApp()
    middleware = GenerationRequestBodyLimitMiddleware(app, max_body_bytes=8)

    sent = _run(
        middleware,
        _scope(content_length=8),
        [
            _request(b"1234", more_body=True),
            _request(b"5678"),
        ],
    )

    assert app.calls == 1
    assert app.completed == 1
    assert app.bodies == [b"12345678"]
    assert _status(sent) == 204


def test_non_generation_routes_are_not_subject_to_generation_body_limit() -> None:
    app = RecordingApp()
    middleware = GenerationRequestBodyLimitMiddleware(app, max_body_bytes=8)

    sent = _run(
        middleware,
        _scope(path="/v1/route/explain", content_length=999),
        [_request(b"{}")],
    )

    assert app.completed == 1
    assert app.bodies == [b"{}"]
    assert _status(sent) == 204


def test_gateway_composition_installs_generation_limit_once() -> None:
    app = create_gateway_app(
        cast(RouteExplainCoordinator, object()),
        cast(GenerateCoordinator, object()),
    )

    installed = [
        item
        for item in app.user_middleware
        if item.cls is GenerationRequestBodyLimitMiddleware
    ]

    assert len(installed) == 1
    assert MAX_GENERATION_REQUEST_BODY_BYTES == 8 * 1024 * 1024
