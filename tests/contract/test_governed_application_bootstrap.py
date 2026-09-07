"""Contract tests for routing-artifact validation before application secret materialization."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from governed_llm_gateway_api import (
    GovernedApplicationBootstrapPaths,
    GovernedGatewayServices,
    GovernedProcessBootstrapPaths,
    GovernedServiceCompositionError,
    bootstrap_governed_application_services,
    load_governed_application_artifacts,
)
from governed_llm_gateway_core.adapters import ComplexityRoutingDocumentError
from governed_llm_gateway_core.application import PolicyProjectionDefaults
from governed_llm_gateway_core.domain.ranking import RankingPolicyError

_ROOT = Path(__file__).resolve().parents[2]


class RecordingSecrets:
    """Record secret-reference access while returning test-owned opaque values."""

    def __init__(
        self,
        *,
        label: str,
        values: dict[str, str],
        events: list[str],
    ) -> None:
        self._label = label
        self._values = values
        self._events = events
        self.calls: list[str] = []

    def resolve(self, reference: str) -> str:
        self.calls.append(reference)
        self._events.append(f"{self._label}:{reference}")
        return self._values[reference]


def _registry_yaml() -> str:
    return """schema_version: "1.0"
catalog_version: "pc10-test"
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
      snapshot_version: "pc10-pricing"
    max_data_classification: internal
    allowed_environments: [development]
    enabled: true
    source_date: "2026-09-07"
    catalog_version: "pc10-test"
"""


def _provider_runtime_json() -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "config_version": "pc10-test",
            "bindings": [
                {
                    "provider": "openai",
                    "api_family": "openai-responses",
                    "credential_reference": "OPENAI_API_KEY",
                    "endpoint": "https://api.openai.example/v1/responses",
                }
            ],
        }
    )


def _client_auth_json() -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "config_version": "pc10-test",
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
    )


def _policy_router_json() -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "config_version": "pc10-test",
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
    )


def _ranking_yaml() -> str:
    return """schema_version: "1.0"
policy_version: "pc10-static-v1"
score_snapshot_id: "pc10-static-v1"
source_date: "2026-09-07"
workloads: {}
"""


def _paths(
    tmp_path: Path,
    *,
    ranking_text: str | None = None,
    complexity_text: str | None = None,
) -> GovernedApplicationBootstrapPaths:
    registry_path = tmp_path / "model_registry.yaml"
    provider_runtime_path = tmp_path / "provider_runtime.json"
    client_auth_path = tmp_path / "client_auth.json"
    policy_router_path = tmp_path / "policy_router.json"
    ranking_policy_path = tmp_path / "ranking_policy.yaml"

    registry_path.write_text(_registry_yaml(), encoding="utf-8")
    provider_runtime_path.write_text(_provider_runtime_json(), encoding="utf-8")
    client_auth_path.write_text(_client_auth_json(), encoding="utf-8")
    policy_router_path.write_text(_policy_router_json(), encoding="utf-8")
    ranking_policy_path.write_text(ranking_text or _ranking_yaml(), encoding="utf-8")

    complexity_path: Path | None = None
    if complexity_text is not None:
        complexity_path = tmp_path / "complexity.json"
        complexity_path.write_text(complexity_text, encoding="utf-8")

    return GovernedApplicationBootstrapPaths(
        process=GovernedProcessBootstrapPaths(
            model_registry_path=registry_path,
            provider_runtime_path=provider_runtime_path,
            client_auth_path=client_auth_path,
            policy_router_path=policy_router_path,
        ),
        ranking_policy_path=ranking_policy_path,
        complexity_routing_path=complexity_path,
    )


def _secrets() -> tuple[RecordingSecrets, RecordingSecrets, RecordingSecrets, list[str]]:
    events: list[str] = []
    client = RecordingSecrets(
        label="client",
        values={"GATEWAY_CLIENT_A_KEY": "pc10-client-opaque"},
        events=events,
    )
    policy = RecordingSecrets(
        label="policy",
        values={"POLICY_SERVICE_A_KEY": "pc10-policy-opaque"},
        events=events,
    )
    provider = RecordingSecrets(
        label="provider",
        values={"OPENAI_API_KEY": "pc10-provider-opaque"},
        events=events,
    )
    return client, policy, provider, events


def _bootstrap(
    paths: GovernedApplicationBootstrapPaths,
    client: RecordingSecrets,
    policy: RecordingSecrets,
    provider: RecordingSecrets,
) -> GovernedGatewayServices:
    return bootstrap_governed_application_services(
        paths,
        client_secrets=client,
        policy_router_secrets=policy,
        provider_secrets=provider,
        defaults=PolicyProjectionDefaults(
            max_latency_ms=15_000,
            max_cost_usd=Decimal("0.05"),
        ),
    )


def test_invalid_ranking_artifact_fails_before_all_secret_resolvers(tmp_path: Path) -> None:
    client, policy, provider, events = _secrets()
    paths = _paths(tmp_path, ranking_text="[]")

    with pytest.raises(RankingPolicyError):
        _bootstrap(paths, client, policy, provider)

    assert events == []
    assert client.calls == []
    assert policy.calls == []
    assert provider.calls == []


def test_invalid_complexity_artifact_fails_before_all_secret_resolvers(tmp_path: Path) -> None:
    client, policy, provider, events = _secrets()
    paths = _paths(tmp_path, complexity_text="[]")

    with pytest.raises(ComplexityRoutingDocumentError):
        _bootstrap(paths, client, policy, provider)

    assert events == []
    assert client.calls == []
    assert policy.calls == []
    assert provider.calls == []


def test_static_ranking_plus_explicit_complexity_fails_before_secret_access(
    tmp_path: Path,
) -> None:
    client, policy, provider, events = _secrets()
    paths = _paths(
        tmp_path,
        complexity_text=(_ROOT / "config/routing/complexity.json").read_text(encoding="utf-8"),
    )

    with pytest.raises(
        GovernedServiceCompositionError,
        match="complexity routing requires an explicit evidence-driven ranking policy",
    ):
        _bootstrap(paths, client, policy, provider)

    assert events == []
    assert client.calls == []
    assert policy.calls == []
    assert provider.calls == []


def test_complexity_is_opt_in_when_only_checked_in_file_exists(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    artifacts = load_governed_application_artifacts(paths)

    assert artifacts.complexity_enabled is False
    assert artifacts.complexity_routing is None
    assert (_ROOT / "config/routing/complexity.json").is_file()


def test_operational_bootstrap_resolves_secrets_then_delegates_to_pc9(tmp_path: Path) -> None:
    client, policy, provider, events = _secrets()
    paths = _paths(tmp_path)

    services = _bootstrap(paths, client, policy, provider)

    assert events == [
        "client:GATEWAY_CLIENT_A_KEY",
        "policy:POLICY_SERVICE_A_KEY",
        "provider:OPENAI_API_KEY",
    ]
    assert services.complexity_enabled is False
    assert services.generate_coordinator._health is services.health
    assert services.streaming_service._health is services.health
    route_paths = {route.path for route in services.app.routes if isinstance(route, APIRoute)}
    assert "/v1/route/explain" in route_paths
    assert "/v1/generate" in route_paths
