"""Atomic composition contracts for the owned Operations HTTP route set."""

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from governed_llm_gateway_api.client_auth import GatewayClientIdentity
from governed_llm_gateway_api.operations_http import OperationsHttpCompositionError, attach_operations_routes
from governed_llm_gateway_core.application import OperationsSnapshot


class NeverCalledAuthorizer:
    """Composition-only authorizer double."""

    async def authorize(self, *, api_key: str) -> GatewayClientIdentity:
        raise AssertionError(f"authorization must not run during composition: {api_key}")


class NeverCalledSnapshotReader:
    """Composition-only snapshot-reader double."""

    def snapshot(self) -> OperationsSnapshot:
        raise AssertionError("snapshot must not run during composition")


@pytest.mark.parametrize("conflicting_path", ["/v1/ops/overview", "/v1/ops/deployments"])
def test_owned_operations_path_conflict_fails_before_partial_attachment(
    conflicting_path: str,
) -> None:
    app = FastAPI()

    async def preexisting_route() -> dict[str, str]:
        return {"status": "preexisting"}

    app.add_api_route(conflicting_path, preexisting_route, methods=["GET"])
    existing_paths = [route.path for route in app.routes if isinstance(route, APIRoute)]

    with pytest.raises(OperationsHttpCompositionError, match="already attached"):
        attach_operations_routes(
            app,
            access=NeverCalledAuthorizer(),
            read_model=NeverCalledSnapshotReader(),
        )

    paths = [route.path for route in app.routes if isinstance(route, APIRoute)]
    assert paths == existing_paths
