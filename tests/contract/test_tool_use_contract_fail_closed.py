"""Fail-closed regressions for the tool-use v1 benchmark contract."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from benchmarks.contracts import BenchmarkCase, BenchmarkWorkload
from benchmarks.workloads.tool_use import load_tool_use_dataset, validate_tool_use_case

_DATASET = Path("benchmarks/datasets/tool-use-v1.json")


def _first_case() -> BenchmarkCase:
    return load_tool_use_dataset(_DATASET).cases[0]


def test_rejects_wrong_workload() -> None:
    case = replace(_first_case(), workload=BenchmarkWorkload.AGENT_ORCHESTRATION)

    with pytest.raises(ValueError, match="different workload"):
        validate_tool_use_case(case)


def test_rejects_wrong_scorer() -> None:
    case = replace(_first_case(), scorer="mapping_fields")

    with pytest.raises(ValueError, match="versioned deterministic scorer"):
        validate_tool_use_case(case)


def test_rejects_tool_execution_enablement() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["execute_tool"] = True
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="execution must remain disabled"):
        validate_tool_use_case(case)


def test_rejects_expected_tool_outside_allowlist() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["allowed_tools"] = ["search_docs"]
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="expected tool must be present"):
        validate_tool_use_case(case)


def test_rejects_duplicate_allowed_tools() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["allowed_tools"] = ["get_weather", "get_weather"]
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="must not contain duplicates"):
        validate_tool_use_case(case)


def test_rejects_extra_expected_output_fields() -> None:
    original = _first_case()
    assert isinstance(original.expected, dict)
    expected = dict(original.expected)
    expected["execute"] = False
    case = replace(original, expected=expected)

    with pytest.raises(ValueError, match="exactly name and arguments"):
        validate_tool_use_case(case)
