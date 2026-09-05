"""Fail-closed regressions for the code-generation v1 benchmark contract."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from benchmarks.contracts import BenchmarkCase, BenchmarkWorkload
from benchmarks.workloads.code_generation import (
    load_code_generation_dataset,
    validate_code_generation_case,
)

_DATASET = Path("benchmarks/datasets/code-generation-v1.json")


def _first_case() -> BenchmarkCase:
    return load_code_generation_dataset(_DATASET).cases[0]


def test_rejects_wrong_workload() -> None:
    case = replace(_first_case(), workload=BenchmarkWorkload.TOOL_USE)

    with pytest.raises(ValueError, match="different workload"):
        validate_code_generation_case(case)


def test_rejects_wrong_scorer() -> None:
    case = replace(_first_case(), scorer="exact_json")

    with pytest.raises(ValueError, match="versioned deterministic scorer"):
        validate_code_generation_case(case)


def test_rejects_non_python_language() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["language"] = "javascript"
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="language must be python"):
        validate_code_generation_case(case)


def test_rejects_candidate_execution_enablement() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["execute_candidate"] = True
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="execution must remain disabled"):
        validate_code_generation_case(case)


def test_rejects_unsafe_reviewed_expected_source() -> None:
    case = replace(
        _first_case(),
        expected="import os\ndef double(value):\n    return value * 2\n",
    )

    with pytest.raises(ValueError, match="forbidden import"):
        validate_code_generation_case(case)


def test_rejects_invalid_reviewed_expected_source() -> None:
    case = replace(_first_case(), expected="def double(value)\n    return value * 2\n")

    with pytest.raises(SyntaxError):
        validate_code_generation_case(case)
