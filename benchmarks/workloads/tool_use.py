"""Deterministic tool-selection benchmark contract and scorer."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

TOOL_USE_CONTRACT_VERSION = "1.0"
TOOL_USE_SCORER_ID = "tool_use_v1"


def load_tool_use_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate a dataset containing only normalized tool-selection cases."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    for case in dataset.cases:
        validate_tool_use_case(case)
    return dataset


def validate_tool_use_case(case: BenchmarkCase) -> None:
    """Fail closed when a tool-use case drifts from the v1 benchmark contract."""
    if case.workload is not BenchmarkWorkload.TOOL_USE:
        raise ValueError("tool use dataset contains a different workload")
    if case.scorer != TOOL_USE_SCORER_ID:
        raise ValueError("tool use v1 requires its versioned deterministic scorer")
    if not isinstance(case.expected, dict):
        raise ValueError("tool use expected output must be an object")
    if set(case.expected) != {"name", "arguments"}:
        raise ValueError("tool use expected output must contain exactly name and arguments")

    name = case.expected.get("name")
    arguments = case.expected.get("arguments")
    if not isinstance(name, str) or not name or name.strip() != name:
        raise ValueError("tool use expected name must be a normalized string")
    if not isinstance(arguments, dict):
        raise ValueError("tool use expected arguments must be an object")

    metadata = case.metadata
    if metadata.get("contract_version") != TOOL_USE_CONTRACT_VERSION:
        raise ValueError("tool use contract_version must be 1.0")
    if metadata.get("synthetic") is not True:
        raise ValueError("tool use cases must be explicitly synthetic")
    if metadata.get("execute_tool") is not False:
        raise ValueError("tool use execution must remain disabled")

    allowed_tools = metadata.get("allowed_tools")
    if not isinstance(allowed_tools, list) or not allowed_tools:
        raise ValueError("tool use allowed_tools must be a non-empty string list")
    if not all(
        isinstance(item, str) and item and item.strip() == item for item in allowed_tools
    ):
        raise ValueError("tool use allowed_tools must contain normalized strings")
    if len(allowed_tools) != len(set(allowed_tools)):
        raise ValueError("tool use allowed_tools must not contain duplicates")
    if name not in allowed_tools:
        raise ValueError("tool use expected tool must be present in allowed_tools")


def score_tool_use(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Score normalized tool name and exact typed arguments without executing the tool."""
    validate_tool_use_case(case)
    if not isinstance(output, dict) or set(output) != {"name", "arguments"}:
        return Decimal("0")

    expected = case.expected
    if not isinstance(expected, dict):
        raise AssertionError("validated tool use expected output must be an object")
    output_name = output.get("name")
    output_arguments = output.get("arguments")
    if not isinstance(output_name, str) or not isinstance(output_arguments, dict):
        return Decimal("0")

    allowed_tools = case.metadata.get("allowed_tools")
    if not isinstance(allowed_tools, list):
        raise AssertionError("validated tool use allowed_tools must be a list")
    if output_name not in allowed_tools:
        return Decimal("0")

    name_score = Decimal("0.5") if output_name == expected.get("name") else Decimal("0")
    arguments_score = (
        Decimal("0.5")
        if _strict_json_equal(output_arguments, expected.get("arguments"))
        else Decimal("0")
    )
    return name_score + arguments_score


def _strict_json_equal(left: JsonValue, right: JsonValue) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(
            _strict_json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _strict_json_equal(left_item, right_item)
            for left_item, right_item in zip(left, right, strict=True)
        )
    return left == right
