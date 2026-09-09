import asyncio
from typing import cast

import pytest
from fastapi.testclient import TestClient
from governed_llm_gateway_api import (
    GenerateCoordinator,
    RouteExplainCoordinator,
    create_gateway_app,
)
from governed_llm_gateway_api.generation_content_type_security import (
    GenerationContentTypeMiddleware,
)
from governed_llm_gateway_api.generation_response_security import GenerationNoStoreMiddleware
from governed_llm_gateway_api.generation_security import GenerationRequestBodyLimitMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RecordingApp:
    def __init__(self) -> None:
        self.calls = 0
        self.bodies: list[bytes] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        del scope
        self.calls += 1
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        self.bodies.append(bytes(body))
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


def _scope(
    *,
    path: str = "/v1/generate",
    method: str = "POST",
    content_type: str | None = None,
) -> Scope:
    headers: list[tuple[bytes, bytes]] = []
    if content_type is not None:
        headers.append((b"content-type", content_type.encode("latin-1")))
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


def _run(app: ASGIApp, scope: Scope, body: bytes = b"{}") -> list[Message]:
    pending = iter([{"type": "http.request", "body": body, "more_body": False}])
    sent: list[Message] = []

    async def receive() -> Message:
        try:
            return cast(Message, next(pending))
        except StopIteration:
            return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(app(scope, receive, send))
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


@pytest.mark.parametrize(
    "content_type",
    [
        "application/json",
        "application/json; charset=utf-8",
        "Application/JSON ; charset=UTF-8",
    ],
)
def test_explicit_application_json_reaches_downstream_unchanged(content_type: str) -> None:
    downstream = RecordingApp()
    middleware = GenerationContentTypeMiddleware(downstream)

    sent = _run(middleware, _scope(content_type=content_type), body=b'{"value":1}')

    assert _status(sent) == 204
    assert downstream.calls == 1
    assert downstream.bodies == [b'{"value":1}']


@pytest.mark.parametrize(
    "content_type",
    [
        None,
        "text/plain",
        "application/x-www-form-urlencoded",
        "application/vnd.gateway+json",
    ],
)
def test_missing_or_unsupported_media_type_is_rejected_before_body_read(
    content_type: str | None,
) -> None:
    downstream = RecordingApp()
    middleware = GenerationContentTypeMiddleware(downstream)

    sent = _run(middleware, _scope(content_type=content_type))

    assert _status(sent) == 415
    assert _response_body(sent) == b'{"detail":{"code":"unsupported_generation_media_type"}}'
    assert downstream.calls == 0
    assert downstream.bodies == []


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/health", "POST"),
        ("/v1/generate", "GET"),
    ],
)
def test_media_type_guard_does_not_change_unrelated_route_or_method(
    path: str,
    method: str,
) -> None:
    downstream = RecordingApp()
    middleware = GenerationContentTypeMiddleware(downstream)

    sent = _run(middleware, _scope(path=path, method=method))

    assert _status(sent) == 204
    assert downstream.calls == 1


def test_gateway_composition_orders_no_store_content_type_and_body_limit() -> None:
    app = create_gateway_app(
        cast(RouteExplainCoordinator, object()),
        cast(GenerateCoordinator, object()),
    )

    middleware_classes = tuple(cast(object, item.cls) for item in app.user_middleware)

    assert middleware_classes.count(GenerationNoStoreMiddleware) == 1
    assert middleware_classes.count(GenerationContentTypeMiddleware) == 1
    assert middleware_classes.count(GenerationRequestBodyLimitMiddleware) == 1
    assert middleware_classes.index(GenerationNoStoreMiddleware) < middleware_classes.index(
        GenerationContentTypeMiddleware
    )
    assert middleware_classes.index(GenerationContentTypeMiddleware) < middleware_classes.index(
        GenerationRequestBodyLimitMiddleware
    )


def test_composed_gateway_returns_non_storable_415_before_generation_parsing() -> None:
    app = create_gateway_app(
        cast(RouteExplainCoordinator, object()),
        cast(GenerateCoordinator, object()),
    )
    client = TestClient(app)

    response = client.post(
        "/v1/generate",
        headers={"X-Gateway-API-Key": "gateway-key", "Content-Type": "text/plain"},
        content=b"{}",
    )

    assert response.status_code == 415
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": {"code": "unsupported_generation_media_type"}}


def test_composed_gateway_keeps_get_method_semantics() -> None:
    app = create_gateway_app(
        cast(RouteExplainCoordinator, object()),
        cast(GenerateCoordinator, object()),
    )

    response = TestClient(app).get("/v1/generate")

    assert response.status_code == 405
