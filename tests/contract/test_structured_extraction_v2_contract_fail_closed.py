"""Fail-closed regressions for the structured-extraction v2 benchmark contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.workloads.structured_extraction_v2 import load_structured_extraction_v2_dataset

_DATASET = Path("benchmarks/datasets/structured-extraction-v2.json")


def _payload() -> dict[str, object]:
    value = json.loads(_DATASET.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "structured-extraction-v2-invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_rejects_wrong_benchmark_version(tmp_path: Path) -> None:
    payload = _payload()
    payload["benchmark_version"] = "structured-extraction-v1"

    with pytest.raises(ValueError, match="requires benchmark_version"):
        load_structured_extraction_v2_dataset(_write(tmp_path, payload))


def test_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = _payload()
    cases = payload["cases"]
    assert isinstance(cases, list)
    assert isinstance(cases[0], dict)
    assert isinstance(cases[1], dict)
    cases[1]["case_id"] = cases[0]["case_id"]

    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_structured_extraction_v2_dataset(_write(tmp_path, payload))


def test_rejects_unknown_metadata_fields(tmp_path: Path) -> None:
    payload = _payload()
    cases = payload["cases"]
    assert isinstance(cases, list)
    first = cases[0]
    assert isinstance(first, dict)
    metadata = first["metadata"]
    assert isinstance(metadata, dict)
    metadata["normalizer"] = "permissive"

    with pytest.raises(ValueError, match="metadata contains unknown fields"):
        load_structured_extraction_v2_dataset(_write(tmp_path, payload))


def test_rejects_unsupported_schema_type(tmp_path: Path) -> None:
    payload = _payload()
    cases = payload["cases"]
    assert isinstance(cases, list)
    first = cases[0]
    assert isinstance(first, dict)
    metadata = first["metadata"]
    assert isinstance(metadata, dict)
    schema = metadata["output_schema"]
    assert isinstance(schema, dict)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    properties["line_count"] = {"type": "int32"}

    with pytest.raises(ValueError, match="unsupported types"):
        load_structured_extraction_v2_dataset(_write(tmp_path, payload))


def test_rejects_enum_values_with_wrong_type(tmp_path: Path) -> None:
    payload = _payload()
    cases = payload["cases"]
    assert isinstance(cases, list)
    first = cases[0]
    assert isinstance(first, dict)
    metadata = first["metadata"]
    assert isinstance(metadata, dict)
    schema = metadata["output_schema"]
    assert isinstance(schema, dict)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    currency = properties["currency"]
    assert isinstance(currency, dict)
    currency["enum"] = ["BRL", 7]

    with pytest.raises(ValueError, match="enum value 1 has wrong type"):
        load_structured_extraction_v2_dataset(_write(tmp_path, payload))


def test_rejects_required_field_not_declared_in_properties(tmp_path: Path) -> None:
    payload = _payload()
    cases = payload["cases"]
    assert isinstance(cases, list)
    first = cases[0]
    assert isinstance(first, dict)
    metadata = first["metadata"]
    assert isinstance(metadata, dict)
    schema = metadata["output_schema"]
    assert isinstance(schema, dict)
    required = schema["required"]
    assert isinstance(required, list)
    required.append("unknown")

    with pytest.raises(ValueError, match="required fields must exist in properties"):
        load_structured_extraction_v2_dataset(_write(tmp_path, payload))


def test_rejects_array_without_item_schema(tmp_path: Path) -> None:
    payload = _payload()
    cases = payload["cases"]
    assert isinstance(cases, list)
    incident = cases[3]
    assert isinstance(incident, dict)
    metadata = incident["metadata"]
    assert isinstance(metadata, dict)
    schema = metadata["output_schema"]
    assert isinstance(schema, dict)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    regions = properties["impacted_regions"]
    assert isinstance(regions, dict)
    regions.pop("items")

    with pytest.raises(ValueError, match="requires items"):
        load_structured_extraction_v2_dataset(_write(tmp_path, payload))
