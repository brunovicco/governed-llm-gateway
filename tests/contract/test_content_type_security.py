import asyncio
from typing import cast

import pytest
from fastapi.testclient import TestClient
from governed_llm_gateway_api import (
    GenerateCoordinator,
    RouteExplainCoordinator,
    create_gateway_app,
)
from governed_llm_gateway_api.content_type_security import GovernedJsonContentTypeMiddleware
from governed_llm_gateway_api.generation_response_security import GenerationNoStoreMiddleware
from governed_llm_gateway_api.generation_security import GenerationRequestBodyLimitMiddleware
from governed_llm_gateway_api.route_explain_request_security import (
    RouteExplainRequestBodyLimitMiddleware,
)
from governed_llm_gateway_api.route_explain_security import RouteExplainNoStoreMiddleware
from starlette.types import Message, Receive, Scope, Send


class RecordingApp:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        del scope, receive
        self.calls += 1
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


def _scope(
    *,
    path: str = "/v1/generate",
    method: str = "POST",
    content_types: tuple[bytes, ...] = (),
) -> Scope:
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
            "headers": [(b"content-type", value) for value in content_types],
            "client": None,
            "server": ("gateway.test", 443),
            "root_path": "",
        },
    )


def _run(middleware: GovernedJsonContentTypeMiddleware, scope: Scope) -> list[Message]:
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"{}", "more_body": False}

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


@pytest.mark.parametrize("path", ["/v1/generate", "/v1/route/explain"])
@pytest.mark.parametrize(
    "content_types",
    [
        (),
        (b"text/plain",),
        (b"application/x-www-form-urlencoded",),
        (b"multipart/form-data; boundary=test",),
        (b"application/+json",),
        (b"application/vnd example+json",),
        (b"application/json", b"application/json"),
    ],
)
def test_governed_posts_reject_missing_ambiguous_or_non_json_media_types(
    path: str,
    content_types: tuple[bytes, ...],
) -> None:
    downstream = RecordingApp()
    middleware = GovernedJsonContentTypeMiddleware(downstream)

    sent = _run(middleware, _scope(path=path, content_types=content_types))

    assert downstream.calls == 0
    assert _status(sent) == 415
    assert _response_body(sent) == b'{"detail":{"code":"unsupported_media_type"}}'


@pytest.mark.parametrize(
    "content_type",
    [
        b"application/json",
        b"application/json; charset=utf-8",
        b"Application/JSON; Charset=UTF-8",
        b"application/vnd.example+json",
        b"application/problem+json; charset=utf-8",
    ],
)
@pytest.mark.parametrize("path", ["/v1/generate", "/v1/route/explain"])
def test_json_compatible_media_types_reach_downstream_unchanged(
    path: str,
    content_type: bytes,
) -> None:
    downstream = RecordingApp()
    middleware = GovernedJsonContentTypeMiddleware(downstream)

    sent = _run(middleware, _scope(path=path, content_types=(content_type,)))

    assert downstream.calls == 1
    assert _status(sent) == 204


def test_non_post_and_unrelated_routes_are_not_subject_to_json_media_type_gate() -> None:
    downstream = RecordingApp()
    middleware = GovernedJsonContentTypeMiddleware(downstream)

    unrelated = _run(middleware, _scope(path="/health"))
    get_generation = _run(middleware, _scope(method="GET"))

    assert downstream.calls == 2
    assert _status(unrelated) == 204
    assert _status(get_generation) == 204


@pytest.mark.parametrize("path", ["/v1/generate", "/v1/route/explain"])
def test_composed_gateway_returns_no_store_on_media_type_rejection(path: str) -> None:
    app = create_gateway_app(
        cast(RouteExplainCoordinator, object()),
        cast(GenerateCoordinator, object()),
    )

    response = TestClient(app).post(path, content=b"{}")

    assert response.status_code == 415
    assert response.json() == {"detail": {"code": "unsupported_media_type"}}
    assert response.headers["cache-control"] == "no-store"


def test_gateway_composition_places_media_type_gate_inside_no_store_and_outside_body_limits() -> None:
    app = create_gateway_app(
        cast(RouteExplainCoordinator, object()),
        cast(GenerateCoordinator, object()),
    )
    middleware_classes = tuple(cast(object, item.cls) for item in app.user_middleware)

    content_type_index = middleware_classes.index(GovernedJsonContentTypeMiddleware)

    assert middleware_classes.index(GenerationNoStoreMiddleware) < content_type_index
    assert middleware_classes.index(RouteExplainNoStoreMiddleware) < content_type_index
    assert content_type_index < middleware_classes.index(GenerationRequestBodyLimitMiddleware)
    assert content_type_index < middleware_classes.index(RouteExplainRequestBodyLimitMiddleware)
