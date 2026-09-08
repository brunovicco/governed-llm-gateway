"""Contract tests for the authenticated read-only Operations deployment catalog."""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from governed_llm_gateway_api.client_auth import GatewayClientIdentity
from governed_llm_gateway_api.operations_access import OperationsReadAuthorizationError
from governed_llm_gateway_api.operations_http import (
    OperationsHttpCompositionError,
    attach_operations_routes,
)
from governed_llm_gateway_api.route_explain import ClientAuthenticationError
from governed_llm_gateway_core.application import (
    OperationalEvidenceNotSupplied,
    OperationsDeploymentSummary,
    OperationsRankingSummary,
    OperationsRegistrySummary,
    OperationsSnapshot,
)
from governed_llm_gateway_core.domain.resilience import (
    CircuitState,
    DeploymentHealthSnapshot,
    HealthStatus,
)


class RecordingAuthorizer:
    """Operations authorization double with observable call ordering."""

    def __init__(self, outcome: str, events: list[str]) -> None:
        self._outcome = outcome
        self._events = events
        self.calls: list[str] = []

    async def authorize(self, *, api_key: str) -> GatewayClientIdentity:
        self.calls.append(api_key)
        self._events.append("authorize")
        if self._outcome == "invalid":
            raise ClientAuthenticationError("credential detail must not escape")
        if self._outcome == "denied":
            raise OperationsReadAuthorizationError()
        return GatewayClientIdentity(client_id="operator-a", environment="development")


class RecordingSnapshotReader:
    """Snapshot reader double proving authorization happens before catalog reads."""

    def __init__(
        self,
        snapshot: OperationsSnapshot,
        events: list[str],
        *,
        fail: bool = False,
    ) -> None:
        self._snapshot = snapshot
        self._events = events
        self._fail = fail
        self.calls = 0

    def snapshot(self) -> OperationsSnapshot:
        self.calls += 1
        self._events.append("snapshot")
        if self._fail:
            raise RuntimeError("private snapshot failure")
        return self._snapshot


def _deployment(
    *,
    deployment_id: str,
    provider: str,
    model_id: str,
    status: HealthStatus,
    circuit_state: CircuitState,
) -> OperationsDeploymentSummary:
    return OperationsDeploymentSummary(
        deployment_id=deployment_id,
        provider=provider,
        model_id=model_id,
        model_group="general",
        api_family="responses",
        enabled=True,
        capabilities=("structured_output", "text"),
        modalities=("text",),
        context_tokens=128_000,
        max_data_classification="internal",
        allowed_environments=("development", "staging"),
        pricing_snapshot_version="pricing-v1",
        health=DeploymentHealthSnapshot(
            deployment_id=deployment_id,
            status=status,
            circuit_state=circuit_state,
            request_count=7,
            success_count=5,
            transient_failure_count=2,
            timeout_count=1,
            rate_limit_count=1,
            server_error_count=0,
            consecutive_transient_failures=2,
            last_latency_ms=432,
        ),
    )


def _snapshot() -> OperationsSnapshot:
    return OperationsSnapshot(
        registry=OperationsRegistrySummary(
            schema_version="1.0",
            catalog_version="catalog-v2",
            source_date=date(2026, 9, 8),
            digest="a" * 64,
            deployment_count=2,
        ),
        ranking=OperationsRankingSummary(
            schema_version="1.0",
            policy_version="ranking-v1",
            source_date=date(2026, 9, 8),
            digest="b" * 64,
            score_snapshot_id="score-v1",
            score_provenance_mode=None,
            benchmark_snapshot_id=None,
            promotion_evidence_id=None,
            manual_override_id=None,
        ),
        deployments=(
            _deployment(
                deployment_id="zeta-primary",
                provider="provider-z",
                model_id="z/model-z",
                status=HealthStatus.DEGRADED,
                circuit_state=CircuitState.CLOSED,
            ),
            _deployment(
                deployment_id="alpha-fallback",
                provider="provider-a",
                model_id="a/model-a",
                status=HealthStatus.UNHEALTHY,
                circuit_state=CircuitState.OPEN,
            ),
        ),
        operational_evidence=OperationalEvidenceNotSupplied(),
    )


def _app(
    *,
    outcome: str = "allowed",
    fail_snapshot: bool = False,
) -> tuple[FastAPI, RecordingAuthorizer, RecordingSnapshotReader, list[str]]:
    events: list[str] = []
    authorizer = RecordingAuthorizer(outcome, events)
    reader = RecordingSnapshotReader(_snapshot(), events, fail=fail_snapshot)
    app = FastAPI()
    attach_operations_routes(app, access=authorizer, read_model=reader)
    return app, authorizer, reader, events


def test_missing_deployments_credential_returns_401_without_snapshot() -> None:
    app, authorizer, reader, events = _app()

    response = TestClient(app).get("/v1/ops/deployments")

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "invalid_gateway_credential"}}
    assert authorizer.calls == []
    assert reader.calls == 0
    assert events == []


@pytest.mark.parametrize(
    ("outcome", "status", "code"),
    [
        ("invalid", 401, "invalid_gateway_credential"),
        ("denied", 403, "operations_read_access_denied"),
    ],
)
def test_rejected_deployments_callers_cannot_read_snapshot(
    outcome: str,
    status: int,
    code: str,
) -> None:
    app, authorizer, reader, events = _app(outcome=outcome)

    response = TestClient(app).get(
        "/v1/ops/deployments",
        headers={"X-Gateway-API-Key": "opaque-credential"},
    )

    assert response.status_code == status
    assert response.json() == {"detail": {"code": code}}
    assert authorizer.calls == ["opaque-credential"]
    assert reader.calls == 0
    assert events == ["authorize"]


def test_granted_deployments_catalog_preserves_typed_order_and_bounded_fields() -> None:
    app, authorizer, reader, events = _app()

    response = TestClient(app).get(
        "/v1/ops/deployments",
        headers={"X-Gateway-API-Key": "granted-opaque"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "health_scope": "process_local",
        "deployments": [
            {
                "deployment_id": "zeta-primary",
                "provider": "provider-z",
                "model_id": "z/model-z",
                "model_group": "general",
                "api_family": "responses",
                "enabled": True,
                "capabilities": ["structured_output", "text"],
                "modalities": ["text"],
                "context_tokens": 128_000,
                "max_data_classification": "internal",
                "allowed_environments": ["development", "staging"],
                "pricing_snapshot_version": "pricing-v1",
                "health": {"status": "degraded", "circuit_state": "closed"},
            },
            {
                "deployment_id": "alpha-fallback",
                "provider": "provider-a",
                "model_id": "a/model-a",
                "model_group": "general",
                "api_family": "responses",
                "enabled": True,
                "capabilities": ["structured_output", "text"],
                "modalities": ["text"],
                "context_tokens": 128_000,
                "max_data_classification": "internal",
                "allowed_environments": ["development", "staging"],
                "pricing_snapshot_version": "pricing-v1",
                "health": {"status": "unhealthy", "circuit_state": "open"},
            },
        ],
    }
    assert authorizer.calls == ["granted-opaque"]
    assert reader.calls == 1
    assert events == ["authorize", "snapshot"]

    serialized = response.text
    for forbidden in (
        "request_count",
        "success_count",
        "transient_failure_count",
        "timeout_count",
        "rate_limit_count",
        "server_error_count",
        "consecutive_transient_failures",
        "last_latency_ms",
        "credential_reference",
        "operational_evidence",
        "operator-a",
    ):
        assert forbidden not in serialized


def test_deployments_snapshot_runtime_failure_is_sanitized_as_503() -> None:
    app, _, reader, events = _app(fail_snapshot=True)

    response = TestClient(app).get(
        "/v1/ops/deployments",
        headers={"X-Gateway-API-Key": "granted-opaque"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "operations_snapshot_unavailable"}}
    assert "private snapshot failure" not in response.text
    assert reader.calls == 1
    assert events == ["authorize", "snapshot"]


def test_preexisting_deployments_path_fails_before_partial_operations_attachment() -> None:
    events: list[str] = []
    authorizer = RecordingAuthorizer("allowed", events)
    reader = RecordingSnapshotReader(_snapshot(), events)
    app = FastAPI()

    @app.get("/v1/ops/deployments")
    async def existing_deployments() -> dict[str, str]:
        return {"status": "existing"}

    with pytest.raises(OperationsHttpCompositionError, match="/v1/ops/deployments"):
        attach_operations_routes(app, access=authorizer, read_model=reader)

    paths = [route.path for route in app.routes if isinstance(route, APIRoute)]
    assert paths.count("/v1/ops/deployments") == 1
    assert "/v1/ops/overview" not in paths
