"""Deployment-owned assertions must describe the entire local catalog pool."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]
from governed_llm_gateway_contracts import Capability, DataClassification
from governed_llm_gateway_core.adapters.model_registry_yaml import load_model_registry
from governed_llm_gateway_core.domain.model_registry import ModelRegistry

from scripts.check_governed_composition import (
    POLICY_PATH,
    REGISTRY_PATH,
    CompositionConfigurationError,
    composition_errors,
    main,
)
from scripts.quality_gate import STEPS


@pytest.fixture
def registry() -> ModelRegistry:
    catalog = load_model_registry(REGISTRY_PATH)
    pool = tuple(member for member in catalog.deployments if member.model_group == "balanced")
    return replace(catalog, deployments=pool)


def _policy() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "model_groups": {
            "balanced": {
                "authorized_data_classifications": ["public"],
                "supports_structured_output": False,
                "supports_tool_calling": False,
                "input_cost_usd_per_million_tokens": "0.50",
                "output_cost_usd_per_million_tokens": "2.00",
            }
        },
        "workloads": {"rag.answer": {"model_group": "balanced", "requires_tool_calling": False}},
    }


def _errors(policy: dict[str, Any], registry: ModelRegistry) -> tuple[str, ...]:
    # JSON is safe YAML too; synthetic assertions never modify real artifacts.
    return composition_errors(json.dumps(policy), registry, environment="development")


def test_checked_in_policy_describes_every_personal_default_pool() -> None:
    assert (
        composition_errors(
            POLICY_PATH.read_text(encoding="utf-8"),
            load_model_registry(REGISTRY_PATH),
            environment="development",
        )
        == ()
    )


def test_offline_check_is_in_the_canonical_ci_gate() -> None:
    command = dict(STEPS)["governed-composition"]
    assert command[-2:] == ["python", "scripts/check_governed_composition.py"]
    assert "--all-packages" in command


def test_compose_mounts_the_same_policy_and_catalog_checked_offline() -> None:
    root = POLICY_PATH.parents[2]
    compose = yaml.safe_load((root / "compose.gateway.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert services["policy-model-router"]["environment"]["APP_ENV"] == "development"
    policy_mount = (
        f"./{POLICY_PATH.relative_to(root)}:/etc/policy-model-router/routing_policy.yaml:ro"
    )
    assert policy_mount in services["policy-model-router"]["volumes"]
    registry_mount = f"./{REGISTRY_PATH.parent.relative_to(root)}:/config:ro"
    assert registry_mount in services["gateway"]["volumes"]
    assert "--model-registry-path=model_registry.yaml" in services["gateway"]["command"]


def test_one_cleared_deployment_cannot_authorize_the_rest(registry: ModelRegistry) -> None:
    policy = _policy()
    policy["model_groups"]["balanced"]["authorized_data_classifications"] = ["confidential"]
    members = registry.deployments
    mixed = replace(
        registry,
        deployments=(
            replace(members[0], max_data_classification=DataClassification.RESTRICTED),
            *members[1:],
        ),
    )
    errors = _errors(policy, mixed)
    assert len(errors) == len(members) - 1
    assert all("not cleared for confidential" in error for error in errors)
    assert not any(members[0].deployment_id in error for error in errors)


def test_all_pool_members_must_cover_each_authorized_classification(
    registry: ModelRegistry,
) -> None:
    policy = _policy()
    policy["model_groups"]["balanced"]["authorized_data_classifications"] = [
        "public",
        "internal",
        "confidential",
    ]
    cleared = replace(
        registry,
        deployments=tuple(
            replace(member, max_data_classification=DataClassification.CONFIDENTIAL)
            for member in registry.deployments
        ),
    )
    assert _errors(policy, cleared) == ()


def test_disabled_member_is_not_a_clearance_exemption(registry: ModelRegistry) -> None:
    policy = _policy()
    policy["model_groups"]["balanced"]["authorized_data_classifications"] = ["confidential"]
    members = registry.deployments
    mixed = replace(
        registry,
        deployments=(
            replace(members[0], enabled=False),
            *(
                replace(member, max_data_classification=DataClassification.CONFIDENTIAL)
                for member in members[1:]
            ),
        ),
    )
    assert _errors(policy, mixed) == (
        f"balanced/{members[0].deployment_id}: not cleared for confidential",
    )


def test_pool_scope_is_the_configured_environment(registry: ModelRegistry) -> None:
    policy = _policy()
    policy["model_groups"]["balanced"]["authorized_data_classifications"] = ["confidential"]
    members = registry.deployments
    scoped = replace(
        registry,
        deployments=(
            replace(members[0], allowed_environments=frozenset({"production"})),
            *(
                replace(member, max_data_classification=DataClassification.CONFIDENTIAL)
                for member in members[1:]
            ),
        ),
    )
    assert _errors(policy, scoped) == ()


@pytest.mark.parametrize("capability", [Capability.STRUCTURED_OUTPUT, Capability.TOOL_CALLING])
def test_one_capable_member_does_not_prove_pool_support(
    registry: ModelRegistry, capability: Capability
) -> None:
    policy = _policy()
    policy["model_groups"]["balanced"][f"supports_{capability.value}"] = True
    members = registry.deployments
    mixed = replace(
        registry,
        deployments=(
            replace(members[0], capabilities=members[0].capabilities | {capability}),
            *members[1:],
        ),
    )
    errors = _errors(policy, mixed)
    assert len(errors) == len(members) - 1
    assert all(f"missing {capability.value}" in error for error in errors)


def test_empty_pool_cannot_vacuously_pass(registry: ModelRegistry) -> None:
    assert _errors(_policy(), replace(registry, deployments=())) == (
        "balanced: no catalog deployments in development",
    )


def test_catalog_group_must_exist_in_policy(registry: ModelRegistry) -> None:
    orphan = replace(registry.deployments[0], deployment_id="orphan", model_group="other")
    errors = _errors(_policy(), replace(registry, deployments=(*registry.deployments, orphan)))
    assert errors == ("orphan: model group absent from policy",)


def test_workload_must_reference_a_declared_group(registry: ModelRegistry) -> None:
    policy = _policy()
    policy["workloads"]["rag.answer"]["model_group"] = "other"
    assert _errors(policy, registry) == ("rag.answer: model group absent from policy",)


def test_tool_workload_requires_group_tool_support(registry: ModelRegistry) -> None:
    policy = _policy()
    policy["workloads"]["rag.answer"]["requires_tool_calling"] = True
    assert _errors(policy, registry) == (
        "rag.answer: requires tools but group does not advertise them",
    )


def test_group_estimates_are_not_required_to_equal_or_bound_deployment_prices(
    registry: ModelRegistry,
) -> None:
    policy = _policy()
    # The real balanced pool includes a zero-cost tier and input/output prices both
    # above and below this independent PDP estimate. This is not a catalog drift rule.
    assert _errors(policy, registry) == ()
    policy["model_groups"]["balanced"]["input_cost_usd_per_million_tokens"] = "100.00"
    policy["model_groups"]["balanced"]["output_cost_usd_per_million_tokens"] = "100.00"
    assert _errors(policy, registry) == ()


@pytest.mark.parametrize("value", ["true", 1, None])
def test_non_boolean_capability_assertion_is_invalid(
    registry: ModelRegistry, value: object
) -> None:
    policy = _policy()
    policy["model_groups"]["balanced"]["supports_tool_calling"] = value
    with pytest.raises(CompositionConfigurationError):
        _errors(policy, registry)


@pytest.mark.parametrize("value", [[], ["secret"], "public", None])
def test_invalid_classification_assertion_is_rejected(
    registry: ModelRegistry, value: object
) -> None:
    policy = _policy()
    policy["model_groups"]["balanced"]["authorized_data_classifications"] = value
    with pytest.raises(CompositionConfigurationError):
        _errors(policy, registry)


@pytest.mark.parametrize(
    "text",
    ["schema_version: '1.0'\nschema_version: '1.0'", "[", "!!python/object:builtins.object {}"],
)
def test_duplicate_or_unsafe_yaml_is_rejected(registry: ModelRegistry, text: str) -> None:
    with pytest.raises(CompositionConfigurationError):
        composition_errors(text, registry, environment="development")


def test_cli_returns_nonzero_for_drift(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    policy = _policy()
    policy["model_groups"]["balanced"]["supports_tool_calling"] = True
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    assert main(["--policy-path", str(policy_path)]) == 1
    assert "governed_composition: FAIL" in capsys.readouterr().out


def test_cli_sanitizes_unreadable_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.yaml"
    assert main(["--policy-path", str(missing)]) == 1
    output = capsys.readouterr().out
    assert "invalid or unreadable configuration" in output
    assert str(missing) not in output
