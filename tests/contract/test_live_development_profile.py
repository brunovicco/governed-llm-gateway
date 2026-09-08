"""Credential-free contract tests for the explicit PC-33 live-development profile."""

from decimal import Decimal
from pathlib import Path

import pytest
from governed_llm_gateway_api import GovernedDeploymentSettings, activate_governed_deployment
from governed_llm_gateway_core.adapters import (
    load_model_registry,
    load_policy_router_runtime_document,
    load_provider_runtime_document,
    validate_provider_runtime_registry,
)
from governed_llm_gateway_core.adapters.ranking_policy_yaml import load_ranking_policy

_ROOT = Path(__file__).resolve().parents[2]
_PROFILE = _ROOT / "config" / "profiles" / "live-development"
_OPAQUE_ENV = {
    "GATEWAY_DEMO_API_KEY": "opaque-gateway-demo-value",
    "POLICY_ROUTER_DEMO_API_KEY": "opaque-policy-router-demo-value",
    "OPENAI_API_KEY": "opaque-openai-value",
    "GEMINI_API_KEY": "opaque-gemini-value",
}


def _settings() -> GovernedDeploymentSettings:
    return GovernedDeploymentSettings(
        deployment_root=_ROOT,
        model_registry_path=Path("config/profiles/live-development/model_registry.yaml"),
        provider_runtime_path=Path("config/profiles/live-development/provider_runtime.json"),
        client_auth_path=Path("config/profiles/live-development/client_auth.json"),
        policy_router_path=Path("config/profiles/live-development/policy_router.json"),
        ranking_policy_path=Path("config/profiles/live-development/ranking_policy.yaml"),
        default_max_latency_ms=60_000,
        default_max_cost_usd=Decimal("0.05"),
    )


def test_profile_has_exact_bounded_provider_and_authority_shape() -> None:
    registry = load_model_registry(_PROFILE / "model_registry.yaml")
    provider_runtime = load_provider_runtime_document(_PROFILE / "provider_runtime.json")
    policy_runtime = load_policy_router_runtime_document(_PROFILE / "policy_router.json")
    ranking = load_ranking_policy(_PROFILE / "ranking_policy.yaml")

    validate_provider_runtime_registry(provider_runtime, registry)

    assert len(registry.deployments) == 2
    assert {deployment.provider for deployment in registry.deployments} == {"google", "openai"}
    assert {deployment.model_group for deployment in registry.deployments} == {"balanced"}
    assert all(
        deployment.allowed_environments == frozenset({"development"})
        for deployment in registry.deployments
    )
    assert all(
        deployment.max_data_classification.value == "public"
        for deployment in registry.deployments
    )
    assert policy_runtime.runtime.enabled is True
    assert policy_runtime.runtime.endpoint == "http://127.0.0.1:8001/route"
    assert tuple(binding.client_id for binding in policy_runtime.runtime.bindings) == (
        "gateway-demo",
    )

    workload = ranking.for_workload("rag.answer")
    google_score = workload.score_for("google-gemini-3-8-flash-dev")
    openai_score = workload.score_for("openai-gpt-5-6-luna-dev")
    assert google_score is not None
    assert openai_score is not None
    assert google_score == openai_score


def test_profile_materializes_real_production_composition_without_network_calls() -> None:
    services = activate_governed_deployment(_settings(), environ=_OPAQUE_ENV)

    paths = {getattr(route, "path", None) for route in services.app.routes}
    assert "/v1/generate" in paths
    assert "/v1/route/explain" in paths
    assert services.complexity_enabled is False


@pytest.mark.parametrize("missing_reference", tuple(_OPAQUE_ENV))
def test_profile_fails_closed_when_any_required_secret_is_missing(missing_reference: str) -> None:
    environ = dict(_OPAQUE_ENV)
    del environ[missing_reference]

    with pytest.raises(RuntimeError):
        activate_governed_deployment(_settings(), environ=environ)


def test_profile_does_not_activate_the_checked_in_default_runtime() -> None:
    default_registry = load_model_registry(_ROOT / "config" / "model_registry.yaml")
    default_provider_runtime = load_provider_runtime_document(
        _ROOT / "config" / "providers" / "runtime.json"
    )
    default_policy_runtime = load_policy_router_runtime_document(
        _ROOT / "config" / "policy" / "router.json"
    )

    assert default_registry.deployments == ()
    assert default_provider_runtime.bindings == ()
    assert default_policy_runtime.runtime.enabled is False
