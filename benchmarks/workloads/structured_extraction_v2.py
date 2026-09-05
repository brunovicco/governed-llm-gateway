"""Deterministic structured-extraction v2 workload contract and scorer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

STRUCTURED_EXTRACTION_V2_BENCHMARK_VERSION = "structured-extraction-v2"
STRUCTURED_EXTRACTION_V2_CONTRACT_VERSION = "2.0"
STRUCTURED_EXTRACTION_V2_SCORER_ID = "structured_extraction_v2"

_ALLOWED_METADATA_FIELDS = {"contract_version", "language", "synthetic", "output_schema"}
_SUPPORTED_SCHEMA_TYPES = {"array", "boolean", "integer", "null", "number", "object", "string"}


@dataclass(frozen=True, slots=True, order=True)
class StructuredExtractionIssue:
    """Stable reason code and JSON-pointer-like path for one deterministic scoring issue."""

    code: str
    path: str


@dataclass(frozen=True, slots=True)
class StructuredExtractionAssessment:
    """Explainable schema and exact-value evidence for one structured extraction output."""

    score: Decimal
    schema_score: Decimal
    value_score: Decimal
    issues: tuple[StructuredExtractionIssue, ...]

    @property
    def schema_valid(self) -> bool:
        """Return whether the output satisfies the reviewed bounded schema exactly."""
        return self.schema_score == Decimal("1")


def load_structured_extraction_v2_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate a dataset containing only structured-extraction v2 cases."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    if dataset.benchmark_version != STRUCTURED_EXTRACTION_V2_BENCHMARK_VERSION:
        raise ValueError(
            "structured extraction v2 requires benchmark_version structured-extraction-v2"
        )
    case_ids = [case.case_id for case in dataset.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("structured extraction v2 case IDs must be unique")
    for case in dataset.cases:
        validate_structured_extraction_v2_case(case)
    return dataset


def validate_structured_extraction_v2_case(case: BenchmarkCase) -> None:
    """Fail closed when a structured-extraction case drifts from the v2 contract."""
    if case.workload is not BenchmarkWorkload.STRUCTURED_EXTRACTION:
        raise ValueError("structured extraction v2 dataset contains a different workload")
    if case.scorer != STRUCTURED_EXTRACTION_V2_SCORER_ID:
        raise ValueError("structured extraction v2 requires its versioned deterministic scorer")
    if not isinstance(case.expected, dict) or not case.expected:
        raise ValueError("structured extraction v2 expected output must be a non-empty object")

    metadata = case.metadata
    unknown_metadata = sorted(set(metadata) - _ALLOWED_METADATA_FIELDS)
    if unknown_metadata:
        fields = ", ".join(unknown_metadata)
        raise ValueError(f"structured extraction v2 metadata contains unknown fields: {fields}")
    if metadata.get("contract_version") != STRUCTURED_EXTRACTION_V2_CONTRACT_VERSION:
        raise ValueError("structured extraction v2 contract_version must be 2.0")
    if metadata.get("synthetic") is not True:
        raise ValueError("structured extraction v2 cases must be explicitly synthetic")

    language = metadata.get("language")
    if not isinstance(language, str) or not language or language.strip() != language:
        raise ValueError("structured extraction v2 language must be a normalized string")

    schema = metadata.get("output_schema")
    if not isinstance(schema, dict):
        raise ValueError("structured extraction v2 output_schema must be an object")
    _validate_schema_definition(schema, path="/")
    expected_issues = _validate_instance(schema, case.expected, path="/")
    if expected_issues:
        first = expected_issues[0]
        raise ValueError(
            "structured extraction v2 expected output does not satisfy output_schema: "
            f"{first.code} at {first.path}"
        )


def assess_structured_extraction_v2(
    case: BenchmarkCase,
    output: JsonValue,
) -> StructuredExtractionAssessment:
    """Return deterministic schema, value, and reason-code evidence for one output."""
    validate_structured_extraction_v2_case(case)
    expected = case.expected
    schema = case.metadata["output_schema"]
    if not isinstance(expected, dict) or not isinstance(schema, dict):
        raise AssertionError("validated structured extraction v2 case is inconsistent")

    schema_issues = _validate_instance(schema, output, path="/")
    matched, total, value_issues = _compare_values(expected, output, path="/")
    schema_score = Decimal("1") if not schema_issues else Decimal("0")
    value_score = Decimal(matched) / Decimal(max(total, 1))
    score = (schema_score + value_score) / Decimal("2")
    issues = tuple(sorted({*schema_issues, *value_issues}))
    return StructuredExtractionAssessment(
        score=score,
        schema_score=schema_score,
        value_score=value_score,
        issues=issues,
    )


def score_structured_extraction_v2(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Return the scalar v2 score consumed by the existing BenchmarkRunner contract."""
    return assess_structured_extraction_v2(case, output).score


def _validate_schema_definition(schema: Mapping[str, JsonValue], *, path: str) -> None:
    types = _schema_types(schema, path=path)
    non_null_types = [item for item in types if item != "null"]
    if len(non_null_types) > 1:
        raise ValueError(f"structured extraction v2 schema {path} supports one non-null type")

    primary_type = non_null_types[0] if non_null_types else "null"
    allowed = {"type", "enum"}
    if primary_type == "object":
        allowed.update({"additionalProperties", "properties", "required"})
    elif primary_type == "array":
        allowed.add("items")
    unknown = sorted(set(schema) - allowed)
    if unknown:
        fields = ", ".join(unknown)
        raise ValueError(
            f"structured extraction v2 schema {path} contains unknown fields: {fields}"
        )

    enum_values = schema.get("enum")
    if enum_values is not None:
        if primary_type in {"array", "object"}:
            raise ValueError(f"structured extraction v2 schema {path} enum must be scalar")
        if not isinstance(enum_values, list) or not enum_values:
            raise ValueError(
                f"structured extraction v2 schema {path} enum must be a non-empty list"
            )
        for index, enum_value in enumerate(enum_values):
            if not _matches_any_type(enum_value, types):
                raise ValueError(
                    f"structured extraction v2 schema {path} enum value {index} has wrong type"
                )
        for index, enum_value in enumerate(enum_values):
            if any(_strict_json_equal(enum_value, previous) for previous in enum_values[:index]):
                raise ValueError(f"structured extraction v2 schema {path} enum has duplicates")

    if primary_type == "object":
        if schema.get("additionalProperties") is not False:
            raise ValueError(
                f"structured extraction v2 object schema {path} must reject additional properties"
            )
        properties = schema.get("properties")
        if not isinstance(properties, dict) or not properties:
            raise ValueError(
                f"structured extraction v2 object schema {path} properties must be non-empty"
            )
        required = schema.get("required")
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise ValueError(
                f"structured extraction v2 object schema {path} required must be a string list"
            )
        if len(required) != len(set(required)):
            raise ValueError(
                "structured extraction v2 object schema "
                f"{path} required must not contain duplicates"
            )
        unknown_required = sorted(set(required) - set(properties))
        if unknown_required:
            raise ValueError(
                "structured extraction v2 object schema "
                f"{path} required fields must exist in properties"
            )
        for key, property_schema in properties.items():
            if not isinstance(key, str) or not key or key.strip() != key:
                raise ValueError(
                    "structured extraction v2 object schema "
                    f"{path} property names must be normalized"
                )
            if not isinstance(property_schema, dict):
                raise ValueError(
                    "structured extraction v2 object schema "
                    f"{_child_path(path, key)} must be an object"
                )
            _validate_schema_definition(property_schema, path=_child_path(path, key))
    elif primary_type == "array":
        items = schema.get("items")
        if not isinstance(items, dict):
            raise ValueError(f"structured extraction v2 array schema {path} requires items")
        _validate_schema_definition(items, path=_child_path(path, "*"))


def _schema_types(schema: Mapping[str, JsonValue], *, path: str) -> tuple[str, ...]:
    raw_type = schema.get("type")
    if isinstance(raw_type, str):
        types = (raw_type,)
    elif (
        isinstance(raw_type, list)
        and raw_type
        and all(isinstance(item, str) for item in raw_type)
    ):
        types = tuple(item for item in raw_type if isinstance(item, str))
    else:
        raise ValueError(
            f"structured extraction v2 schema {path} type must be a string or string list"
        )
    if len(types) != len(set(types)):
        raise ValueError(
            f"structured extraction v2 schema {path} type list must not contain duplicates"
        )
    unknown = sorted(set(types) - _SUPPORTED_SCHEMA_TYPES)
    if unknown:
        raise ValueError(
            f"structured extraction v2 schema {path} has unsupported types: {', '.join(unknown)}"
        )
    return types


def _validate_instance(
    schema: Mapping[str, JsonValue],
    value: JsonValue,
    *,
    path: str,
) -> tuple[StructuredExtractionIssue, ...]:
    types = _schema_types(schema, path=path)
    if not _matches_any_type(value, types):
        return (StructuredExtractionIssue("wrong_type", path),)

    issues: list[StructuredExtractionIssue] = []
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and not any(
        _strict_json_equal(value, enum_value) for enum_value in enum_values
    ):
        issues.append(StructuredExtractionIssue("enum_violation", path))

    if isinstance(value, dict) and "object" in types:
        raw_properties = schema.get("properties")
        raw_required = schema.get("required")
        if not isinstance(raw_properties, dict) or not isinstance(raw_required, list):
            raise AssertionError("validated structured extraction v2 object schema is inconsistent")
        properties: dict[str, JsonValue] = raw_properties
        required: Sequence[JsonValue] = raw_required
        for required_key in required:
            if not isinstance(required_key, str):
                raise AssertionError(
                    "validated structured extraction v2 required key is not a string"
                )
            if required_key not in value:
                issues.append(
                    StructuredExtractionIssue(
                        "missing_required_field", _child_path(path, required_key)
                    )
                )
        for key in sorted(value):
            property_schema = properties.get(key)
            child_path = _child_path(path, key)
            if property_schema is None:
                issues.append(StructuredExtractionIssue("unexpected_field", child_path))
                continue
            if not isinstance(property_schema, dict):
                raise AssertionError(
                    "validated structured extraction v2 property schema is inconsistent"
                )
            issues.extend(_validate_instance(property_schema, value[key], path=child_path))
    elif isinstance(value, list) and "array" in types:
        items = schema.get("items")
        if not isinstance(items, dict):
            raise AssertionError("validated structured extraction v2 array schema is inconsistent")
        for index, item in enumerate(value):
            issues.extend(_validate_instance(items, item, path=_child_path(path, str(index))))

    return tuple(issues)


def _compare_values(
    expected: JsonValue,
    actual: JsonValue,
    *,
    path: str,
) -> tuple[int, int, tuple[StructuredExtractionIssue, ...]]:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return 0, _value_units(expected), (StructuredExtractionIssue("wrong_type", path),)
        matched = 0
        total = 0
        issues: list[StructuredExtractionIssue] = []
        for key in sorted(expected):
            child_path = _child_path(path, key)
            if key not in actual:
                total += _value_units(expected[key])
                issues.append(StructuredExtractionIssue("missing_expected_field", child_path))
                continue
            child_matched, child_total, child_issues = _compare_values(
                expected[key], actual[key], path=child_path
            )
            matched += child_matched
            total += child_total
            issues.extend(child_issues)
        for key in sorted(set(actual) - set(expected)):
            child_path = _child_path(path, key)
            total += _value_units(actual[key])
            issues.append(StructuredExtractionIssue("unexpected_extracted_field", child_path))
        return matched, max(total, 1), tuple(issues)

    if isinstance(expected, list):
        if not isinstance(actual, list):
            return 0, _value_units(expected), (StructuredExtractionIssue("wrong_type", path),)
        matched = 0
        total = 0
        issues: list[StructuredExtractionIssue] = []
        if len(expected) != len(actual):
            issues.append(StructuredExtractionIssue("array_length_mismatch", path))
        for index in range(max(len(expected), len(actual))):
            child_path = _child_path(path, str(index))
            if index >= len(expected):
                total += _value_units(actual[index])
                continue
            if index >= len(actual):
                total += _value_units(expected[index])
                continue
            child_matched, child_total, child_issues = _compare_values(
                expected[index], actual[index], path=child_path
            )
            matched += child_matched
            total += child_total
            issues.extend(child_issues)
        return matched, max(total, 1), tuple(issues)

    if _strict_json_equal(expected, actual):
        return 1, 1, ()
    issue_code = "wrong_type" if type(expected) is not type(actual) else "wrong_value"
    return 0, 1, (StructuredExtractionIssue(issue_code, path),)


def _value_units(value: JsonValue) -> int:
    if isinstance(value, dict):
        return max(sum(_value_units(item) for item in value.values()), 1)
    if isinstance(value, list):
        return max(sum(_value_units(item) for item in value), 1)
    return 1


def _matches_any_type(value: JsonValue, types: Sequence[str]) -> bool:
    return any(_matches_type(value, schema_type) for schema_type in types)


def _matches_type(value: JsonValue, schema_type: str) -> bool:
    if schema_type == "null":
        return value is None
    if schema_type == "boolean":
        return type(value) is bool
    if schema_type == "integer":
        return type(value) is int
    if schema_type == "number":
        return type(value) in {int, float}
    if schema_type == "string":
        return type(value) is str
    if schema_type == "array":
        return type(value) is list
    if schema_type == "object":
        return type(value) is dict
    raise AssertionError(f"unsupported validated schema type: {schema_type}")


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


def _child_path(path: str, token: str) -> str:
    escaped = token.replace("~", "~0").replace("/", "~1")
    if path == "/":
        return f"/{escaped}"
    return f"{path}/{escaped}"
