"""Strict YAML adapter for loading versioned Phase 5 ranking policy."""

from collections.abc import Mapping
from pathlib import Path
from typing import cast

import yaml  # type: ignore[import-untyped]

from governed_llm_gateway_core.domain.ranking import (
    DuplicateRankingKeyError,
    RankingPolicy,
    RankingPolicyError,
    build_ranking_policy,
)


class _UniqueRankingKeySafeLoader(yaml.SafeLoader):  # type: ignore[misc]
    """Safe YAML loader that rejects duplicate ranking-policy mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueRankingKeySafeLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise RankingPolicyError("ranking policy mapping keys must be hashable") from exc
        if duplicate:
            raise DuplicateRankingKeyError(f"duplicate ranking policy mapping key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueRankingKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_ranking_policy(path: str | Path) -> RankingPolicy:
    """Load and validate one UTF-8 YAML ranking-policy file."""
    policy_path = Path(path)
    return load_ranking_policy_text(policy_path.read_text(encoding="utf-8"))


def load_ranking_policy_text(text: str) -> RankingPolicy:
    """Load and validate ranking-policy YAML supplied as text."""
    loader = _UniqueRankingKeySafeLoader(text)
    try:
        payload = loader.get_single_data()
    except yaml.YAMLError as exc:
        raise RankingPolicyError("ranking policy is not valid safe YAML") from exc
    finally:
        loader.dispose()
    if not isinstance(payload, Mapping):
        raise RankingPolicyError("ranking policy root must be a mapping")
    return build_ranking_policy(cast(Mapping[object, object], payload))
