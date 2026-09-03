"""Strict loader for versioned public/synthetic benchmark datasets."""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

_ALLOWED_TOP_LEVEL = {"schema_version", "benchmark_version", "data_classification", "cases"}
_ALLOWED_CASE_KEYS = {"case_id", "workload", "scorer", "prompt", "expected", "metadata"}


def load_dataset(path: Path) -> BenchmarkDataset:
    """Load a benchmark dataset and reject unknown fields or malformed case definitions."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("benchmark dataset root must be an object")
    _reject_unknown(payload, _ALLOWED_TOP_LEVEL, "benchmark dataset")

    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("benchmark dataset cases must be a list")

    cases: list[BenchmarkCase] = []
    for index, raw_case in enumerate(raw_cases):
        if not isinstance(raw_case, dict):
            raise ValueError(f"benchmark case {index} must be an object")
        _reject_unknown(raw_case, _ALLOWED_CASE_KEYS, f"benchmark case {index}")
        metadata = raw_case.get("metadata", {})
        if not isinstance(metadata, dict):
            raise ValueError(f"benchmark case {index} metadata must be an object")
        cases.append(
            BenchmarkCase(
                case_id=_required_string(raw_case, "case_id", index),
                workload=BenchmarkWorkload(_required_string(raw_case, "workload", index)),
                scorer=_required_string(raw_case, "scorer", index),
                prompt=_required_string(raw_case, "prompt", index),
                expected=_json_value(raw_case.get("expected"), f"benchmark case {index} expected"),
                metadata={
                    str(key): _json_value(value, f"benchmark case {index} metadata.{key}")
                    for key, value in metadata.items()
                },
            )
        )

    return BenchmarkDataset(
        schema_version=_root_string(payload, "schema_version"),
        benchmark_version=_root_string(payload, "benchmark_version"),
        data_classification=_root_string(payload, "data_classification"),
        cases=tuple(cases),
    )


def _reject_unknown(payload: dict[str, object], allowed: set[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {', '.join(unknown)}")


def _required_string(payload: dict[str, object], key: str, index: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"benchmark case {index} {key} must be a string")
    return value


def _root_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"benchmark dataset {key} must be a string")
    return value


def _json_value(value: object, label: str) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [_json_value(item, label) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError(f"{label} object keys must be strings")
        return {str(key): _json_value(item, label) for key, item in value.items()}
    raise ValueError(f"{label} must contain only JSON-compatible values")
