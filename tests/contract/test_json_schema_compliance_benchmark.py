import json
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.contracts import BenchmarkWorkload, JsonValue
from benchmarks.dataset import load_dataset
from benchmarks.scoring import build_default_scorers
from benchmarks.snapshot import dataset_digest
from benchmarks.workloads.json_schema_compliance import (
    JSON_SCHEMA_COMPLIANCE_BENCHMARK_VERSION,
    JSON_SCHEMA_COMPLIANCE_SCORER_ID,
    JsonSchemaComplianceIssue,
    assess_json_schema_compliance,
    load_json_schema_compliance_dataset,
    validate_json_schema_compliance_case,
)

_DATASET_PATH = Path("benchmarks/datasets/json-schema-compliance-v1.json")


def _expected(case_index: int) -> JsonValue:
    return deepcopy(load_json_schema_compliance_dataset(_DATASET_PATH).cases[case_index].expected)


def test_checked_in_json_schema_compliance_dataset_covers_reviewed_boundary() -> None:
    dataset = load_json_schema_compliance_dataset(_DATASET_PATH)

    assert dataset.benchmark_version == JSON_SCHEMA_COMPLIANCE_BENCHMARK_VERSION
    assert len(dataset.cases) == 6
    for case in dataset.cases:
        assert case.workload is BenchmarkWorkload.JSON_SCHEMA_COMPLIANCE
        assert case.scorer == JSON_SCHEMA_COMPLIANCE_SCORER_ID
        assert case.metadata["synthetic"] is True
        assert case.metadata["language"] == "en"
        assert "Schema: {" in case.prompt


def test_json_schema_compliance_dataset_digest_is_deterministic() -> None:
    first = load_json_schema_compliance_dataset(_DATASET_PATH)
    second = load_json_schema_compliance_dataset(_DATASET_PATH)

    assert dataset_digest(first.cases) == dataset_digest(second.cases)


def test_json_schema_compliance_accepts_reviewed_reference_example() -> None:
    case = load_json_schema_compliance_dataset(_DATASET_PATH).cases[0]
    assessment = assess_json_schema_compliance(case, _expected(0))

    assert assessment.score == Decimal("1")
    assert assessment.schema_valid is True
    assert assessment.issues == ()


def test_json_schema_compliance_accepts_different_schema_valid_values() -> None:
    case = load_json_schema_compliance_dataset(_DATASET_PATH).cases[0]
    output: JsonValue = {"name": "different", "active": False}

    assessment = assess_json_schema_compliance(case, output)

    assert output != case.expected
    assert assessment.score == Decimal("1")
    assert assessment.schema_valid is True


def test_json_schema_compliance_reports_nested_wrong_type() -> None:
    case = load_json_schema_compliance_dataset(_DATASET_PATH).cases[1]
    output: JsonValue = {"profile": {"tier": "pro", "seats": "three"}}

    assessment = assess_json_schema_compliance(case, output)

    assert assessment.score == Decimal("0")
    assert assessment.schema_valid is False
    assert JsonSchemaComplianceIssue("schema_type", "/profile/seats") in assessment.issues


def test_json_schema_compliance_reports_missing_required_field() -> None:
    case = load_json_schema_compliance_dataset(_DATASET_PATH).cases[0]
    output: JsonValue = {"name": "alpha"}

    assessment = assess_json_schema_compliance(case, output)

    assert assessment.score == Decimal("0")
    assert JsonSchemaComplianceIssue("schema_required", "/") in assessment.issues


def test_json_schema_compliance_reports_additional_property() -> None:
    case = load_json_schema_compliance_dataset(_DATASET_PATH).cases[3]
    output: JsonValue = {"status": "ready", "extra": True}

    assessment = assess_json_schema_compliance(case, output)

    assert assessment.score == Decimal("0")
    assert JsonSchemaComplianceIssue("schema_additionalProperties", "/") in assessment.issues


def test_json_schema_compliance_reports_enum_violation() -> None:
    case = load_json_schema_compliance_dataset(_DATASET_PATH).cases[3]
    output: JsonValue = {"status": "unknown"}

    assessment = assess_json_schema_compliance(case, output)

    assert assessment.score == Decimal("0")
    assert JsonSchemaComplianceIssue("schema_enum", "/status") in assessment.issues


def test_json_schema_compliance_reports_array_uniqueness_violation() -> None:
    case = load_json_schema_compliance_dataset(_DATASET_PATH).cases[2]
    output: JsonValue = ["alpha", "alpha"]

    assessment = assess_json_schema_compliance(case, output)

    assert assessment.score == Decimal("0")
    assert JsonSchemaComplianceIssue("schema_uniqueItems", "/") in assessment.issues


def test_json_schema_compliance_reports_numeric_bound_violation() -> None:
    case = load_json_schema_compliance_dataset(_DATASET_PATH).cases[5]
    output: JsonValue = {"ratio": 2.0, "count": 2}

    assessment = assess_json_schema_compliance(case, output)

    assert assessment.score == Decimal("0")
    assert JsonSchemaComplianceIssue("schema_maximum", "/ratio") in assessment.issues


def test_json_schema_compliance_contract_rejects_prompt_schema_drift() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, prompt=f"{case.prompt} ")

    with pytest.raises(ValueError, match="exactly materialize output_schema"):
        validate_json_schema_compliance_case(drifted)


def test_json_schema_compliance_contract_rejects_invalid_reference_example() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, expected={"name": "alpha"})

    with pytest.raises(ValueError, match="reference example does not satisfy output_schema"):
        validate_json_schema_compliance_case(drifted)


def test_json_schema_compliance_contract_reuses_phase7_schema_boundary() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted_schema: dict[str, JsonValue] = {"type": "string", "pattern": "^unsafe-drift$"}
    drifted = replace(case, metadata={**case.metadata, "output_schema": drifted_schema})

    with pytest.raises(ValueError, match="reviewed Phase 7 subset"):
        validate_json_schema_compliance_case(drifted)


def test_json_schema_compliance_contract_rejects_unknown_metadata() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "provider_hint": "openai"})

    with pytest.raises(ValueError, match="unknown fields: provider_hint"):
        validate_json_schema_compliance_case(drifted)


def test_json_schema_compliance_dataset_requires_exact_case_count(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    payload["cases"] = cases[:-1]
    path = tmp_path / "json-schema-compliance-incomplete.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="requires exactly six reviewed cases"):
        load_json_schema_compliance_dataset(path)


def test_json_schema_compliance_dataset_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    first = cases[0]
    second = cases[1]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    second["case_id"] = first["case_id"]
    path = tmp_path / "json-schema-compliance-duplicate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_json_schema_compliance_dataset(path)


def test_json_schema_compliance_scorer_is_registered() -> None:
    scorers = build_default_scorers()

    assert JSON_SCHEMA_COMPLIANCE_SCORER_ID in scorers
