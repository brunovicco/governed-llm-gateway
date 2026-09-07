"""Contract tests for bounded process-only liveness and readiness surfaces."""

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from governed_llm_gateway_api.process_health import (
    ProcessHealthCompositionError,
    attach_process_health_routes,
)


def test_process_health_routes_return_only_bounded_status_payloads() -> None:
    app = FastAPI()
    attach_process_health_routes(app)
    client = TestClient(app)

    live = client.get("/livez")
    ready = client.get("/readyz")

    assert live.status_code == 200
    assert live.json() == {"status": "live"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


def test_duplicate_process_health_attachment_fails_closed() -> None:
    app = FastAPI()
    attach_process_health_routes(app)

    with pytest.raises(
        ProcessHealthCompositionError,
        match="process health route already attached",
    ):
        attach_process_health_routes(app)


def test_existing_health_path_conflict_fails_before_partial_attachment() -> None:
    app = FastAPI()

    @app.get("/readyz")
    async def existing_ready() -> dict[str, str]:
        return {"status": "existing"}

    with pytest.raises(ProcessHealthCompositionError, match="/readyz"):
        attach_process_health_routes(app)

    route_paths = [route.path for route in app.routes if isinstance(route, APIRoute)]
    assert route_paths.count("/livez") == 0
    assert route_paths.count("/readyz") == 1
