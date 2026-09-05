"""Deterministic structured-extraction workload contract and scorer."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

STRUCTURED_EXTRACTION_CONTRACT_VERSION = "1.0"
STRUCTURED_EXTRACTION_SCORER_ID = "structured_extraction_v1"


def load_structured_extraction_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate a dataset containing only structured-extraction v1 cases."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    for case in dataset.cases:
        validate_structured_extraction_case(case)
    return dataset


def validate_structured_extraction_case(case: BenchmarkCase) -> None:
    """Fail closed when a structured-extraction case drifts from the v1 contract."""
    if case.workload is not BenchmarkWorkload.STRUCTURED_EXTRACTION:
        raise ValueError("structured extraction dataset contains a different workload")
    if case.scorer != STRUCTURED_EXTRACTION_SCORER_ID:
        raise ValueError("structured extraction v1 requires its versioned deterministic scorer")
    if not isinstance(case.expected, dict) or not case.expected:
        raise ValueError("structured extraction expected output must be a non-empty object")

    metadata = case.metadata
    if metadata.get("contract_version") != STRUCTURED_EXTRACTION_CONTRACT_VERSION:
        raise ValueError("structured extraction contract_version must be 1.0")
    if metadata.get("synthetic") is not True:
        raise ValueError("structured extraction cases must be explicitly synthetic")

    language = metadata.get("language")
    if not isinstance(language, str) or not language or language.strip() != language:
        raise ValueError("structured extraction language must be a normalized string")

    schema = metadata.get("output_schema")
    if not isinstance(schema, dict):
        raise ValueError("structured extraction output_schema must be an object")
    _validate_output_schema(schema, case.expected)


def score_structured_extraction(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Score exact typed top-level fields while penalizing missing or extra fields."""
    validate_structured_extraction_case(case)
    expected = case.expected
    if not isinstance(expected, dict):
        raise AssertionError("validated structured extraction expected output must be an object")
    if not isinstance(output, dict):
        return Decimal("0")

    denominator = max(len(expected), len(output), 1)
    matches = sum(
        1
        for key, expected_value in expected.items()
        if key in output and _strict_json_equal(output[key], expected_value)
    )
    return Decimal(matches) / Decimal(denominator)


def _validate_output_schema(
    schema: Mapping[str, JsonValue], expected: dict[str, JsonValue]
) -> None:
    allowed = {"type", "additionalProperties", "required", "properties"}
    unknown = sorted(set(schema) - allowed)
    if unknown:
        fields = ", ".join(unknown)
        raise ValueError(f"structured extraction output_schema contains unknown fields: {fields}")
    if schema.get("type") != "object":
        raise ValueError("structured extraction output_schema.type must be object")
    if schema.get("additionalProperties") is not False:
        raise ValueError("structured extraction output_schema must reject additional properties")

    required = schema.get("required")
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise ValueError("structured extraction output_schema.required must be a string list")
    if len(required) != len(set(required)):
        raise ValueError("structured extraction output_schema.required must not contain duplicates")
    if set(required) != set(expected):
        raise ValueError("structured extraction required fields must match expected output keys")

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise ValueError("structured extraction output_schema.properties must be an object")
    if set(properties) != set(expected):
        raise ValueError("structured extraction schema properties must match expected output keys")
    for key, value in properties.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise ValueError("structured extraction schema properties must be named objects")
        property_type = value.get("type")
        if not isinstance(property_type, str | list):
            raise ValueError("structured extraction property type must be a string or string list")
        if isinstance(property_type, list) and not all(
            isinstance(item, str) for item in property_type
        ):
            raise ValueError("structured extraction property type list must contain strings")


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
