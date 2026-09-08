"""Contract tests for the first authenticated read-only Operations HTTP surface."""

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
    """Deterministic operations authorizer double with observable call order."""

    def __init__(self, outcome: str, events: list[str]) -> None:
        self._outcome = outcome
        self._events = events
        self.calls: list[str] = []

    async def authorize(self, *, api_key: str) -> GatewayClientIdentity:
        self.calls.append(api_key)
        self._events.append("authorize")
        if self._outcome == "invalid":
            raise ClientAuthenticationError("gateway credential rejected")
        if self._outcome == "denied":
            raise OperationsReadAuthorizationError()
        return GatewayClientIdentity(client_id="operations-console", environment="development")


class RecordingSnapshotReader:
    """Snapshot reader double that proves authorization occurs before descriptive reads."""

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
            raise RuntimeError("internal snapshot detail must not escape")
        return self._snapshot


def _deployment(
    deployment_id: str,
    status: HealthStatus,
    circuit_state: CircuitState,
) -> OperationsDeploymentSummary:
    return OperationsDeploymentSummary(
        deployment_id=deployment_id,
        provider="provider-hidden-from-overview",
        model_id="model-hidden-from-overview",
        model_group="general",
        api_family="test",
        enabled=True,
        capabilities=("text",),
        modalities=("text",),
        context_tokens=128_000,
        max_data_classification="internal",
        allowed_environments=("development",),
        pricing_snapshot_version="pricing-hidden-from-overview",
        health=DeploymentHealthSnapshot(
            deployment_id=deployment_id,
            status=status,
            circuit_state=circuit_state,
        ),
    )


def _snapshot(*, registry_deployment_count: int = 3) -> OperationsSnapshot:
    return OperationsSnapshot(
        registry=OperationsRegistrySummary(
            schema_version="1.0",
            catalog_version="catalog-v1",
            source_date=date(2026, 9, 7),
            digest="a" * 64,
            deployment_count=registry_deployment_count,
        ),
        ranking=OperationsRankingSummary(
            schema_version="1.1",
            policy_version="ranking-v1",
            source_date=date(2026, 9, 7),
            digest="b" * 64,
            score_snapshot_id="score-v1",
            score_provenance_mode="benchmark_hybrid",
            benchmark_snapshot_id="sha256:" + "c" * 64,
            promotion_evidence_id="sha256:" + "d" * 64,
            manual_override_id=None,
        ),
        deployments=(
            _deployment("healthy-hidden", HealthStatus.HEALTHY, CircuitState.CLOSED),
            _deployment("degraded-hidden", HealthStatus.DEGRADED, CircuitState.CLOSED),
            _deployment("unhealthy-hidden", HealthStatus.UNHEALTHY, CircuitState.OPEN),
        ),
        operational_evidence=OperationalEvidenceNotSupplied(),
    )


def _app(
    *,
    outcome: str = "allowed",
    snapshot: OperationsSnapshot | None = None,
    fail_snapshot: bool = False,
) -> tuple[FastAPI, RecordingAuthorizer, RecordingSnapshotReader, list[str]]:
    events: list[str] = []
    authorizer = RecordingAuthorizer(outcome, events)
    reader = RecordingSnapshotReader(snapshot or _snapshot(), events, fail=fail_snapshot)
    app = FastAPI()
    attach_operations_routes(app, access=authorizer, read_model=reader)
    return app, authorizer, reader, events


def test_missing_credential_returns_sanitized_401_before_authorization_or_snapshot() -> None:
    app, authorizer, reader, events = _app()

    response = TestClient(app).get("/v1/ops/overview")

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "invalid_gateway_credential"}}
    assert authorizer.calls == []
    assert reader.calls == 0
    assert events == []


def test_invalid_credential_returns_sanitized_401_without_snapshot() -> None:
    app, authorizer, reader, events = _app(outcome="invalid")

    response = TestClient(app).get(
        "/v1/ops/overview",
        headers={"X-Gateway-API-Key": "invalid-opaque"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "invalid_gateway_credential"}}
    assert authorizer.calls == ["invalid-opaque"]
    assert reader.calls == 0
    assert events == ["authorize"]


def test_authenticated_but_ungranted_credential_returns_403_without_snapshot() -> None:
    app, authorizer, reader, events = _app(outcome="denied")

    response = TestClient(app).get(
        "/v1/ops/overview",
        headers={"X-Gateway-API-Key": "valid-but-ungranted"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "operations_read_access_denied"}}
    assert authorizer.calls == ["valid-but-ungranted"]
    assert reader.calls == 0
    assert events == ["authorize"]


def test_granted_caller_is_authorized_before_bounded_snapshot_projection() -> None:
    app, authorizer, reader, events = _app()

    response = TestClient(app).get(
        "/v1/ops/overview",
        headers={"X-Gateway-API-Key": "granted-opaque"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "registry": {
            "schema_version": "1.0",
            "catalog_version": "catalog-v1",
            "source_date": "2026-09-07",
            "digest": "a" * 64,
            "deployment_count": 3,
        },
        "ranking": {
            "schema_version": "1.1",
            "policy_version": "ranking-v1",
            "source_date": "2026-09-07",
            "digest": "b" * 64,
            "score_snapshot_id": "score-v1",
            "score_provenance_mode": "benchmark_hybrid",
            "benchmark_snapshot_id": "sha256:" + "c" * 64,
            "promotion_evidence_id": "sha256:" + "d" * 64,
            "manual_override_id": None,
        },
        "health": {
            "scope": "process_local",
            "deployment_count": 3,
            "healthy": 1,
            "degraded": 1,
            "unhealthy": 1,
        },
        "operational_evidence": {"state": "not_supplied"},
    }
    assert authorizer.calls == ["granted-opaque"]
    assert reader.calls == 1
    assert events == ["authorize", "snapshot"]
    serialized = response.text
    assert "operations-console" not in serialized
    assert "healthy-hidden" not in serialized
    assert "degraded-hidden" not in serialized
    assert "unhealthy-hidden" not in serialized
    assert "provider-hidden-from-overview" not in serialized
    assert "model-hidden-from-overview" not in serialized
    assert "pricing-hidden-from-overview" not in serialized


def test_snapshot_runtime_failure_is_sanitized_as_503_after_authorization() -> None:
    app, _, reader, events = _app(fail_snapshot=True)

    response = TestClient(app).get(
        "/v1/ops/overview",
        headers={"X-Gateway-API-Key": "granted-opaque"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "operations_snapshot_unavailable"}}
    assert "internal snapshot detail" not in response.text
    assert reader.calls == 1
    assert events == ["authorize", "snapshot"]


def test_incomplete_health_aggregate_fails_closed_as_sanitized_503() -> None:
    app, _, reader, events = _app(snapshot=_snapshot(registry_deployment_count=4))

    response = TestClient(app).get(
        "/v1/ops/overview",
        headers={"X-Gateway-API-Key": "granted-opaque"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "operations_snapshot_unavailable"}}
    assert reader.calls == 1
    assert events == ["authorize", "snapshot"]


def test_duplicate_operations_route_attachment_fails_without_second_route() -> None:
    app, authorizer, reader, _ = _app()

    with pytest.raises(OperationsHttpCompositionError, match="already attached"):
        attach_operations_routes(app, access=authorizer, read_model=reader)

    paths = [route.path for route in app.routes if isinstance(route, APIRoute)]
    assert paths.count("/v1/ops/overview") == 1
