"""Canonical dataset and benchmark snapshot serialization."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path

from .contracts import (
    BenchmarkCase,
    BenchmarkObservation,
    BenchmarkSnapshot,
    BenchmarkTarget,
    JsonValue,
    Scorecard,
)


def dataset_digest(cases: Sequence[BenchmarkCase]) -> str:
    """Return a deterministic digest over the complete versioned dataset content."""

    payload = [_case_payload(case) for case in cases]
    return _sha256(_canonical_bytes(payload))


def build_snapshot(
    *,
    benchmark_version: str,
    runner_version: str,
    run_date: date,
    cases: Sequence[BenchmarkCase],
    targets: Sequence[BenchmarkTarget],
    observations: Sequence[BenchmarkObservation],
    scorecards: Sequence[Scorecard],
) -> BenchmarkSnapshot:
    """Build a reproducible snapshot whose ID covers all routing-quality evidence."""

    for name, value in (
        ("benchmark_version", benchmark_version),
        ("runner_version", runner_version),
    ):
        if not value or value.strip() != value:
            raise ValueError(f"{name} must be non-empty and normalized")

    dataset_sha = dataset_digest(cases)
    base_payload = {
        "schema_version": "1.0",
        "benchmark_version": benchmark_version,
        "runner_version": runner_version,
        "run_date": run_date.isoformat(),
        "dataset_digest": dataset_sha,
        "targets": [_target_payload(target) for target in targets],
        "observations": [_observation_payload(item) for item in observations],
        "scorecards": [_scorecard_payload(item) for item in scorecards],
    }
    snapshot_id = _sha256(_canonical_bytes(base_payload))
    return BenchmarkSnapshot(
        schema_version="1.0",
        benchmark_version=benchmark_version,
        runner_version=runner_version,
        run_date=run_date,
        dataset_digest=dataset_sha,
        snapshot_id=snapshot_id,
        targets=tuple(targets),
        observations=tuple(observations),
        scorecards=tuple(scorecards),
    )


def canonical_snapshot_json(snapshot: BenchmarkSnapshot) -> str:
    """Serialize a snapshot in stable canonical JSON for reviewable evidence artifacts."""

    payload = {
        "schema_version": snapshot.schema_version,
        "benchmark_version": snapshot.benchmark_version,
        "runner_version": snapshot.runner_version,
        "run_date": snapshot.run_date.isoformat(),
        "dataset_digest": snapshot.dataset_digest,
        "snapshot_id": snapshot.snapshot_id,
        "targets": [_target_payload(target) for target in snapshot.targets],
        "observations": [_observation_payload(item) for item in snapshot.observations],
        "scorecards": [_scorecard_payload(item) for item in snapshot.scorecards],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def persist_snapshot(root: Path, snapshot: BenchmarkSnapshot) -> Path:
    """Persist immutable evidence under benchmark-version/snapshot-id.json."""

    version_dir = root / snapshot.benchmark_version
    version_dir.mkdir(parents=True, exist_ok=True)
    path = version_dir / f"{snapshot.snapshot_id.removeprefix('sha256:')}.json"
    content = canonical_snapshot_json(snapshot)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError("snapshot ID collision with different content")
        return path
    path.write_text(content, encoding="utf-8")
    return path


def _case_payload(case: BenchmarkCase) -> dict[str, object]:
    return {
        "case_id": case.case_id,
        "workload": case.workload.value,
        "scorer": case.scorer,
        "prompt": case.prompt,
        "expected": _json_value(case.expected),
        "metadata": _mapping_payload(case.metadata),
    }


def _target_payload(target: BenchmarkTarget) -> dict[str, object]:
    return {
        "target_id": target.target_id,
        "provider": target.provider,
        "model": target.model,
        "api": target.api,
        "configuration": target.configuration,
        "source_date": target.source_date.isoformat(),
    }


def _observation_payload(item: BenchmarkObservation) -> dict[str, object]:
    return {
        "target_id": item.target_id,
        "case_id": item.case_id,
        "workload": item.workload.value,
        "status": item.status.value,
        "quality_score": _decimal(item.quality_score),
        "latency_ms": item.latency_ms,
        "ttft_ms": item.ttft_ms,
        "input_units": item.input_units,
        "output_units": item.output_units,
        "cost_usd": _decimal(item.cost_usd),
        "fallback_count": item.fallback_count,
        "provider_error_code": item.provider_error_code,
        "provider_error_status": item.provider_error_status,
    }


def _scorecard_payload(item: Scorecard) -> dict[str, object]:
    return {
        "target_id": item.target_id,
        "workload": item.workload.value,
        "total_cases": item.total_cases,
        "completed_calls": item.completed_calls,
        "provider_failures": item.provider_failures,
        "quality_successes": item.quality_successes,
        "quality_failures": item.quality_failures,
        "availability_rate": _decimal(item.availability_rate),
        "quality_success_rate": _decimal(item.quality_success_rate),
        "mean_quality_score": _decimal(item.mean_quality_score),
        "latency_p50_ms": item.latency_p50_ms,
        "latency_p95_ms": item.latency_p95_ms,
        "ttft_p50_ms": item.ttft_p50_ms,
        "ttft_p95_ms": item.ttft_p95_ms,
        "total_input_units": item.total_input_units,
        "total_output_units": item.total_output_units,
        "total_cost_usd": _decimal(item.total_cost_usd),
        "rate_limit_errors": item.rate_limit_errors,
        "fallback_frequency": _decimal(item.fallback_frequency),
        "provider_error_counts": dict(sorted(item.provider_error_counts.items())),
    }


def _mapping_payload(value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    return {key: _json_value(item) for key, item in sorted(value.items())}


def _json_value(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()
