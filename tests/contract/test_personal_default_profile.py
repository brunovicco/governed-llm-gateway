"""Credential-free contract tests for the operator's personal-default profile."""

from decimal import Decimal
from pathlib import Path

import pytest
from governed_llm_gateway_api import (
    GovernedDeploymentSettings,
    activate_governed_deployment,
)
from governed_llm_gateway_api.client_auth_json import load_gateway_client_auth_document
from governed_llm_gateway_api.operations_access_json import (
    load_operations_read_access_document,
    validate_operations_access_client_auth,
)
from governed_llm_gateway_core.adapters import (
    load_model_registry,
    load_policy_router_runtime_document,
    load_provider_runtime_document,
    validate_provider_runtime_registry,
)
from governed_llm_gateway_core.adapters.ranking_policy_yaml import load_ranking_policy

_ROOT = Path(__file__).resolve().parents[2]
_PROFILE_REL = Path("config") / "profiles" / "personal-default"
_PROFILE = _ROOT / _PROFILE_REL
_NVIDIA_DEPLOYMENT_ID = "nvidia-nemotron-3-super-dev"
_OPAQUE_ENV = {
    "GATEWAY_DEMO_API_KEY": "opaque-gateway-demo-value",
    "POLICY_ROUTER_DEMO_API_KEY": "opaque-policy-router-demo-value",
    "OPENAI_API_KEY": "opaque-openai-value",
    "GEMINI_API_KEY": "opaque-gemini-value",
    "ANTHROPIC_API_KEY": "opaque-anthropic-value",
    "NVIDIA_API_KEY": "opaque-nvidia-value",
    "GROQ_API_KEY": "opaque-groq-value",
    "OPENROUTER_API_KEY": "opaque-openrouter-value",
}


def _settings() -> GovernedDeploymentSettings:
    return GovernedDeploymentSettings(
        deployment_root=_ROOT,
        model_registry_path=_PROFILE_REL / "model_registry.yaml",
        provider_runtime_path=_PROFILE_REL / "provider_runtime.json",
        client_auth_path=_PROFILE_REL / "client_auth.json",
        policy_router_path=_PROFILE_REL / "policy_router.json",
        ranking_policy_path=_PROFILE_REL / "ranking_policy.yaml",
        operations_access_path=_PROFILE_REL / "operations_access.json",
        default_max_latency_ms=60_000,
        default_max_cost_usd=Decimal("0.05"),
    )


def test_profile_has_exact_bounded_provider_and_authority_shape() -> None:
    registry = load_model_registry(_PROFILE / "model_registry.yaml")
    provider_runtime = load_provider_runtime_document(_PROFILE / "provider_runtime.json")
    policy_runtime = load_policy_router_runtime_document(_PROFILE / "policy_router.json")
    client_auth = load_gateway_client_auth_document(_PROFILE / "client_auth.json")
    operations_access = load_operations_read_access_document(_PROFILE / "operations_access.json")

    validate_provider_runtime_registry(provider_runtime, registry)
    validate_operations_access_client_auth(operations_access, client_auth)

    providers = {deployment.provider for deployment in registry.deployments}
    model_groups = {deployment.model_group for deployment in registry.deployments}
    assert len(registry.deployments) == 6
    assert providers == {"google", "openai", "anthropic", "nvidia", "groq", "openrouter"}
    assert model_groups == {"balanced"}
    assert all(
        deployment.allowed_environments == frozenset({"development"})
        for deployment in registry.deployments
    )
    assert all(
        deployment.max_data_classification.value == "public" for deployment in registry.deployments
    )
    assert policy_runtime.runtime.enabled is True
    assert tuple(binding.client_id for binding in policy_runtime.runtime.bindings) == (
        "gateway-demo",
    )
    assert tuple(
        (principal.client_id, principal.environment)
        for principal in operations_access.policy.principals
    ) == (("gateway-demo", "development"),)


def test_nvidia_has_a_genuine_cost_preference_and_wins_deterministic_ranking() -> None:
    registry = load_model_registry(_PROFILE / "model_registry.yaml")
    ranking = load_ranking_policy(_PROFILE / "ranking_policy.yaml")
    workload = ranking.for_workload("rag.answer")

    nvidia_deployment = next(
        deployment
        for deployment in registry.deployments
        if deployment.deployment_id == _NVIDIA_DEPLOYMENT_ID
    )
    assert nvidia_deployment.pricing is not None
    assert nvidia_deployment.pricing.input_usd_per_million_tokens == Decimal("0")
    assert nvidia_deployment.pricing.output_usd_per_million_tokens == Decimal("0")

    nvidia_score = workload.score_for(_NVIDIA_DEPLOYMENT_ID)
    assert nvidia_score is not None
    nvidia_total = (
        nvidia_score.quality
        + nvidia_score.reliability
        + nvidia_score.latency
        + nvidia_score.cost
        + nvidia_score.availability
    )

    other_totals = []
    for deployment in registry.deployments:
        if deployment.deployment_id == _NVIDIA_DEPLOYMENT_ID:
            continue
        score = workload.score_for(deployment.deployment_id)
        assert score is not None
        other_totals.append(
            score.quality + score.reliability + score.latency + score.cost + score.availability
        )

    assert len(other_totals) == 5
    assert len(set(other_totals)) == 1
    assert nvidia_total > other_totals[0]


def test_profile_materializes_without_network_calls() -> None:
    services = activate_governed_deployment(_settings(), environ=_OPAQUE_ENV)

    paths = {getattr(route, "path", None) for route in services.app.routes}
    assert "/v1/generate" in paths
    assert "/v1/route/explain" in paths
    assert "/v1/ops/overview" in paths
    assert "/v1/ops/deployments" in paths
    assert services.complexity_enabled is False


@pytest.mark.parametrize("missing_reference", tuple(_OPAQUE_ENV))
def test_profile_fails_closed_on_missing_secret(missing_reference: str) -> None:
    environ = dict(_OPAQUE_ENV)
    del environ[missing_reference]

    with pytest.raises(RuntimeError):
        activate_governed_deployment(_settings(), environ=environ)
