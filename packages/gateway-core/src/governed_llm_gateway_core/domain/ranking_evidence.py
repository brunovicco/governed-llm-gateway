"""Strict runtime contract for explicitly promoted benchmark-derived ranking evidence.

The runtime validates a compiled artifact without importing the repository-level
``benchmarks`` package. Evidence remains subordinate to PDP authorization and the
normal gateway eligibility gates.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


class RankingEvidenceError(ValueError):
    """Raised when promoted benchmark evidence is malformed or tampered with."""


@dataclass(frozen=True, slots=True)
class RankingEvidenceRecord:
    """Validated empirical evidence for one runtime workload/deployment pair."""

    target_id: str
    deployment_id: str
    benchmark_workload: str
    runtime_workload: str
    total_cases: int
    completed_calls: int
    quality_score: Decimal
    availability_rate: Decimal
    latency_p95_ms: int | None
    cost_per_completed_call_usd: Decimal | None
    fallback_frequency: Decimal


@dataclass(frozen=True, slots=True)
class PromotedRankingEvidence:
    """Validated content-addressed promotion artifact consumable by runtime configuration."""

    schema_version: str
    promotion_version: str
    approval_date: date
    approved_by: str
    benchmark_snapshot_id: str
    benchmark_version: str
    dataset_digest: str
    evidence_id: str
    records: tuple[RankingEvidenceRecord, ...]

    def for_runtime(
        self, runtime_workload: str, deployment_id: str
    ) -> RankingEvidenceRecord | None:
        """Return promoted evidence for an already-known runtime candidate, when present."""
        for record in self.records:
            if (
                record.runtime_workload == runtime_workload
                and record.deployment_id == deployment_id
            ):
                return record
        return None


def build_promoted_ranking_evidence(payload: Mapping[str, object]) -> PromotedRankingEvidence:
    """Validate a Phase 11 promotion artifact and verify its content-derived identity."""
    allowed = {
        "schema_version",
        "promotion_version",
        "approval_date",
        "approved_by",
        "benchmark_snapshot_id",
        "benchmark_version",
        "dataset_digest",
        "evidence_id",
        "records",
    }
    _require_exact_fields(payload, allowed, "promoted ranking evidence")
    schema_version = _require_string(payload["schema_version"], "schema_version")
    if schema_version != "1.0":
        raise RankingEvidenceError("promoted ranking evidence schema_version must be '1.0'")

    promotion_version = _require_normalized(payload["promotion_version"], "promotion_version")
    approval_date = _require_date(payload["approval_date"], "approval_date")
    approved_by = _require_normalized(payload["approved_by"], "approved_by")
    benchmark_snapshot_id = _require_sha256(
        payload["benchmark_snapshot_id"], "benchmark_snapshot_id"
    )
    benchmark_version = _require_normalized(payload["benchmark_version"], "benchmark_version")
    dataset_digest = _require_sha256(payload["dataset_digest"], "dataset_digest")
    evidence_id = _require_sha256(payload["evidence_id"], "evidence_id")

    raw_records = payload["records"]
    if not isinstance(raw_records, list) or not raw_records:
        raise RankingEvidenceError("records must be a non-empty list")
    records: list[RankingEvidenceRecord] = []
    seen_runtime: set[tuple[str, str]] = set()
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, Mapping):
            raise RankingEvidenceError(f"records[{index}] must be a mapping")
        record = _build_record(raw_record, index)
        key = (record.runtime_workload, record.deployment_id)
        if key in seen_runtime:
            raise RankingEvidenceError("duplicate runtime workload/deployment evidence record")
        seen_runtime.add(key)
        records.append(record)

    records_tuple = tuple(
        sorted(
            records,
            key=lambda item: (item.runtime_workload, item.deployment_id, item.target_id),
        )
    )
    canonical_without_id = {
        "schema_version": schema_version,
        "promotion_version": promotion_version,
        "approval_date": approval_date.isoformat(),
        "approved_by": approved_by,
        "benchmark_snapshot_id": benchmark_snapshot_id,
        "benchmark_version": benchmark_version,
        "dataset_digest": dataset_digest,
        "records": [_record_payload(record) for record in records_tuple],
    }
    expected_id = _sha256_payload(canonical_without_id)
    if evidence_id != expected_id:
        raise RankingEvidenceError("evidence_id does not match canonical promoted evidence content")

    return PromotedRankingEvidence(
        schema_version=schema_version,
        promotion_version=promotion_version,
        approval_date=approval_date,
        approved_by=approved_by,
        benchmark_snapshot_id=benchmark_snapshot_id,
        benchmark_version=benchmark_version,
        dataset_digest=dataset_digest,
        evidence_id=evidence_id,
        records=records_tuple,
    )


def _build_record(payload: Mapping[str, object], index: int) -> RankingEvidenceRecord:
    allowed = {
        "target_id",
        "deployment_id",
        "benchmark_workload",
        "runtime_workload",
        "total_cases",
        "completed_calls",
        "quality_score",
        "availability_rate",
        "latency_p95_ms",
        "cost_per_completed_call_usd",
        "fallback_frequency",
    }
    location = f"records[{index}]"
    _require_exact_fields(payload, allowed, location)
    target_id = _require_normalized(payload["target_id"], f"{location}.target_id")
    deployment_id = _require_normalized(payload["deployment_id"], f"{location}.deployment_id")
    benchmark_workload = _require_normalized(
        payload["benchmark_workload"], f"{location}.benchmark_workload"
    )
    runtime_workload = _require_normalized(
        payload["runtime_workload"], f"{location}.runtime_workload"
    )
    if "." not in runtime_workload:
        raise RankingEvidenceError(f"{location}.runtime_workload must be dotted")

    total_cases = _require_positive_int(payload["total_cases"], f"{location}.total_cases")
    completed_calls = _require_positive_int(
        payload["completed_calls"], f"{location}.completed_calls"
    )
    if completed_calls > total_cases:
        raise RankingEvidenceError(f"{location}.completed_calls cannot exceed total_cases")

    quality_score = _require_unit_decimal(payload["quality_score"], f"{location}.quality_score")
    availability_rate = _require_unit_decimal(
        payload["availability_rate"], f"{location}.availability_rate"
    )
    fallback_frequency = _require_unit_decimal(
        payload["fallback_frequency"], f"{location}.fallback_frequency"
    )
    latency_p95_ms = _require_optional_nonnegative_int(
        payload["latency_p95_ms"], f"{location}.latency_p95_ms"
    )
    cost_per_call = _require_optional_nonnegative_decimal(
        payload["cost_per_completed_call_usd"],
        f"{location}.cost_per_completed_call_usd",
    )
    return RankingEvidenceRecord(
        target_id=target_id,
        deployment_id=deployment_id,
        benchmark_workload=benchmark_workload,
        runtime_workload=runtime_workload,
        total_cases=total_cases,
        completed_calls=completed_calls,
        quality_score=quality_score,
        availability_rate=availability_rate,
        latency_p95_ms=latency_p95_ms,
        cost_per_completed_call_usd=cost_per_call,
        fallback_frequency=fallback_frequency,
    )


def _record_payload(record: RankingEvidenceRecord) -> dict[str, object]:
    return {
        "target_id": record.target_id,
        "deployment_id": record.deployment_id,
        "benchmark_workload": record.benchmark_workload,
        "runtime_workload": record.runtime_workload,
        "total_cases": record.total_cases,
        "completed_calls": record.completed_calls,
        "quality_score": _decimal_text(record.quality_score),
        "availability_rate": _decimal_text(record.availability_rate),
        "latency_p95_ms": record.latency_p95_ms,
        "cost_per_completed_call_usd": _decimal_text(record.cost_per_completed_call_usd),
        "fallback_frequency": _decimal_text(record.fallback_frequency),
    }


def _require_exact_fields(payload: Mapping[str, object], allowed: set[str], location: str) -> None:
    keys = set(payload)
    unknown = sorted(keys - allowed)
    if unknown:
        raise RankingEvidenceError(f"unknown {location} fields: {', '.join(unknown)}")
    missing = sorted(allowed - keys)
    if missing:
        raise RankingEvidenceError(f"missing {location} fields: {', '.join(missing)}")


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise RankingEvidenceError(f"{field} must be a string")
    return value


def _require_normalized(value: object, field: str) -> str:
    text = _require_string(value, field)
    if not text or text.strip() != text:
        raise RankingEvidenceError(f"{field} must be non-empty and normalized")
    return text


def _require_sha256(value: object, field: str) -> str:
    text = _require_normalized(value, field)
    prefix = "sha256:"
    digest = text.removeprefix(prefix)
    if not text.startswith(prefix) or len(digest) != 64:
        raise RankingEvidenceError(f"{field} must be a sha256: content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise RankingEvidenceError(f"{field} must contain a hexadecimal SHA-256 digest") from exc
    return text


def _require_date(value: object, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = _require_string(value, field)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise RankingEvidenceError(f"{field} must be an ISO date") from exc


def _require_positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RankingEvidenceError(f"{field} must be a positive integer")
    return value


def _require_decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str | int | float | Decimal):
        raise RankingEvidenceError(f"{field} must be decimal-compatible")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise RankingEvidenceError(f"{field} must be a valid decimal") from exc
    if not parsed.is_finite():
        raise RankingEvidenceError(f"{field} must be finite")
    return parsed


def _require_unit_decimal(value: object, field: str) -> Decimal:
    parsed = _require_decimal(value, field)
    if parsed < 0 or parsed > 1:
        raise RankingEvidenceError(f"{field} must be between 0 and 1")
    return parsed


def _require_optional_nonnegative_decimal(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    parsed = _require_decimal(value, field)
    if parsed < 0:
        raise RankingEvidenceError(f"{field} must be non-negative")
    return parsed


def _require_optional_nonnegative_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RankingEvidenceError(f"{field} must be a non-negative integer or null")
    return value


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _sha256_payload(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
