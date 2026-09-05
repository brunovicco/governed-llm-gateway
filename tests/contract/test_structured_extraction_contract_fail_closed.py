"""Fail-closed regressions for the structured-extraction v1 benchmark contract."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from benchmarks.contracts import BenchmarkWorkload
from benchmarks.workloads.structured_extraction import (
    load_structured_extraction_dataset,
    validate_structured_extraction_case,
)

_DATASET = Path("benchmarks/datasets/structured-extraction-v1.json")


def _first_case():
    return load_structured_extraction_dataset(_DATASET).cases[0]


def test_rejects_wrong_workload() -> None:
    case = replace(_first_case(), workload=BenchmarkWorkload.RAG_PTBR)

    with pytest.raises(ValueError, match="different workload"):
        validate_structured_extraction_case(case)


def test_rejects_wrong_scorer() -> None:
    case = replace(_first_case(), scorer="exact_json")

    with pytest.raises(ValueError, match="versioned deterministic scorer"):
        validate_structured_extraction_case(case)


def test_rejects_non_synthetic_case() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["synthetic"] = False
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="explicitly synthetic"):
        validate_structured_extraction_case(case)


def test_rejects_schema_that_allows_extra_properties() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    raw_schema = metadata["output_schema"]
    assert isinstance(raw_schema, dict)
    schema = dict(raw_schema)
    schema["additionalProperties"] = True
    metadata["output_schema"] = schema
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="reject additional properties"):
        validate_structured_extraction_case(case)


def test_rejects_required_fields_that_do_not_match_expected_output() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    raw_schema = metadata["output_schema"]
    assert isinstance(raw_schema, dict)
    schema = dict(raw_schema)
    schema["required"] = ["invoice_id"]
    metadata["output_schema"] = schema
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="required fields must match"):
        validate_structured_extraction_case(case)


def test_rejects_schema_properties_that_do_not_match_expected_output() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    raw_schema = metadata["output_schema"]
    assert isinstance(raw_schema, dict)
    schema = dict(raw_schema)
    schema["properties"] = {"invoice_id": {"type": "string"}}
    metadata["output_schema"] = schema
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="schema properties must match"):
        validate_structured_extraction_case(case)
