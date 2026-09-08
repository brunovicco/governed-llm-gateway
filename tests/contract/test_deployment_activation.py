"""Contract tests for deployment-owned activation settings above the staged bootstrap."""

import asyncio
import json
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from governed_llm_gateway_api import (
    GovernedDeploymentSettings,
    OperationsReadAccessDocumentError,
    OperationsReadAuthorizationError,
    activate_governed_deployment,
)
from governed_llm_gateway_core.domain.model_registry import ModelRegistryError
from governed_llm_gateway_core.domain.operational_evidence import (
    OperationalEvidenceError,
    OperationalEvidenceRecord,
    OperationalEvidenceSnapshot,
    canonical_operational_evidence_json,
    create_operational_evidence_snapshot,
)


class RecordingEnvironment(Mapping[str, str]):
    """Environment mapping that records every credential lookup attempt."""

    def __init__(self) -> None:
        self.lookups: list[str] = []

    def __getitem__(self, key: str) -> str:
        self.lookups.append(key)
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0


def _settings(
    root: Path,
    *,
    model_registry_path: Path = Path("config/model-registry.yaml"),
    provider_runtime_path: Path = Path("config/provider-runtime.json"),
    client_auth_path: Path = Path("config/client-auth.json"),
    policy_router_path: Path = Path("config/policy-router.json"),
    ranking_policy_path: Path | None = Path("config/ranking.yaml"),
    approved_ranking_artifact_path: Path | None = None,
    expected_ranking_artifact_id: str | None = None,
    complexity_routing_path: Path | None = None,
    operations_access_path: Path | None = None,
    operational_evidence_path: Path | None = None,
    default_max_latency_ms: int = 5_000,
    default_max_cost_usd: Decimal = Decimal("1.25"),
) -> GovernedDeploymentSettings:
    return GovernedDeploymentSettings(
        deployment_root=root,
        model_registry_path=model_registry_path,
        provider_runtime_path=provider_runtime_path,
        client_auth_path=client_auth_path,
        policy_router_path=policy_router_path,
        ranking_policy_path=ranking_policy_path,
        approved_ranking_artifact_path=approved_ranking_artifact_path,
        expected_ranking_artifact_id=expected_ranking_artifact_id,
        complexity_routing_path=complexity_routing_path,
        operations_access_path=operations_access_path,
        operational_evidence_path=operational_evidence_path,
        default_max_latency_ms=default_max_latency_ms,
        default_max_cost_usd=default_max_cost_usd,
    )


def _write_valid_static_deployment(root: Path) -> None:
    config = root / "config"
    config.mkdir()
    (config / "model-registry.yaml").write_text(
        """schema_version: "1.0"
catalog_version: "pc12-test"
source_date: "2026-09-07"
deployments:
  openai-primary:
    provider: openai
    model_id: openai/test-model
    model_group: general
    api_family: openai-responses
    capabilities:
      text: true
      vision: false
      tool_calling: true
      structured_output: true
      streaming: true
    context_tokens: 128000
    modalities: [text]
    pricing:
      input_usd_per_million_tokens: "1.00"
      output_usd_per_million_tokens: "2.00"
      source_date: "2026-09-07"
      snapshot_version: "pc12-pricing"
    max_data_classification: internal
    allowed_environments: [development]
    enabled: true
    source_date: "2026-09-07"
    catalog_version: "pc12-test"
""",
        encoding="utf-8",
    )
    (config / "provider-runtime.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "config_version": "pc12-test",
                "bindings": [
                    {
                        "provider": "openai",
                        "api_family": "openai-responses",
                        "credential_reference": "OPENAI_API_KEY",
                        "endpoint": "https://api.openai.example/v1/responses",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (config / "client-auth.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "config_version": "pc12-test",
                "bindings": [
                    {
                        "client_id": "service-a",
                        "environment": "development",
                        "credential_reference": "GATEWAY_CLIENT_A_KEY",
                        "allowed_workloads": ["rag.answer"],
                        "minimum_risk_level": "high",
                        "minimum_data_classification": "confidential",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (config / "policy-router.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "config_version": "pc12-test",
                "enabled": True,
                "endpoint": "https://policy-router.example/route",
                "timeout_seconds": 5.0,
                "bindings": [
                    {
                        "client_id": "service-a",
                        "credential_reference": "POLICY_SERVICE_A_KEY",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (config / "ranking.yaml").write_text(
        """schema_version: "1.0"
policy_version: "pc12-static-v1"
score_snapshot_id: "pc12-static-v1"
source_date: "2026-09-07"
workloads: {}
""",
        encoding="utf-8",
    )


def _write_operations_access(root: Path, *, environment: str = "development") -> None:
    (root / "config/operations-access.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "config_version": "pc21-test",
                "principals": [
                    {
                        "client_id": "service-a",
                        "environment": environment,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_operational_evidence(
    root: Path,
    *,
    deployment_id: str = "openai-primary",
) -> OperationalEvidenceSnapshot:
    window_start = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
    window_end = window_start + timedelta(minutes=5)
    snapshot = create_operational_evidence_snapshot(
        snapshot_version="pc23-evidence-v1",
        collector_id="gateway-operational-evidence",
        collector_version="pc23-test",
        window_start=window_start,
        window_end=window_end,
        captured_at=window_end + timedelta(minutes=1),
        records=(
            OperationalEvidenceRecord(
                runtime_workload="rag.answer",
                deployment_id=deployment_id,
                gateway_request_count=1,
                provider_attempt_count=1,
                successful_provider_attempt_count=1,
                provider_error_count=0,
                rate_limit_error_count=0,
                timeout_count=0,
                fallback_request_count=0,
                provider_latency_p50_ms=120,
                provider_latency_p95_ms=120,
            ),
        ),
    )
    (root / "config/operational-evidence.json").write_text(
        canonical_operational_evidence_json(snapshot),
        encoding="utf-8",
    )
    return snapshot


def test_settings_resolve_relative_paths_deterministically(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    settings = _settings(
        root,
        complexity_routing_path=Path("config/complexity.json"),
        operations_access_path=Path("config/operations-access.json"),
        operational_evidence_path=Path("config/operational-evidence.json"),
    )

    first = settings.bootstrap_paths
    second = settings.bootstrap_paths

    assert first == second
    assert first.process.model_registry_path == root / "config/model-registry.yaml"
    assert first.process.provider_runtime_path == root / "config/provider-runtime.json"
    assert first.process.client_auth_path == root / "config/client-auth.json"
    assert first.process.policy_router_path == root / "config/policy-router.json"
    assert first.process.operations_access_path == root / "config/operations-access.json"
    assert first.ranking_policy_path == root / "config/ranking.yaml"
    assert first.complexity_routing_path == root / "config/complexity.json"
    assert first.operational_evidence_path == root / "config/operational-evidence.json"
    assert settings.projection_defaults.max_latency_ms == 5_000
    assert settings.projection_defaults.max_cost_usd == Decimal("1.25")


def test_relative_artifact_path_cannot_escape_deployment_root(tmp_path: Path) -> None:
    settings = _settings(tmp_path.resolve(), model_registry_path=Path("../registry.yaml"))

    with pytest.raises(ValueError, match="model_registry_path must not escape deployment_root"):
        _ = settings.bootstrap_paths


def test_operations_access_path_cannot_escape_deployment_root(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path.resolve(),
        operations_access_path=Path("../operations-access.json"),
    )

    with pytest.raises(ValueError, match="operations_access_path must not escape deployment_root"):
        _ = settings.bootstrap_paths


def test_operational_evidence_path_cannot_escape_deployment_root(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path.resolve(),
        operational_evidence_path=Path("../operational-evidence.json"),
    )

    with pytest.raises(
        ValueError,
        match="operational_evidence_path must not escape deployment_root",
    ):
        _ = settings.bootstrap_paths


def test_absolute_artifact_path_remains_explicit(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    external = (tmp_path.parent / "external-registry.yaml").resolve()
    settings = _settings(root, model_registry_path=external)

    assert settings.bootstrap_paths.process.model_registry_path == external


def test_ambiguous_ranking_source_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="static or approved, not both"):
        _settings(
            tmp_path.resolve(),
            approved_ranking_artifact_path=Path("approved.json"),
            expected_ranking_artifact_id="sha256:" + "a" * 64,
        )


def test_approved_ranking_requires_path_and_exact_expected_identity(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be supplied together"):
        _settings(
            tmp_path.resolve(),
            ranking_policy_path=None,
            approved_ranking_artifact_path=Path("approved.json"),
        )


def test_invalid_projection_defaults_fail_during_secret_free_settings_validation(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="default max_latency_ms must be positive"):
        _settings(tmp_path.resolve(), default_max_latency_ms=0)


def test_invalid_artifact_fails_before_environment_secret_lookup(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    config = root / "config"
    config.mkdir()
    (config / "model-registry.yaml").write_text("not-a-mapping\n", encoding="utf-8")
    environment = RecordingEnvironment()
    settings = _settings(root)

    with pytest.raises(ModelRegistryError, match="root must be a mapping"):
        activate_governed_deployment(settings, environ=environment)

    assert environment.lookups == []


def test_unknown_operations_principal_fails_before_environment_secret_lookup(
    tmp_path: Path,
) -> None:
    root = tmp_path.resolve()
    _write_valid_static_deployment(root)
    _write_operations_access(root, environment="production")
    environment = RecordingEnvironment()
    settings = _settings(
        root,
        operations_access_path=Path("config/operations-access.json"),
    )

    with pytest.raises(
        OperationsReadAccessDocumentError,
        match="must reference configured Gateway client identities",
    ):
        activate_governed_deployment(settings, environ=environment)

    assert environment.lookups == []


def test_malformed_operational_evidence_fails_before_environment_secret_lookup(
    tmp_path: Path,
) -> None:
    root = tmp_path.resolve()
    _write_valid_static_deployment(root)
    (root / "config/operational-evidence.json").write_text("not-json", encoding="utf-8")
    environment = RecordingEnvironment()

    with pytest.raises(OperationalEvidenceError, match="not valid JSON"):
        activate_governed_deployment(
            _settings(
                root,
                operational_evidence_path=Path("config/operational-evidence.json"),
            ),
            environ=environment,
        )

    assert environment.lookups == []


def test_unknown_evidence_deployment_fails_before_environment_secret_lookup(
    tmp_path: Path,
) -> None:
    root = tmp_path.resolve()
    _write_valid_static_deployment(root)
    _write_operational_evidence(root, deployment_id="retired-deployment")
    environment = RecordingEnvironment()

    with pytest.raises(OperationalEvidenceError, match="active model registry"):
        activate_governed_deployment(
            _settings(
                root,
                operational_evidence_path=Path("config/operational-evidence.json"),
            ),
            environ=environment,
        )

    assert environment.lookups == []


def test_omitted_operations_access_materializes_deny_all_policy(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    _write_valid_static_deployment(root)
    services = activate_governed_deployment(
        _settings(root),
        environ={
            "GATEWAY_CLIENT_A_KEY": "pc12-client-opaque",
            "POLICY_SERVICE_A_KEY": "pc12-policy-opaque",
            "OPENAI_API_KEY": "pc12-provider-opaque",
        },
    )

    with pytest.raises(OperationsReadAuthorizationError, match="operations read access denied"):
        asyncio.run(services.operations_read_access.authorize(api_key="pc12-client-opaque"))

    response = TestClient(services.app).get(
        "/v1/ops/overview",
        headers={"X-Gateway-API-Key": "pc12-client-opaque"},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": {"code": "operations_read_access_denied"}}


def test_configured_operations_access_authorizes_exact_runtime_principal(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    _write_valid_static_deployment(root)
    _write_operations_access(root)
    services = activate_governed_deployment(
        _settings(
            root,
            operations_access_path=Path("config/operations-access.json"),
        ),
        environ={
            "GATEWAY_CLIENT_A_KEY": "pc12-client-opaque",
            "POLICY_SERVICE_A_KEY": "pc12-policy-opaque",
            "OPENAI_API_KEY": "pc12-provider-opaque",
        },
    )

    identity = asyncio.run(services.operations_read_access.authorize(api_key="pc12-client-opaque"))

    assert identity.client_id == "service-a"
    assert identity.environment == "development"
    route_paths = {route.path for route in services.app.routes if isinstance(route, APIRoute)}
    operations_paths = {path for path in route_paths if path.startswith("/v1/ops")}
    assert operations_paths == {"/v1/ops/overview"}

    response = TestClient(services.app).get(
        "/v1/ops/overview",
        headers={"X-Gateway-API-Key": "pc12-client-opaque"},
    )
    assert response.status_code == 200
    assert response.json()["registry"]["deployment_count"] == 1
    assert response.json()["health"] == {
        "scope": "process_local",
        "deployment_count": 1,
        "healthy": 1,
        "degraded": 0,
        "unhealthy": 0,
    }
    assert response.json()["operational_evidence"] == {"state": "not_supplied"}


def test_configured_operational_evidence_is_bound_to_authenticated_overview(
    tmp_path: Path,
) -> None:
    root = tmp_path.resolve()
    _write_valid_static_deployment(root)
    _write_operations_access(root)
    expected = _write_operational_evidence(root)
    services = activate_governed_deployment(
        _settings(
            root,
            operations_access_path=Path("config/operations-access.json"),
            operational_evidence_path=Path("config/operational-evidence.json"),
        ),
        environ={
            "GATEWAY_CLIENT_A_KEY": "pc12-client-opaque",
            "POLICY_SERVICE_A_KEY": "pc12-policy-opaque",
            "OPENAI_API_KEY": "pc12-provider-opaque",
        },
    )

    bound = services.operations_snapshot_reader.operational_evidence
    assert bound is not None
    assert bound.evidence_id == expected.evidence_id
    assert (
        services.operations_snapshot_reader.snapshot().operational_evidence.state.value
        == "available"
    )

    response = TestClient(services.app).get(
        "/v1/ops/overview",
        headers={"X-Gateway-API-Key": "pc12-client-opaque"},
    )
    assert response.status_code == 200
    assert response.json()["operational_evidence"] == {"state": "available"}


def test_valid_settings_delegate_to_existing_governed_service_graph(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    _write_valid_static_deployment(root)
    settings = _settings(root)
    environment = {
        "GATEWAY_CLIENT_A_KEY": "pc12-client-opaque",
        "POLICY_SERVICE_A_KEY": "pc12-policy-opaque",
        "OPENAI_API_KEY": "pc12-provider-opaque",
    }

    services = activate_governed_deployment(settings, environ=environment)

    route_paths = {route.path for route in services.app.routes if isinstance(route, APIRoute)}
    assert "/v1/route/explain" in route_paths
    assert "/v1/generate" in route_paths
    assert "/v1/ops/overview" in route_paths
    assert services.complexity_enabled is False
    assert services.generate_coordinator._health is services.health
    assert services.streaming_service._health is services.health
