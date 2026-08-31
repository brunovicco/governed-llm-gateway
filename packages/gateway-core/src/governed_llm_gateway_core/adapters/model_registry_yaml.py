"""Strict YAML adapter for loading model-registry configuration."""

from collections.abc import Mapping
from pathlib import Path
from typing import cast

import yaml  # type: ignore[import-untyped]

from governed_llm_gateway_core.domain.model_registry import (
    DuplicateRegistryKeyError,
    ModelRegistry,
    ModelRegistryError,
    build_model_registry,
)


class _UniqueKeySafeLoader(yaml.SafeLoader):  # type: ignore[misc]
    """Safe YAML loader that refuses duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ModelRegistryError("registry mapping keys must be hashable") from exc
        if duplicate:
            raise DuplicateRegistryKeyError(f"duplicate registry mapping key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_model_registry(path: str | Path) -> ModelRegistry:
    """Load and validate one UTF-8 YAML model-registry file."""
    registry_path = Path(path)
    return load_model_registry_text(registry_path.read_text(encoding="utf-8"))


def load_model_registry_text(text: str) -> ModelRegistry:
    """Load and validate model-registry YAML supplied as text."""
    loader = _UniqueKeySafeLoader(text)
    try:
        payload = loader.get_single_data()
    except yaml.YAMLError as exc:
        raise ModelRegistryError("model registry is not valid safe YAML") from exc
    finally:
        loader.dispose()
    if not isinstance(payload, Mapping):
        raise ModelRegistryError("model registry root must be a mapping")
    return build_model_registry(cast(Mapping[object, object], payload))
