"""Deterministic JSON/schema-compliance benchmark contract and scorer."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from governed_llm_gateway_contracts import StructuredOutputSchema
from governed_llm_gateway_core.domain.structured import (
    InvalidSchemaError,
    validate_structured_output_schema,
)
from jsonschema import Draft202012Validator

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

JSON_SCHEMA_COMPLIANCE_BENCHMARK_VERSION = "json-schema-compliance-v1"
JSON_SCHEMA_COMPLIANCE_CONTRACT_VERSION = "1.0"
JSON_SCHEMA_COMPLIANCE_SCORER_ID = "json_schema_compliance_v1"

_ALLOWED_METADATA_FIELDS = {"contract_version", "language", "output_schema", "synthetic"}
_EXPECTED_CASE_COUNT = 6
_PROMPT_PREFIX = (
    "Return only one JSON value that satisfies the reviewed schema below. "
    "Choose any values permitted by the schema. Do not add prose or markdown. Schema: "
)


@dataclass(frozen=True, slots=True, order=True)
class JsonSchemaComplianceIssue:
    """Stable schema-validator reason code and JSON-pointer-like output path."""

    code: str
    path: str


@dataclass(frozen=True, slots=True)
class JsonSchemaComplianceAssessment:
    """Explainable deterministic schema-compliance evidence for normalized JSON output."""

    score: Decimal
    issues: tuple[JsonSchemaComplianceIssue, ...]

    @property
    def schema_valid(self) -> bool:
        """Return whether normalized output satisfies the reviewed schema."""
        return self.score == Decimal("1") and not self.issues


def load_json_schema_compliance_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate the complete reviewed json-schema-compliance-v1 dataset."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    if dataset.benchmark_version != JSON_SCHEMA_COMPLIANCE_BENCHMARK_VERSION:
        raise ValueError(
            "JSON schema compliance v1 requires benchmark_version json-schema-compliance-v1"
        )

    case_ids = [case.case_id for case in dataset.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("JSON schema compliance v1 case IDs must be unique")
    if len(dataset.cases) != _EXPECTED_CASE_COUNT:
        raise ValueError("JSON schema compliance v1 requires exactly six reviewed cases")

    for case in dataset.cases:
        validate_json_schema_compliance_case(case)
    return dataset


def validate_json_schema_compliance_case(case: BenchmarkCase) -> None:
    """Fail closed when a case drifts from the reviewed v1 compliance contract."""
    if case.workload is not BenchmarkWorkload.JSON_SCHEMA_COMPLIANCE:
        raise ValueError("JSON schema compliance v1 dataset contains a different workload")
    if case.scorer != JSON_SCHEMA_COMPLIANCE_SCORER_ID:
        raise ValueError("JSON schema compliance v1 requires its versioned deterministic scorer")

    metadata = case.metadata
    unknown_metadata = sorted(set(metadata) - _ALLOWED_METADATA_FIELDS)
    if unknown_metadata:
        fields = ", ".join(unknown_metadata)
        raise ValueError(f"JSON schema compliance v1 metadata contains unknown fields: {fields}")
    if metadata.get("contract_version") != JSON_SCHEMA_COMPLIANCE_CONTRACT_VERSION:
        raise ValueError("JSON schema compliance v1 contract_version must be 1.0")
    if metadata.get("synthetic") is not True:
        raise ValueError("JSON schema compliance v1 cases must be explicitly synthetic")

    language = metadata.get("language")
    if not isinstance(language, str) or not language or language.strip() != language:
        raise ValueError("JSON schema compliance v1 language must be a normalized string")

    schema = metadata.get("output_schema")
    if not isinstance(schema, dict) or not schema:
        raise ValueError("JSON schema compliance v1 output_schema must be a non-empty object")
    _validate_reviewed_schema(schema)

    reference_issues = _schema_issues(schema, case.expected)
    if reference_issues:
        first = reference_issues[0]
        raise ValueError(
            "JSON schema compliance v1 reference example does not satisfy output_schema: "
            f"{first.code} at {first.path}"
        )

    expected_prompt = _build_prompt(schema)
    if case.prompt != expected_prompt:
        raise ValueError("JSON schema compliance v1 prompt must exactly materialize output_schema")


def assess_json_schema_compliance(
    case: BenchmarkCase,
    output: JsonValue,
) -> JsonSchemaComplianceAssessment:
    """Return binary deterministic compliance evidence for normalized JSON output."""
    validate_json_schema_compliance_case(case)
    schema = case.metadata["output_schema"]
    if not isinstance(schema, dict):
        raise AssertionError("validated JSON schema compliance case is inconsistent")

    issues = _schema_issues(schema, output)
    score = Decimal("1") if not issues else Decimal("0")
    return JsonSchemaComplianceAssessment(score=score, issues=issues)


def score_json_schema_compliance(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Return the scalar v1 score consumed by BenchmarkRunner."""
    return assess_json_schema_compliance(case, output).score


def _validate_reviewed_schema(schema: Mapping[str, JsonValue]) -> None:
    spec = StructuredOutputSchema(name="benchmark_schema", schema=dict(schema))
    try:
        validate_structured_output_schema(spec)
    except InvalidSchemaError as exc:
        raise ValueError(
            "JSON schema compliance v1 output_schema must satisfy the reviewed Phase 7 subset"
        ) from exc


def _schema_issues(
    schema: Mapping[str, JsonValue],
    output: JsonValue,
) -> tuple[JsonSchemaComplianceIssue, ...]:
    validator = Draft202012Validator(dict(schema))
    issues = {
        JsonSchemaComplianceIssue(
            code=_validator_code(error.validator),
            path=_json_pointer_path(tuple(error.absolute_path)),
        )
        for error in validator.iter_errors(output)
    }
    return tuple(sorted(issues))


def _validator_code(value: object) -> str:
    if isinstance(value, str) and value:
        return f"schema_{value}"
    return "schema_violation"


def _json_pointer_path(parts: tuple[object, ...]) -> str:
    if not parts:
        return "/"
    encoded = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(encoded)


def _build_prompt(schema: Mapping[str, JsonValue]) -> str:
    canonical_schema = json.dumps(
        dict(schema),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return f"{_PROMPT_PREFIX}{canonical_schema}"
