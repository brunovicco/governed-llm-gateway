"""Strict loading for immutable persisted benchmark snapshots."""

import hashlib
import json
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .contracts import (
    BenchmarkObservation,
    BenchmarkQualityMetric,
    BenchmarkSnapshot,
    BenchmarkTarget,
    BenchmarkWorkload,
    ObservationStatus,
    Scorecard,
)
from .snapshot import canonical_snapshot_json


def load_snapshot(path: Path) -> BenchmarkSnapshot:
    """Load one persisted snapshot and verify its content-addressed identity."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    payload = _mapping(raw, "snapshot")
    snapshot_id = _string(payload.get("snapshot_id"), "snapshot_id")

    identity_payload = dict(payload)
    identity_payload.pop("snapshot_id", None)
    expected_id = _sha256(_canonical_bytes(identity_payload))
    if snapshot_id != expected_id:
        raise ValueError(
            f"snapshot_id mismatch: persisted {snapshot_id!r}, computed {expected_id!r}"
        )

    snapshot = BenchmarkSnapshot(
        schema_version=_string(payload.get("schema_version"), "schema_version"),
        benchmark_version=_string(payload.get("benchmark_version"), "benchmark_version"),
        runner_version=_string(payload.get("runner_version"), "runner_version"),
        run_date=date.fromisoformat(_string(payload.get("run_date"), "run_date")),
        dataset_digest=_string(payload.get("dataset_digest"), "dataset_digest"),
        snapshot_id=snapshot_id,
        targets=tuple(_target(item) for item in _list(payload.get("targets"), "targets")),
        observations=tuple(
            _observation(item) for item in _list(payload.get("observations"), "observations")
        ),
        scorecards=tuple(
            _scorecard(item) for item in _list(payload.get("scorecards"), "scorecards")
        ),
        target_matrix_version=_optional_string(payload.get("target_matrix_version")),
        target_matrix_digest=_optional_string(payload.get("target_matrix_digest")),
    )

    canonical_loaded = canonical_snapshot_json(snapshot)
    canonical_persisted = (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    )
    if canonical_loaded != canonical_persisted:
        raise ValueError("persisted snapshot contains unsupported or non-canonical fields")
    return snapshot


def _target(value: object) -> BenchmarkTarget:
    payload = _mapping(value, "target")
    return BenchmarkTarget(
        target_id=_string(payload.get("target_id"), "target.target_id"),
        provider=_string(payload.get("provider"), "target.provider"),
        model=_string(payload.get("model"), "target.model"),
        api=_string(payload.get("api"), "target.api"),
        configuration=_string(payload.get("configuration"), "target.configuration"),
        source_date=date.fromisoformat(_string(payload.get("source_date"), "target.source_date")),
        api_family=_optional_string(payload.get("api_family")),
        max_output_tokens=_optional_int(
            payload.get("max_output_tokens"),
            "target.max_output_tokens",
        ),
    )


def _observation(value: object) -> BenchmarkObservation:
    payload = _mapping(value, "observation")
    return BenchmarkObservation(
        target_id=_string(payload.get("target_id"), "observation.target_id"),
        case_id=_string(payload.get("case_id"), "observation.case_id"),
        workload=BenchmarkWorkload(_string(payload.get("workload"), "observation.workload")),
        status=ObservationStatus(_string(payload.get("status"), "observation.status")),
        quality_score=_optional_decimal(payload.get("quality_score"), "observation.quality_score"),
        latency_ms=_optional_int(payload.get("latency_ms"), "observation.latency_ms"),
        ttft_ms=_optional_int(payload.get("ttft_ms"), "observation.ttft_ms"),
        input_units=_optional_int(payload.get("input_units"), "observation.input_units"),
        output_units=_optional_int(payload.get("output_units"), "observation.output_units"),
        cost_usd=_optional_decimal(payload.get("cost_usd"), "observation.cost_usd"),
        fallback_count=_int(payload.get("fallback_count"), "observation.fallback_count"),
        provider_error_code=_optional_string(payload.get("provider_error_code")),
        provider_error_status=_optional_int(
            payload.get("provider_error_status"), "observation.provider_error_status"
        ),
        provider=_optional_string(payload.get("provider")),
        model=_optional_string(payload.get("model")),
        deployment=_optional_string(payload.get("deployment")),
        api_family=_optional_string(payload.get("api_family")),
        max_output_tokens=_optional_int(
            payload.get("max_output_tokens"), "observation.max_output_tokens"
        ),
        quality_metrics=_quality_metrics(payload.get("quality_metrics")),
    )


def _scorecard(value: object) -> Scorecard:
    payload = _mapping(value, "scorecard")
    return Scorecard(
        target_id=_string(payload.get("target_id"), "scorecard.target_id"),
        workload=BenchmarkWorkload(_string(payload.get("workload"), "scorecard.workload")),
        total_cases=_int(payload.get("total_cases"), "scorecard.total_cases"),
        completed_calls=_int(payload.get("completed_calls"), "scorecard.completed_calls"),
        provider_failures=_int(payload.get("provider_failures"), "scorecard.provider_failures"),
        quality_successes=_int(payload.get("quality_successes"), "scorecard.quality_successes"),
        quality_failures=_int(payload.get("quality_failures"), "scorecard.quality_failures"),
        availability_rate=_decimal(payload.get("availability_rate"), "scorecard.availability_rate"),
        quality_success_rate=_optional_decimal(
            payload.get("quality_success_rate"), "scorecard.quality_success_rate"
        ),
        mean_quality_score=_optional_decimal(
            payload.get("mean_quality_score"), "scorecard.mean_quality_score"
        ),
        latency_p50_ms=_optional_int(payload.get("latency_p50_ms"), "scorecard.latency_p50_ms"),
        latency_p95_ms=_optional_int(payload.get("latency_p95_ms"), "scorecard.latency_p95_ms"),
        ttft_p50_ms=_optional_int(payload.get("ttft_p50_ms"), "scorecard.ttft_p50_ms"),
        ttft_p95_ms=_optional_int(payload.get("ttft_p95_ms"), "scorecard.ttft_p95_ms"),
        total_input_units=_int(payload.get("total_input_units"), "scorecard.total_input_units"),
        total_output_units=_int(payload.get("total_output_units"), "scorecard.total_output_units"),
        total_cost_usd=_decimal(payload.get("total_cost_usd"), "scorecard.total_cost_usd"),
        rate_limit_errors=_int(payload.get("rate_limit_errors"), "scorecard.rate_limit_errors"),
        fallback_frequency=_decimal(
            payload.get("fallback_frequency"),
            "scorecard.fallback_frequency",
        ),
        provider_error_counts=_string_int_mapping(payload.get("provider_error_counts")),
        mean_quality_metrics=_quality_metrics(payload.get("mean_quality_metrics")),
    )


def _quality_metrics(value: object) -> dict[BenchmarkQualityMetric, Decimal]:
    if value is None:
        return {}
    payload = _mapping(value, "quality_metrics")
    return {
        BenchmarkQualityMetric(_string(key, "quality_metrics key")): _decimal(
            score, f"quality_metrics.{key}"
        )
        for key, score in payload.items()
    }


def _string_int_mapping(value: object) -> dict[str, int]:
    payload = _mapping(value, "provider_error_counts")
    return {
        _string(key, "provider_error_counts key"): _int(count, f"provider_error_counts.{key}")
        for key, count in payload.items()
    }


def _mapping(value: object, field: str) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{field} must be a normalized non-empty string")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _string(value, "optional string")


def _int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer")
    return value


def _optional_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    return _int(value, field)


def _decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a decimal string")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be a decimal string") from exc


def _optional_decimal(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    return _decimal(value, field)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()
