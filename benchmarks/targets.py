"""Strict loader for fully identified benchmark provider/model targets."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .contracts import BenchmarkTarget

_ALLOWED_ROOT = {"schema_version", "matrix_version", "targets"}
_ALLOWED_TARGET = {
    "target_id",
    "provider",
    "model",
    "api",
    "configuration",
    "source_date",
}


def load_targets(path: Path) -> tuple[str, tuple[BenchmarkTarget, ...]]:
    """Load the Phase 10 target matrix and reject ambiguous/unknown configuration fields."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("benchmark target matrix root must be an object")
    _reject_unknown(payload, _ALLOWED_ROOT, "benchmark target matrix")
    if payload.get("schema_version") != "1.0":
        raise ValueError("unsupported benchmark target matrix schema_version")
    matrix_version = _required_string(payload, "matrix_version", "benchmark target matrix")
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("benchmark target matrix must contain at least one target")

    targets: list[BenchmarkTarget] = []
    for index, raw_target in enumerate(raw_targets):
        if not isinstance(raw_target, dict):
            raise ValueError(f"benchmark target {index} must be an object")
        _reject_unknown(raw_target, _ALLOWED_TARGET, f"benchmark target {index}")
        source_date = _required_string(raw_target, "source_date", f"benchmark target {index}")
        targets.append(
            BenchmarkTarget(
                target_id=_required_string(raw_target, "target_id", f"benchmark target {index}"),
                provider=_required_string(raw_target, "provider", f"benchmark target {index}"),
                model=_required_string(raw_target, "model", f"benchmark target {index}"),
                api=_required_string(raw_target, "api", f"benchmark target {index}"),
                configuration=_required_string(
                    raw_target, "configuration", f"benchmark target {index}"
                ),
                source_date=date.fromisoformat(source_date),
            )
        )

    ids = [target.target_id for target in targets]
    if len(ids) != len(set(ids)):
        raise ValueError("benchmark target IDs must be unique")
    return matrix_version, tuple(targets)


def _reject_unknown(payload: dict[str, object], allowed: set[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {', '.join(unknown)}")


def _required_string(payload: dict[str, object], key: str, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{label} {key} must be a normalized non-empty string")
    return value
