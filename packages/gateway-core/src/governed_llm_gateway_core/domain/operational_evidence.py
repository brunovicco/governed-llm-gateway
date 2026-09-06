"""Strict content-addressed contract for recent operational ranking evidence.

Operational evidence is descriptive metadata only. It does not authorize models,
change eligibility, or alter ranking until a separate reviewed policy explicitly
consumes it.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

_IDENTIFIER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")


class OperationalEvidenceError(ValueError):
    """Raised when recent operational evidence is malformed or tampered with."""


@dataclass(frozen=True, slots=True)
class OperationalEvidenceRecord:
    """Recent operational measurements for one workload/deployment pair."""

    runtime_workload: str
    deployment_id: str
    gateway_request_count: int
    provider_attempt_count: int
    successful_provider_attempt_count: int
    provider_error_count: int
    rate_limit_error_count: int
    timeout_count: int
    fallback_request_count: int
    provider_latency_p50_ms: int
    provider_latency_p95_ms: int

    def __post_init__(self) -> None:
        """Reject inconsistent counters or ambiguous identifiers."""
        _validate_record(self)


@dataclass(frozen=True, slots=True)
class OperationalEvidenceSnapshot:
    """Immutable recent operational-evidence window with content-derived identity."""

    schema_version: str
    snapshot_version: str
    collector_id: str
    collector_version: str
    window_start: datetime
    window_end: datetime
    captured_at: datetime
    evidence_id: str
    records: tuple[OperationalEvidenceRecord, ...]

    def __post_init__(self) -> None:
        """Require canonical ordering, UTC provenance, and a valid content identity."""
        if self.schema_version != "1.0":
            raise OperationalEvidenceError("operational evidence schema_version must be '1.0'")
        _validate_identifier(self.snapshot_version, "snapshot_version")
        _validate_identifier(self.collector_id, "collector_id")
        _validate_identifier(self.collector_version, "collector_version")
        _validate_utc_datetime(self.window_start, "window_start")
        _validate_utc_datetime(self.window_end, "window_end")
        _validate_utc_datetime(self.captured_at, "captured_at")
        if self.window_start >= self.window_end:
            raise OperationalEvidenceError(
                "operational evidence window_start must precede window_end"
            )
        if self.captured_at < self.window_end:
            raise OperationalEvidenceError(
                "operational evidence captured_at cannot precede window_end"
            )
        if not isinstance(self.records, tuple) or not self.records:
            raise OperationalEvidenceError("operational evidence records must be a non-empty tuple")
        ordered = tuple(
            sorted(self.records, key=lambda item: (item.runtime_workload, item.deployment_id))
        )
        if self.records != ordered:
            raise OperationalEvidenceError(
                "operational evidence records must use canonical ordering"
            )
        keys = [(item.runtime_workload, item.deployment_id) for item in self.records]
        if len(keys) != len(set(keys)):
            raise OperationalEvidenceError(
                "duplicate runtime workload/deployment operational evidence record"
            )
        _validate_sha256(self.evidence_id, "evidence_id")
        expected = _sha256_payload(_snapshot_payload_without_id(self))
        if self.evidence_id != expected:
            raise OperationalEvidenceError(
                "evidence_id does not match canonical operational evidence content"
            )

    def for_runtime(
        self, runtime_workload: str, deployment_id: str
    ) -> OperationalEvidenceRecord | None:
        """Return descriptive evidence for an already-known runtime candidate."""
        for record in self.records:
            if (
                record.runtime_workload == runtime_workload
                and record.deployment_id == deployment_id
            ):
                return record
        return None


def build_operational_evidence_snapshot(
    payload: Mapping[str, object],
) -> OperationalEvidenceSnapshot:
    """Strictly validate one serialized operational-evidence snapshot."""
    allowed = {
        "schema_version",
        "snapshot_version",
        "collector_id",
        "collector_version",
        "window_start",
        "window_end",
        "captured_at",
        "evidence_id",
        "records",
    }
    _require_exact_fields(payload, allowed, "operational evidence")
    schema_version = _require_string(payload["schema_version"], "schema_version")
    snapshot_version = _require_identifier(payload["snapshot_version"], "snapshot_version")
    collector_id = _require_identifier(payload["collector_id"], "collector_id")
    collector_version = _require_identifier(payload["collector_version"], "collector_version")
    window_start = _require_utc_datetime(payload["window_start"], "window_start")
    window_end = _require_utc_datetime(payload["window_end"], "window_end")
    captured_at = _require_utc_datetime(payload["captured_at"], "captured_at")
    evidence_id = _require_sha256(payload["evidence_id"], "evidence_id")

    raw_records = payload["records"]
    if not isinstance(raw_records, list) or not raw_records:
        raise OperationalEvidenceError("operational evidence records must be a non-empty list")
    records: list[OperationalEvidenceRecord] = []
    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, Mapping):
            raise OperationalEvidenceError(f"records[{index}] must be a mapping")
        records.append(_build_record(raw_record, index))

    ordered = tuple(sorted(records, key=lambda item: (item.runtime_workload, item.deployment_id)))
    return OperationalEvidenceSnapshot(
        schema_version=schema_version,
        snapshot_version=snapshot_version,
        collector_id=collector_id,
        collector_version=collector_version,
        window_start=window_start,
        window_end=window_end,
        captured_at=captured_at,
        evidence_id=evidence_id,
        records=ordered,
    )


def create_operational_evidence_snapshot(
    *,
    snapshot_version: str,
    collector_id: str,
    collector_version: str,
    window_start: datetime,
    window_end: datetime,
    captured_at: datetime,
    records: tuple[OperationalEvidenceRecord, ...],
) -> OperationalEvidenceSnapshot:
    """Create canonical schema-1.0 evidence with a derived content identity."""
    ordered = tuple(sorted(records, key=lambda item: (item.runtime_workload, item.deployment_id)))
    payload = _snapshot_content_payload(
        schema_version="1.0",
        snapshot_version=snapshot_version,
        collector_id=collector_id,
        collector_version=collector_version,
        window_start=window_start,
        window_end=window_end,
        captured_at=captured_at,
        records=ordered,
    )
    evidence_id = _sha256_payload(payload)
    return OperationalEvidenceSnapshot(
        schema_version="1.0",
        snapshot_version=snapshot_version,
        collector_id=collector_id,
        collector_version=collector_version,
        window_start=window_start,
        window_end=window_end,
        captured_at=captured_at,
        evidence_id=evidence_id,
        records=ordered,
    )


def canonical_operational_evidence_json(snapshot: OperationalEvidenceSnapshot) -> str:
    """Return canonical JSON including the verified content-derived evidence ID."""
    payload = {
        **_snapshot_payload_without_id(snapshot),
        "evidence_id": snapshot.evidence_id,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _build_record(payload: Mapping[object, object], index: int) -> OperationalEvidenceRecord:
    allowed = {
        "runtime_workload",
        "deployment_id",
        "gateway_request_count",
        "provider_attempt_count",
        "successful_provider_attempt_count",
        "provider_error_count",
        "rate_limit_error_count",
        "timeout_count",
        "fallback_request_count",
        "provider_latency_p50_ms",
        "provider_latency_p95_ms",
    }
    location = f"records[{index}]"
    _require_exact_object_fields(payload, allowed, location)
    runtime_workload = _require_identifier(
        payload["runtime_workload"], f"{location}.runtime_workload"
    )
    if "." not in runtime_workload:
        raise OperationalEvidenceError(f"{location}.runtime_workload must be dotted")
    return OperationalEvidenceRecord(
        runtime_workload=runtime_workload,
        deployment_id=_require_identifier(payload["deployment_id"], f"{location}.deployment_id"),
        gateway_request_count=_require_positive_int(
            payload["gateway_request_count"], f"{location}.gateway_request_count"
        ),
        provider_attempt_count=_require_positive_int(
            payload["provider_attempt_count"], f"{location}.provider_attempt_count"
        ),
        successful_provider_attempt_count=_require_nonnegative_int(
            payload["successful_provider_attempt_count"],
            f"{location}.successful_provider_attempt_count",
        ),
        provider_error_count=_require_nonnegative_int(
            payload["provider_error_count"], f"{location}.provider_error_count"
        ),
        rate_limit_error_count=_require_nonnegative_int(
            payload["rate_limit_error_count"], f"{location}.rate_limit_error_count"
        ),
        timeout_count=_require_nonnegative_int(
            payload["timeout_count"], f"{location}.timeout_count"
        ),
        fallback_request_count=_require_nonnegative_int(
            payload["fallback_request_count"], f"{location}.fallback_request_count"
        ),
        provider_latency_p50_ms=_require_nonnegative_int(
            payload["provider_latency_p50_ms"], f"{location}.provider_latency_p50_ms"
        ),
        provider_latency_p95_ms=_require_nonnegative_int(
            payload["provider_latency_p95_ms"], f"{location}.provider_latency_p95_ms"
        ),
    )


def _validate_record(record: OperationalEvidenceRecord) -> None:
    _validate_identifier(record.runtime_workload, "runtime_workload")
    if "." not in record.runtime_workload:
        raise OperationalEvidenceError("runtime_workload must be dotted")
    _validate_identifier(record.deployment_id, "deployment_id")
    integer_fields = {
        "gateway_request_count": record.gateway_request_count,
        "provider_attempt_count": record.provider_attempt_count,
        "successful_provider_attempt_count": record.successful_provider_attempt_count,
        "provider_error_count": record.provider_error_count,
        "rate_limit_error_count": record.rate_limit_error_count,
        "timeout_count": record.timeout_count,
        "fallback_request_count": record.fallback_request_count,
        "provider_latency_p50_ms": record.provider_latency_p50_ms,
        "provider_latency_p95_ms": record.provider_latency_p95_ms,
    }
    for name, value in integer_fields.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise OperationalEvidenceError(f"{name} must be an integer")
    if record.gateway_request_count <= 0:
        raise OperationalEvidenceError("gateway_request_count must be positive")
    if record.provider_attempt_count <= 0:
        raise OperationalEvidenceError("provider_attempt_count must be positive")
    counters = {
        "successful_provider_attempt_count": record.successful_provider_attempt_count,
        "provider_error_count": record.provider_error_count,
        "rate_limit_error_count": record.rate_limit_error_count,
        "timeout_count": record.timeout_count,
        "fallback_request_count": record.fallback_request_count,
        "provider_latency_p50_ms": record.provider_latency_p50_ms,
        "provider_latency_p95_ms": record.provider_latency_p95_ms,
    }
    for name, value in counters.items():
        if value < 0:
            raise OperationalEvidenceError(f"{name} must be non-negative")
    if (
        record.successful_provider_attempt_count + record.provider_error_count
        != record.provider_attempt_count
    ):
        raise OperationalEvidenceError(
            "successful_provider_attempt_count + provider_error_count "
            "must equal provider_attempt_count"
        )
    if record.rate_limit_error_count > record.provider_error_count:
        raise OperationalEvidenceError("rate_limit_error_count cannot exceed provider_error_count")
    if record.timeout_count > record.provider_error_count:
        raise OperationalEvidenceError("timeout_count cannot exceed provider_error_count")
    if record.fallback_request_count > record.gateway_request_count:
        raise OperationalEvidenceError("fallback_request_count cannot exceed gateway_request_count")
    if record.provider_latency_p95_ms < record.provider_latency_p50_ms:
        raise OperationalEvidenceError("provider_latency_p95_ms cannot be less than p50")


def _snapshot_payload_without_id(snapshot: OperationalEvidenceSnapshot) -> dict[str, object]:
    return _snapshot_content_payload(
        schema_version=snapshot.schema_version,
        snapshot_version=snapshot.snapshot_version,
        collector_id=snapshot.collector_id,
        collector_version=snapshot.collector_version,
        window_start=snapshot.window_start,
        window_end=snapshot.window_end,
        captured_at=snapshot.captured_at,
        records=snapshot.records,
    )


def _snapshot_content_payload(
    *,
    schema_version: str,
    snapshot_version: str,
    collector_id: str,
    collector_version: str,
    window_start: datetime,
    window_end: datetime,
    captured_at: datetime,
    records: tuple[OperationalEvidenceRecord, ...],
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "snapshot_version": snapshot_version,
        "collector_id": collector_id,
        "collector_version": collector_version,
        "window_start": _datetime_text(window_start),
        "window_end": _datetime_text(window_end),
        "captured_at": _datetime_text(captured_at),
        "records": [_record_payload(record) for record in records],
    }


def _record_payload(record: OperationalEvidenceRecord) -> dict[str, object]:
    return {
        "runtime_workload": record.runtime_workload,
        "deployment_id": record.deployment_id,
        "gateway_request_count": record.gateway_request_count,
        "provider_attempt_count": record.provider_attempt_count,
        "successful_provider_attempt_count": record.successful_provider_attempt_count,
        "provider_error_count": record.provider_error_count,
        "rate_limit_error_count": record.rate_limit_error_count,
        "timeout_count": record.timeout_count,
        "fallback_request_count": record.fallback_request_count,
        "provider_latency_p50_ms": record.provider_latency_p50_ms,
        "provider_latency_p95_ms": record.provider_latency_p95_ms,
    }


def _require_exact_fields(payload: Mapping[str, object], allowed: set[str], location: str) -> None:
    keys = set(payload)
    unknown = sorted(keys - allowed)
    if unknown:
        raise OperationalEvidenceError(f"unknown {location} fields: {', '.join(unknown)}")
    missing = sorted(allowed - keys)
    if missing:
        raise OperationalEvidenceError(f"missing {location} fields: {', '.join(missing)}")


def _require_exact_object_fields(
    payload: Mapping[object, object], allowed: set[str], location: str
) -> None:
    keys: set[str] = set()
    for key in payload:
        if not isinstance(key, str):
            raise OperationalEvidenceError(f"{location} field names must be strings")
        keys.add(key)
    unknown = sorted(keys - allowed)
    if unknown:
        raise OperationalEvidenceError(f"unknown {location} fields: {', '.join(unknown)}")
    missing = sorted(allowed - keys)
    if missing:
        raise OperationalEvidenceError(f"missing {location} fields: {', '.join(missing)}")


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise OperationalEvidenceError(f"{field} must be a string")
    return value


def _validate_identifier(value: str, field: str) -> None:
    if not value or value.strip() != value or not _IDENTIFIER_RE.fullmatch(value):
        raise OperationalEvidenceError(
            f"{field} must be a normalized lowercase identifier using '.', '_', or '-'"
        )


def _require_identifier(value: object, field: str) -> str:
    text = _require_string(value, field)
    _validate_identifier(text, field)
    return text


def _require_positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise OperationalEvidenceError(f"{field} must be a positive integer")
    return value


def _require_nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OperationalEvidenceError(f"{field} must be a non-negative integer")
    return value


def _validate_utc_datetime(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise OperationalEvidenceError(f"{field} must be an offset-aware UTC timestamp")


def _require_utc_datetime(value: object, field: str) -> datetime:
    text = _require_string(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OperationalEvidenceError(f"{field} must be an ISO-8601 timestamp") from exc
    _validate_utc_datetime(parsed, field)
    return parsed.astimezone(UTC)


def _require_sha256(value: object, field: str) -> str:
    text = _require_string(value, field)
    _validate_sha256(text, field)
    return text


def _validate_sha256(value: str, field: str) -> None:
    prefix = "sha256:"
    digest = value.removeprefix(prefix)
    if not value.startswith(prefix) or len(digest) != 64:
        raise OperationalEvidenceError(f"{field} must be a sha256: content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise OperationalEvidenceError(
            f"{field} must contain a hexadecimal SHA-256 digest"
        ) from exc


def _datetime_text(value: datetime) -> str:
    _validate_utc_datetime(value, "timestamp")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sha256_payload(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
