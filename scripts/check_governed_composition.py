"""Offline consistency check for deployment-owned PDP policy and Gateway catalog.

This checks configuration assertions, not routing or authorization. The external Router
still validates its full policy schema and remains the only PDP. No Router code, second
checkout, Docker, provider credential, health signal or approved score is needed here.
"""

import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import yaml  # type: ignore[import-untyped]
from governed_llm_gateway_contracts import Capability, DataClassification
from governed_llm_gateway_core.adapters.model_registry_yaml import load_model_registry
from governed_llm_gateway_core.domain.model_registry import ModelRegistry, ModelRegistryError

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config/deployment/governed-compose-routing-policy.yaml"
REGISTRY_PATH = ROOT / "config/profiles/personal-default/model_registry.yaml"
_CLASSIFICATIONS = tuple(DataClassification)
_CAPABILITY_FIELDS = {
    "supports_structured_output": Capability.STRUCTURED_OUTPUT,
    "supports_tool_calling": Capability.TOOL_CALLING,
}


class CompositionConfigurationError(ValueError):
    """Raised when the policy's consistency-check projection is malformed."""


class _UniqueKeySafeLoader(yaml.SafeLoader):  # type: ignore[misc]
    """Reject duplicate or non-string keys in deployment-owned safe YAML."""

    def construct_mapping(
        self, node: yaml.nodes.MappingNode, deep: bool = False
    ) -> dict[str, object]:
        self.flatten_mapping(node)
        result: dict[str, object] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise CompositionConfigurationError("policy keys must be unique strings")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not value:
        raise CompositionConfigurationError(f"{label} must be a non-empty mapping")
    if not all(isinstance(key, str) for key in value):
        raise CompositionConfigurationError(f"{label} keys must be strings")
    return cast(Mapping[str, object], value)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise CompositionConfigurationError(f"{label} must be a boolean")
    return value


def _classifications(value: object) -> tuple[DataClassification, ...]:
    if not isinstance(value, list) or not value:
        raise CompositionConfigurationError("authorized_data_classifications must be non-empty")
    try:
        return tuple(DataClassification(item) for item in value)
    except (ValueError, TypeError):
        raise CompositionConfigurationError("invalid authorized_data_classifications") from None


def composition_errors(
    policy_text: str, registry: ModelRegistry, *, environment: str
) -> tuple[str, ...]:
    """Report pool assertions inconsistent with every catalog member in an environment.

    Pool membership includes disabled deployments: an operational toggle, health state,
    or missing ranking coverage is not evidence of classification clearance. Removing a
    member from the pool requires changing its group/environment or removing its entry.
    Advertised structured/tool support is checked conservatively across the same pool.
    Group prices remain independent PDP planning estimates, not pool-price guarantees.
    """
    if not environment or environment.strip() != environment:
        raise CompositionConfigurationError("environment must be a normalized non-empty string")
    loader = _UniqueKeySafeLoader(policy_text)
    try:
        policy = _mapping(loader.get_single_data(), "policy")
    except yaml.YAMLError:
        raise CompositionConfigurationError("policy must be valid safe YAML") from None
    finally:
        loader.dispose()
    if policy.get("schema_version") != "1.0":
        raise CompositionConfigurationError("policy schema_version must be '1.0'")
    groups = _mapping(policy.get("model_groups"), "model_groups")
    workloads = _mapping(policy.get("workloads"), "workloads")
    errors: list[str] = []
    tool_support: dict[str, bool] = {}
    for group_id, raw_group in sorted(groups.items()):
        group = _mapping(raw_group, "model group")
        classifications = _classifications(group.get("authorized_data_classifications"))
        required_capabilities = tuple(
            capability
            for field, capability in _CAPABILITY_FIELDS.items()
            if _boolean(group.get(field), field)
        )
        tool_support[group_id] = Capability.TOOL_CALLING in required_capabilities
        pool = tuple(
            member
            for member in registry.deployments
            if member.model_group == group_id and environment in member.allowed_environments
        )
        if not pool:
            errors.append(f"{group_id}: no catalog deployments in {environment}")
        for member in pool:
            cleared = _CLASSIFICATIONS[: _CLASSIFICATIONS.index(member.max_data_classification) + 1]
            for classification in classifications:
                if classification not in cleared:
                    errors.append(
                        f"{group_id}/{member.deployment_id}: not cleared for {classification.value}"
                    )
            for capability in required_capabilities:
                if capability not in member.capabilities:
                    errors.append(f"{group_id}/{member.deployment_id}: missing {capability.value}")
    for member in registry.deployments:
        if environment in member.allowed_environments and member.model_group not in groups:
            errors.append(f"{member.deployment_id}: model group absent from policy")
    for workload_id, raw_rule in sorted(workloads.items()):
        rule = _mapping(raw_rule, "workload rule")
        rule_group_id = rule.get("model_group")
        if not isinstance(rule_group_id, str) or rule_group_id not in groups:
            errors.append(f"{workload_id}: model group absent from policy")
        elif (
            _boolean(rule.get("requires_tool_calling"), "requires_tool_calling")
            and not tool_support[rule_group_id]
        ):
            errors.append(f"{workload_id}: requires tools but group does not advertise them")
    return tuple(sorted(errors))


def main(argv: Sequence[str] | None = None) -> int:
    """Check local artifacts without contacting the PDP or providers."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy-path", type=Path, default=POLICY_PATH)
    parser.add_argument("--registry-path", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--environment", default="development")
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        errors = composition_errors(
            args.policy_path.read_text(encoding="utf-8"),
            load_model_registry(args.registry_path),
            environment=args.environment,
        )
    except (OSError, UnicodeError, ModelRegistryError, CompositionConfigurationError):
        print("governed_composition: FAIL (invalid or unreadable configuration)")
        return 1
    if errors:
        print("governed_composition: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"governed_composition: PASS ({args.environment})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
