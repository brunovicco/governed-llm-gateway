"""Fail-closed regressions for the tool-use v1 benchmark contract."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from benchmarks.contracts import BenchmarkCase, BenchmarkWorkload
from benchmarks.workloads.tool_use import load_tool_use_dataset, validate_tool_use_case

_DATASET = Path("benchmarks/datasets/tool-use-v1.json")


def _first_case() -> BenchmarkCase:
    return load_tool_use_dataset(_DATASET).cases[0]


def _payload() -> dict[str, object]:
    value = json.loads(_DATASET.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "tool-use-v1-invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_rejects_wrong_workload() -> None:
    case = replace(_first_case(), workload=BenchmarkWorkload.AGENT_ORCHESTRATION)

    with pytest.raises(ValueError, match="different workload"):
        validate_tool_use_case(case)


def test_rejects_wrong_scorer() -> None:
    case = replace(_first_case(), scorer="mapping_fields")

    with pytest.raises(ValueError, match="versioned deterministic scorer"):
        validate_tool_use_case(case)


def test_rejects_wrong_contract_version() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["contract_version"] = "2.0"
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="contract_version must be 1.0"):
        validate_tool_use_case(case)


def test_rejects_unknown_metadata() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["authorization"] = True
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="metadata contains unknown fields"):
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


def test_rejects_wrong_benchmark_version(tmp_path: Path) -> None:
    payload = _payload()
    payload["benchmark_version"] = "tool-use-v2"

    with pytest.raises(ValueError, match="benchmark_version tool-use-v1"):
        load_tool_use_dataset(_write(tmp_path, payload))


def test_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = _payload()
    cases = payload["cases"]
    assert isinstance(cases, list)
    assert isinstance(cases[0], dict)
    assert isinstance(cases[1], dict)
    cases[1]["case_id"] = cases[0]["case_id"]

    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_tool_use_dataset(_write(tmp_path, payload))
