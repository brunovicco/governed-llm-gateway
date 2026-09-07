"""Contract tests for pure governed service composition over the PC-8 runtime bundle."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from governed_llm_gateway_api import (
    GovernedProcessBootstrapPaths,
    GovernedServiceCompositionError,
    bootstrap_governed_process_runtime,
    compose_governed_gateway_services,
)
from governed_llm_gateway_core.adapters import load_complexity_routing_document
from governed_llm_gateway_core.application import InMemoryHealthTracker, PolicyProjectionDefaults
from governed_llm_gateway_core.domain.evidence_ranking import (
    EvidenceDrivenRankingPolicy,
    ScoreProvenanceMode,
)
from governed_llm_gateway_core.domain.ranking import (
    RankingPolicy,
    RankingWeights,
    StaticDeploymentScore,
    WorkloadRankingPolicy,
)

_ROOT = Path(__file__).resolve().parents[2]


class RecordingSecrets:
    """Resolve test-owned opaque values while recording every reference access."""

    def __init__(self, values: dict[str, str], events: list[str], label: str) -> None:
        self._values = values
        self._events = events
        self._label = label
        self.calls: list[str] = []

    def resolve(self, reference: str) -> str:
        self.calls.append(reference)
        self._events.append(f"{self._label}:{reference}")
        return self._values[reference]


def _registry_yaml() -> str:
    return """schema_version: "1.0"
catalog_version: "pc9-test"
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
      snapshot_version: "pc9-pricing"
    max_data_classification: confidential
    allowed_environments: [development]
    enabled: true
    source_date: "2026-09-07"
    catalog_version: "pc9-test"
"""


def _runtime_paths(tmp_path: Path) -> GovernedProcessBootstrapPaths:
    registry_path = tmp_path / "model_registry.yaml"
    provider_runtime_path = tmp_path / "provider_runtime.json"
    client_auth_path = tmp_path / "client_auth.json"
    policy_router_path = tmp_path / "policy_router.json"

    registry_path.write_text(_registry_yaml(), encoding="utf-8")
    provider_runtime_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "config_version": "pc9-test",
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
    client_auth_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "config_version": "pc9-test",
                "bindings": [
                    {
                        "client_id": "service-a",
                        "environment": "development",
                        "credential_reference": "GATEWAY_CLIENT_A_KEY",
                        "allowed_workloads": ["rag.answer"],
                        "minimum_risk_level": "low",
                        "minimum_data_classification": "public",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    policy_router_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "config_version": "pc9-test",
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
    return GovernedProcessBootstrapPaths(
        model_registry_path=registry_path,
        provider_runtime_path=provider_runtime_path,
        client_auth_path=client_auth_path,
        policy_router_path=policy_router_path,
    )


def _runtime(tmp_path: Path) -> tuple[object, list[str]]:
    events: list[str] = []
    client = RecordingSecrets(
        {"GATEWAY_CLIENT_A_KEY": "pc9-client-opaque"},
        events,
        "client",
    )
    policy = RecordingSecrets(
        {"POLICY_SERVICE_A_KEY": "pc9-policy-opaque"},
        events,
        "policy",
    )
    provider = RecordingSecrets(
        {"OPENAI_API_KEY": "pc9-provider-opaque"},
        events,
        "provider",
    )
    runtime = bootstrap_governed_process_runtime(
        _runtime_paths(tmp_path),
        client_secrets=client,
        policy_router_secrets=policy,
        provider_secrets=provider,
    )
    assert events == [
        "client:GATEWAY_CLIENT_A_KEY",
        "policy:POLICY_SERVICE_A_KEY",
        "provider:OPENAI_API_KEY",
    ]
    return runtime, events


def _weights() -> RankingWeights:
    return RankingWeights(
        quality=Decimal("0.40"),
        reliability=Decimal("0.20"),
        latency=Decimal("0.15"),
        cost=Decimal("0.10"),
        availability=Decimal("0.15"),
    )


def _workload() -> WorkloadRankingPolicy:
    return WorkloadRankingPolicy(
        workload="rag.answer",
        weights=_weights(),
        deployments=(
            StaticDeploymentScore(
                deployment_id="openai-primary",
                quality=Decimal("0.95"),
                reliability=Decimal("0.95"),
                latency=Decimal("0.80"),
                cost=Decimal("0.70"),
                availability=Decimal("0.99"),
                expected_latency_ms=800,
            ),
        ),
    )


def _static_ranking_policy() -> RankingPolicy:
    return RankingPolicy(
        schema_version="1.0",
        policy_version="pc9-static",
        score_snapshot_id="pc9-static",
        source_date=date(2026, 9, 7),
        workloads=(_workload(),),
    )


def _evidence_ranking_policy() -> EvidenceDrivenRankingPolicy:
    return EvidenceDrivenRankingPolicy(
        schema_version="1.1",
        policy_version="pc9-evidence",
        score_snapshot_id="pc9-evidence",
        source_date=date(2026, 9, 7),
        workloads=(_workload(),),
        score_provenance_mode=ScoreProvenanceMode.BENCHMARK_HYBRID,
        benchmark_snapshot_id="sha256:" + "a" * 64,
        promotion_evidence_id="sha256:" + "b" * 64,
    )


def _defaults() -> PolicyProjectionDefaults:
    return PolicyProjectionDefaults(
        max_latency_ms=10_000,
        max_cost_usd=Decimal("1.00"),
    )


def test_checked_in_inert_runtime_cannot_compose_active_services() -> None:
    events: list[str] = []
    empty = RecordingSecrets({}, events, "empty")
    runtime = bootstrap_governed_process_runtime(
        GovernedProcessBootstrapPaths(
            model_registry_path=_ROOT / "config/model_registry.yaml",
            provider_runtime_path=_ROOT / "config/providers/runtime.json",
            client_auth_path=_ROOT / "config/clients/auth.json",
            policy_router_path=_ROOT / "config/policy/router.json",
        ),
        client_secrets=empty,
        policy_router_secrets=empty,
        provider_secrets=empty,
    )

    with pytest.raises(GovernedServiceCompositionError, match="Policy Router adapter"):
        compose_governed_gateway_services(
            runtime,
            ranking_policy=_static_ranking_policy(),
            defaults=_defaults(),
        )

    assert events == []


def test_operational_composition_reuses_runtime_without_new_secret_reads(tmp_path: Path) -> None:
    runtime, events = _runtime(tmp_path)
    before = tuple(events)
    health = InMemoryHealthTracker()

    services = compose_governed_gateway_services(
        runtime,
        ranking_policy=_static_ranking_policy(),
        defaults=_defaults(),
        health=health,
    )

    assert tuple(events) == before
    assert services.health is health
    assert services.complexity_enabled is False
    assert services.complexity_route_service is None
    assert services.complexity_route_explain_coordinator is None
    assert services.complexity_generate_coordinator is None
    assert getattr(services.streaming_service, "_health") is health
    assert getattr(services.generate_coordinator, "_health") is health
    paths = {route.path for route in services.app.routes}
    assert "/v1/route/explain" in paths
    assert "/v1/generate" in paths


def test_complexity_configuration_rejects_static_ranking_without_secret_reads(
    tmp_path: Path,
) -> None:
    runtime, events = _runtime(tmp_path)
    before = tuple(events)
    complexity = load_complexity_routing_document(_ROOT / "config/routing/complexity.json")

    with pytest.raises(GovernedServiceCompositionError, match="evidence-driven"):
        compose_governed_gateway_services(
            runtime,
            ranking_policy=_static_ranking_policy(),
            defaults=_defaults(),
            complexity_routing=complexity,
        )

    assert tuple(events) == before


def test_evidence_driven_complexity_composes_complete_post_authorization_path(
    tmp_path: Path,
) -> None:
    runtime, events = _runtime(tmp_path)
    before = tuple(events)
    health = InMemoryHealthTracker()
    complexity = load_complexity_routing_document(_ROOT / "config/routing/complexity.json")

    services = compose_governed_gateway_services(
        runtime,
        ranking_policy=_evidence_ranking_policy(),
        defaults=_defaults(),
        complexity_routing=complexity,
        health=health,
    )

    assert tuple(events) == before
    assert services.complexity_enabled is True
    assert services.complexity_route_service is not None
    assert services.complexity_route_explain_coordinator is not None
    assert services.complexity_generate_coordinator is not None
    assert getattr(services.streaming_service, "_health") is health
    assert getattr(services.complexity_generate_coordinator, "_health") is health
