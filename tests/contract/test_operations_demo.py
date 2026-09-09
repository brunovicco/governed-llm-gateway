"""Contract tests for the bounded operations-only local demo bootstrap."""

import inspect
import json
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from governed_llm_gateway_api import operations_demo
from governed_llm_gateway_api.client_auth import GatewayClientSecretResolutionError
from governed_llm_gateway_api.operations_demo import (
    OperationsDemoConfigurationError,
    OperationsDemoSettings,
    build_operations_demo_app,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_DEMO_API_KEY = "test-only-local-demo-credential"
_DEMO_ENV = {"GATEWAY_LOCAL_DEMO_API_KEY": _DEMO_API_KEY}
_EXPECTED_ROUTE_PATHS = {
    "/livez",
    "/readyz",
    "/v1/ops/deployments",
    "/v1/ops/overview",
}


def _settings() -> OperationsDemoSettings:
    return OperationsDemoSettings(repository_root=_REPOSITORY_ROOT)


def test_operations_demo_exposes_only_health_and_operations_routes() -> None:
    app = build_operations_demo_app(_settings(), environ=_DEMO_ENV)

    route_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}

    assert route_paths == _EXPECTED_ROUTE_PATHS
    assert all("route" not in path for path in route_paths)
    assert all("generate" not in path for path in route_paths)


def test_operations_demo_requires_existing_gateway_authentication_contract() -> None:
    client = TestClient(build_operations_demo_app(_settings(), environ=_DEMO_ENV))

    missing = client.get("/v1/ops/overview")
    wrong = client.get(
        "/v1/ops/overview",
        headers={"X-Gateway-API-Key": "wrong-test-only-credential"},
    )

    assert missing.status_code == 401
    assert missing.json() == {"detail": {"code": "invalid_gateway_credential"}}
    assert wrong.status_code == 401
    assert wrong.json() == {"detail": {"code": "invalid_gateway_credential"}}


def test_operations_demo_returns_empty_descriptive_baseline_for_granted_identity() -> None:
    client = TestClient(build_operations_demo_app(_settings(), environ=_DEMO_ENV))
    headers = {"X-Gateway-API-Key": _DEMO_API_KEY}

    overview = client.get("/v1/ops/overview", headers=headers)
    deployments = client.get("/v1/ops/deployments", headers=headers)

    assert overview.status_code == 200
    overview_payload = overview.json()
    assert overview_payload["registry"]["deployment_count"] == 0
    assert overview_payload["health"] == {
        "scope": "process_local",
        "deployment_count": 0,
        "healthy": 0,
        "degraded": 0,
        "unhealthy": 0,
    }
    assert overview_payload["operational_evidence"] == {"state": "not_supplied"}

    assert deployments.status_code == 200
    assert deployments.json() == {
        "health_scope": "process_local",
        "deployments": [],
    }


def test_operations_demo_fails_closed_without_runtime_demo_credential() -> None:
    with pytest.raises(GatewayClientSecretResolutionError) as exc_info:
        build_operations_demo_app(_settings(), environ={})

    assert "credential" in str(exc_info.value).lower()
    assert _DEMO_API_KEY not in str(exc_info.value)


def test_operations_demo_rejects_any_executable_baseline_shape() -> None:
    with pytest.raises(OperationsDemoConfigurationError):
        operations_demo._require_non_executable_baseline(
            registry_deployment_count=1,
            ranking_workload_count=0,
            provider_binding_count=0,
            policy_router_enabled=False,
            policy_router_endpoint=None,
            policy_router_binding_count=0,
        )

    with pytest.raises(OperationsDemoConfigurationError):
        operations_demo._require_non_executable_baseline(
            registry_deployment_count=0,
            ranking_workload_count=0,
            provider_binding_count=0,
            policy_router_enabled=True,
            policy_router_endpoint="https://policy.example.test",
            policy_router_binding_count=1,
        )


def test_operations_demo_never_imports_provider_or_policy_execution_materializers() -> None:
    source = inspect.getsource(operations_demo)
    forbidden = (
        "EnvironmentPolicyRouterSecretResolver",
        "EnvironmentProviderSecretResolver",
        "build_policy_router_adapter",
        "build_static_provider_resolver",
        "compose_governed_gateway_services",
        "materialize_governed_process_services",
    )

    assert all(name not in source for name in forbidden)


def test_local_demo_artifacts_store_references_and_grants_not_raw_credentials() -> None:
    client_auth = json.loads(
        (_REPOSITORY_ROOT / "examples/local-demo/client-auth.json").read_text(encoding="utf-8")
    )
    operations_access = json.loads(
        (_REPOSITORY_ROOT / "examples/local-demo/operations-access.json").read_text(
            encoding="utf-8"
        )
    )

    binding = client_auth["bindings"][0]
    assert binding["credential_reference"] == "GATEWAY_LOCAL_DEMO_API_KEY"
    assert "credential" not in binding
    assert operations_access["principals"] == [
        {
            "client_id": binding["client_id"],
            "environment": binding["environment"],
        }
    ]
