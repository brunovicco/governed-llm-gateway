import asyncio
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from governed_llm_gateway_api import (
    GenerateCoordinator,
    RouteExplainCoordinator,
    create_gateway_app,
)
from governed_llm_gateway_api.content_type_security import GovernedJsonContentTypeMiddleware
from governed_llm_gateway_api.credential_header_security import (
    GatewayCredentialHeaderMiddleware,
)
from governed_llm_gateway_api.credential_shape import MAX_GATEWAY_API_KEY_LENGTH
from governed_llm_gateway_api.generation_response_security import GenerationNoStoreMiddleware
from governed_llm_gateway_api.operations_http import (
    OperationsReadAuthorizer,
    OperationsSnapshotReader,
    attach_operations_routes,
)
from governed_llm_gateway_api.operations_security import OperationsNoStoreMiddleware
from governed_llm_gateway_api.route_explain_security import RouteExplainNoStoreMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RecordingApp:
    def __init__(self) -> None:
        self.calls = 0
        self.headers: list[tuple[bytes, bytes]] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        del receive
        self.calls += 1
        self.headers = list(scope["headers"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})


def _scope(
    headers: list[tuple[bytes, bytes]],
    *,
    method: str = "POST",
    path: str = "/v1/generate",
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
            "headers": headers,
            "client": None,
            "server": ("gateway.test", 443),
            "root_path": "",
        },
    )


def _run(app: ASGIApp, scope: Scope) -> tuple[list[Message], int]:
    sent: list[Message] = []
    receive_calls = 0

    async def receive() -> Message:
        nonlocal receive_calls
        receive_calls += 1
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    async def scenario() -> None:
        await app(scope, receive, send)

    asyncio.run(scenario())
    return sent, receive_calls


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
    "headers",
    [
        [],
        [(b"x-gateway-api-key", b"one")],
    ],
)
def test_zero_or_one_gateway_credential_header_reaches_downstream_unchanged(
    headers: list[tuple[bytes, bytes]],
) -> None:
    downstream = RecordingApp()
    middleware = GatewayCredentialHeaderMiddleware(downstream)

    sent, receive_calls = _run(middleware, _scope(headers))

    assert _status(sent) == 204
    assert downstream.calls == 1
    assert downstream.headers == headers
    assert receive_calls == 0


def test_duplicate_gateway_credential_headers_fail_before_downstream_or_body_read() -> None:
    downstream = RecordingApp()
    middleware = GatewayCredentialHeaderMiddleware(downstream)

    sent, receive_calls = _run(
        middleware,
        _scope(
            [
                (b"x-gateway-api-key", b"first-secret-value"),
                (b"x-gateway-api-key", b"second-secret-value"),
            ]
        ),
    )

    assert _status(sent) == 400
    assert _response_body(sent) == b'{"detail":{"code":"ambiguous_gateway_credential"}}'
    assert downstream.calls == 0
    assert receive_calls == 0
    assert b"first-secret-value" not in _response_body(sent)
    assert b"second-secret-value" not in _response_body(sent)


@pytest.mark.parametrize("path", ["/v1/generate", "/v1/route/explain"])
@pytest.mark.parametrize(
    "api_key",
    [
        b"",
        b" leading-space",
        b"trailing-space ",
        b"x" * (MAX_GATEWAY_API_KEY_LENGTH + 1),
        b"\xff",
    ],
)
def test_malformed_single_credential_fails_before_downstream_or_body_read(
    path: str,
    api_key: bytes,
) -> None:
    downstream = RecordingApp()
    middleware = GatewayCredentialHeaderMiddleware(downstream)

    sent, receive_calls = _run(
        middleware,
        _scope([(b"x-gateway-api-key", api_key)], path=path),
    )

    assert _status(sent) == 401
    assert _response_body(sent) == b'{"detail":{"code":"invalid_gateway_credential"}}'
    assert downstream.calls == 0
    assert receive_calls == 0


def test_malformed_single_credential_does_not_change_unrelated_route_behavior() -> None:
    headers = [(b"x-gateway-api-key", b" malformed ")]
    downstream = RecordingApp()
    middleware = GatewayCredentialHeaderMiddleware(downstream)

    sent, receive_calls = _run(
        middleware,
        _scope(headers, method="GET", path="/health"),
    )

    assert _status(sent) == 204
    assert downstream.calls == 1
    assert downstream.headers == headers
    assert receive_calls == 0


def _full_gateway_app() -> FastAPI:
    return create_gateway_app(
        cast(RouteExplainCoordinator, object()),
        cast(GenerateCoordinator, object()),
    )


@pytest.mark.parametrize("path", ["/v1/generate", "/v1/route/explain"])
def test_full_gateway_rejects_duplicate_credentials_with_no_store(path: str) -> None:
    app = _full_gateway_app()

    response = TestClient(app).post(
        path,
        headers=[
            ("X-Gateway-API-Key", "first-secret-value"),
            ("X-Gateway-API-Key", "second-secret-value"),
            ("Content-Type", "application/json"),
        ],
        content=b"{}",
    )

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": {"code": "ambiguous_gateway_credential"}}
    assert "first-secret-value" not in response.text
    assert "second-secret-value" not in response.text


@pytest.mark.parametrize("path", ["/v1/generate", "/v1/route/explain"])
def test_full_gateway_rejects_malformed_credential_before_invalid_body(path: str) -> None:
    app = _full_gateway_app()
    malformed = "x" * (MAX_GATEWAY_API_KEY_LENGTH + 1)

    response = TestClient(app).post(
        path,
        headers={
            "X-Gateway-API-Key": malformed,
            "Content-Type": "application/json",
        },
        content=b"not-json",
    )

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": {"code": "invalid_gateway_credential"}}
    assert malformed not in response.text


@pytest.mark.parametrize("path", ["/v1/generate", "/v1/route/explain"])
def test_full_gateway_keeps_valid_shape_body_validation_behavior(path: str) -> None:
    app = _full_gateway_app()

    response = TestClient(app).post(
        path,
        headers={
            "X-Gateway-API-Key": "well-formed-but-unknown",
            "Content-Type": "application/json",
        },
        content=b"not-json",
    )

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


def test_configured_operations_reject_duplicate_credentials_with_no_store() -> None:
    app = _full_gateway_app()
    attach_operations_routes(
        app,
        access=cast(OperationsReadAuthorizer, object()),
        read_model=cast(OperationsSnapshotReader, object()),
    )

    response = TestClient(app).get(
        "/v1/ops/overview",
        headers=[
            ("X-Gateway-API-Key", "first-secret-value"),
            ("X-Gateway-API-Key", "second-secret-value"),
        ],
    )

    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": {"code": "ambiguous_gateway_credential"}}


def test_credential_shape_guard_is_inside_no_store_and_before_request_parsing() -> None:
    app = _full_gateway_app()

    middleware_classes = tuple(cast(object, item.cls) for item in app.user_middleware)

    assert middleware_classes.count(GatewayCredentialHeaderMiddleware) == 1
    credential_index = middleware_classes.index(GatewayCredentialHeaderMiddleware)
    assert middleware_classes.index(GenerationNoStoreMiddleware) < credential_index
    assert middleware_classes.index(RouteExplainNoStoreMiddleware) < credential_index
    assert credential_index < middleware_classes.index(GovernedJsonContentTypeMiddleware)

    attach_operations_routes(
        app,
        access=cast(OperationsReadAuthorizer, object()),
        read_model=cast(OperationsSnapshotReader, object()),
    )
    operations_classes = tuple(cast(object, item.cls) for item in app.user_middleware)
    assert operations_classes.index(OperationsNoStoreMiddleware) < operations_classes.index(
        GatewayCredentialHeaderMiddleware
    )
