"""Content-addressed handoff batches for metadata-only operational attempt samples."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from .operational_evidence import (
    OperationalAttemptSample,
    OperationalEvidenceMaterializationError,
    OperationalProviderErrorKind,
    OperationalSampleOutcome,
    OperationalSampleSource,
    UtcClock,
)

_IDENTIFIER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class OperationalSampleBatchError(ValueError):
    """Raised when an operational sample handoff batch is malformed or tampered with."""


@dataclass(frozen=True, slots=True)
class OperationalSampleBatch:
    """Immutable complete-window handoff for exactly one source instance."""

    schema_version: str
    batch_version: str
    source_instance_id: str
    exporter_id: str
    exporter_version: str
    window_start: datetime
    window_end: datetime
    exported_at: datetime
    batch_id: str
    samples: tuple[OperationalAttemptSample, ...]

    def __post_init__(self) -> None:
        """Require canonical ordering, bounded scope, and content-derived identity."""
        if self.schema_version != "1.0":
            raise OperationalSampleBatchError(
                "operational sample batch schema_version must be '1.0'"
            )
        _validate_identifier(self.batch_version, "batch_version")
        _validate_identifier(self.source_instance_id, "source_instance_id")
        _validate_identifier(self.exporter_id, "exporter_id")
        _validate_identifier(self.exporter_version, "exporter_version")
        _validate_window(self.window_start, self.window_end)
        _validate_utc(self.exported_at, "exported_at")
        if self.exported_at < self.window_end:
            raise OperationalSampleBatchError(
                "operational sample batch exported_at cannot precede window_end"
            )
        if not isinstance(self.samples, tuple) or not self.samples:
            raise OperationalSampleBatchError(
                "operational sample batch samples must be a non-empty tuple"
            )
        ordered = tuple(sorted(self.samples, key=_sample_sort_key))
        if self.samples != ordered:
            raise OperationalSampleBatchError(
                "operational sample batch samples must use canonical ordering"
            )
        _validate_samples_in_window(
            self.samples,
            window_start=self.window_start,
            window_end=self.window_end,
        )
        _reject_duplicate_attempts(self.samples)
        _validate_sha256(self.batch_id, "batch_id")
        expected = _sha256_payload(_batch_payload_without_id(self))
        if self.batch_id != expected:
            raise OperationalSampleBatchError(
                "batch_id does not match canonical operational sample batch content"
            )


class OperationalSampleBatchExporter:
    """Export one complete source-instance window outside provider execution."""

    def __init__(
        self,
        source: OperationalSampleSource,
        *,
        source_instance_id: str,
        exporter_id: str,
        exporter_version: str,
        clock: UtcClock,
    ) -> None:
        """Bind one bounded source and explicit exporter/source-instance provenance."""
        _validate_identifier(source_instance_id, "source_instance_id")
        _validate_identifier(exporter_id, "exporter_id")
        _validate_identifier(exporter_version, "exporter_version")
        self._source = source
        self._source_instance_id = source_instance_id
        self._exporter_id = exporter_id
        self._exporter_version = exporter_version
        self._clock = clock

    async def export(
        self,
        *,
        batch_version: str,
        window_start: datetime,
        window_end: datetime,
    ) -> OperationalSampleBatch:
        """Create a content-addressed handoff from one complete source window."""
        _validate_identifier(batch_version, "batch_version")
        _validate_window(window_start, window_end)
        try:
            samples = await self._source.read_window(
                window_start=window_start,
                window_end=window_end,
            )
        except OperationalEvidenceMaterializationError as exc:
            raise OperationalSampleBatchError(
                "operational sample source could not provide a complete export window"
            ) from exc
        if not samples:
            raise OperationalSampleBatchError(
                "operational sample export window contains no provider-attempt samples"
            )
        exported_at = self._clock()
        _validate_utc(exported_at, "exported_at")
        return create_operational_sample_batch(
            batch_version=batch_version,
            source_instance_id=self._source_instance_id,
            exporter_id=self._exporter_id,
            exporter_version=self._exporter_version,
            window_start=window_start,
            window_end=window_end,
            exported_at=exported_at,
            samples=samples,
        )


def create_operational_sample_batch(
    *,
    batch_version: str,
    source_instance_id: str,
    exporter_id: str,
    exporter_version: str,
    window_start: datetime,
    window_end: datetime,
    exported_at: datetime,
    samples: tuple[OperationalAttemptSample, ...],
) -> OperationalSampleBatch:
    """Create canonical schema-1.0 sample handoff with a derived content identity."""
    ordered = tuple(sorted(samples, key=_sample_sort_key))
    payload = _batch_content_payload(
        schema_version="1.0",
        batch_version=batch_version,
        source_instance_id=source_instance_id,
        exporter_id=exporter_id,
        exporter_version=exporter_version,
        window_start=window_start,
        window_end=window_end,
        exported_at=exported_at,
        samples=ordered,
    )
    batch_id = _sha256_payload(payload)
    return OperationalSampleBatch(
        schema_version="1.0",
        batch_version=batch_version,
        source_instance_id=source_instance_id,
        exporter_id=exporter_id,
        exporter_version=exporter_version,
        window_start=window_start,
        window_end=window_end,
        exported_at=exported_at,
        batch_id=batch_id,
        samples=ordered,
    )


def build_operational_sample_batch(payload: Mapping[str, object]) -> OperationalSampleBatch:
    """Strictly validate one serialized operational sample batch."""
    allowed = {
        "schema_version",
        "batch_version",
        "source_instance_id",
        "exporter_id",
        "exporter_version",
        "window_start",
        "window_end",
        "exported_at",
        "batch_id",
        "samples",
    }
    _require_exact_fields(payload, allowed, "operational sample batch")
    raw_samples = payload["samples"]
    if not isinstance(raw_samples, list) or not raw_samples:
        raise OperationalSampleBatchError(
            "operational sample batch samples must be a non-empty list"
        )
    samples: list[OperationalAttemptSample] = []
    for index, raw_sample in enumerate(raw_samples):
        if not isinstance(raw_sample, Mapping):
            raise OperationalSampleBatchError(f"samples[{index}] must be a mapping")
        samples.append(_build_sample(raw_sample, index))
    return OperationalSampleBatch(
        schema_version=_require_string(payload["schema_version"], "schema_version"),
        batch_version=_require_identifier(payload["batch_version"], "batch_version"),
        source_instance_id=_require_identifier(payload["source_instance_id"], "source_instance_id"),
        exporter_id=_require_identifier(payload["exporter_id"], "exporter_id"),
        exporter_version=_require_identifier(payload["exporter_version"], "exporter_version"),
        window_start=_require_utc_datetime(payload["window_start"], "window_start"),
        window_end=_require_utc_datetime(payload["window_end"], "window_end"),
        exported_at=_require_utc_datetime(payload["exported_at"], "exported_at"),
        batch_id=_require_sha256(payload["batch_id"], "batch_id"),
        samples=tuple(samples),
    )


def canonical_operational_sample_batch_json(batch: OperationalSampleBatch) -> str:
    """Return canonical JSON including the verified content-derived batch ID."""
    payload = {
        **_batch_payload_without_id(batch),
        "batch_id": batch.batch_id,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _build_sample(payload: Mapping[object, object], index: int) -> OperationalAttemptSample:
    allowed = {
        "observed_at",
        "gateway_request_id",
        "runtime_workload",
        "deployment_id",
        "attempt_number",
        "fallback_index",
        "outcome",
        "error_kind",
        "latency_ms",
    }
    location = f"samples[{index}]"
    _require_exact_object_fields(payload, allowed, location)
    outcome_text = _require_string(payload["outcome"], f"{location}.outcome")
    try:
        outcome = OperationalSampleOutcome(outcome_text)
    except ValueError as exc:
        raise OperationalSampleBatchError(
            f"{location}.outcome must be a supported operational sample outcome"
        ) from exc
    raw_error_kind = payload["error_kind"]
    error_kind: OperationalProviderErrorKind | None
    if raw_error_kind is None:
        error_kind = None
    else:
        error_kind_text = _require_string(raw_error_kind, f"{location}.error_kind")
        try:
            error_kind = OperationalProviderErrorKind(error_kind_text)
        except ValueError as exc:
            raise OperationalSampleBatchError(
                f"{location}.error_kind must be a supported provider error kind"
            ) from exc
    request_id_text = _require_string(
        payload["gateway_request_id"], f"{location}.gateway_request_id"
    )
    try:
        request_id = UUID(request_id_text)
    except ValueError as exc:
        raise OperationalSampleBatchError(f"{location}.gateway_request_id must be a UUID") from exc
    try:
        return OperationalAttemptSample(
            observed_at=_require_utc_datetime(payload["observed_at"], f"{location}.observed_at"),
            gateway_request_id=request_id,
            runtime_workload=_require_string(
                payload["runtime_workload"], f"{location}.runtime_workload"
            ),
            deployment_id=_require_string(payload["deployment_id"], f"{location}.deployment_id"),
            attempt_number=_require_int(payload["attempt_number"], f"{location}.attempt_number"),
            fallback_index=_require_int(payload["fallback_index"], f"{location}.fallback_index"),
            outcome=outcome,
            error_kind=error_kind,
            latency_ms=_require_int(payload["latency_ms"], f"{location}.latency_ms"),
        )
    except OperationalEvidenceMaterializationError as exc:
        raise OperationalSampleBatchError(f"{location} is invalid: {exc}") from exc


def _batch_payload_without_id(batch: OperationalSampleBatch) -> dict[str, object]:
    return _batch_content_payload(
        schema_version=batch.schema_version,
        batch_version=batch.batch_version,
        source_instance_id=batch.source_instance_id,
        exporter_id=batch.exporter_id,
        exporter_version=batch.exporter_version,
        window_start=batch.window_start,
        window_end=batch.window_end,
        exported_at=batch.exported_at,
        samples=batch.samples,
    )


def _batch_content_payload(
    *,
    schema_version: str,
    batch_version: str,
    source_instance_id: str,
    exporter_id: str,
    exporter_version: str,
    window_start: datetime,
    window_end: datetime,
    exported_at: datetime,
    samples: tuple[OperationalAttemptSample, ...],
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "batch_version": batch_version,
        "source_instance_id": source_instance_id,
        "exporter_id": exporter_id,
        "exporter_version": exporter_version,
        "window_start": _datetime_text(window_start),
        "window_end": _datetime_text(window_end),
        "exported_at": _datetime_text(exported_at),
        "samples": [_sample_payload(sample) for sample in samples],
    }


def _sample_payload(sample: OperationalAttemptSample) -> dict[str, object]:
    return {
        "observed_at": _datetime_text(sample.observed_at),
        "gateway_request_id": str(sample.gateway_request_id),
        "runtime_workload": sample.runtime_workload,
        "deployment_id": sample.deployment_id,
        "attempt_number": sample.attempt_number,
        "fallback_index": sample.fallback_index,
        "outcome": sample.outcome.value,
        "error_kind": sample.error_kind.value if sample.error_kind is not None else None,
        "latency_ms": sample.latency_ms,
    }


def _sample_sort_key(
    sample: OperationalAttemptSample,
) -> tuple[datetime, str, str, str, int, int]:
    return (
        sample.observed_at,
        str(sample.gateway_request_id),
        sample.runtime_workload,
        sample.deployment_id,
        sample.fallback_index,
        sample.attempt_number,
    )


def _attempt_identity(sample: OperationalAttemptSample) -> tuple[UUID, str, str, int, int]:
    return (
        sample.gateway_request_id,
        sample.runtime_workload,
        sample.deployment_id,
        sample.fallback_index,
        sample.attempt_number,
    )


def _reject_duplicate_attempts(samples: tuple[OperationalAttemptSample, ...]) -> None:
    identities: set[tuple[UUID, str, str, int, int]] = set()
    for sample in samples:
        identity = _attempt_identity(sample)
        if identity in identities:
            raise OperationalSampleBatchError(
                "duplicate operational provider-attempt identity in sample batch"
            )
        identities.add(identity)


def _validate_samples_in_window(
    samples: tuple[OperationalAttemptSample, ...],
    *,
    window_start: datetime,
    window_end: datetime,
) -> None:
    for sample in samples:
        if sample.observed_at < window_start or sample.observed_at >= window_end:
            raise OperationalSampleBatchError(
                "operational sample batch contains data outside declared window"
            )


def _validate_window(window_start: datetime, window_end: datetime) -> None:
    _validate_utc(window_start, "window_start")
    _validate_utc(window_end, "window_end")
    if window_start >= window_end:
        raise OperationalSampleBatchError("window_start must precede window_end")


def _validate_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise OperationalSampleBatchError(f"{field} must be an offset-aware UTC timestamp")


def _datetime_text(value: datetime) -> str:
    _validate_utc(value, "timestamp")
    return value.isoformat().replace("+00:00", "Z")


def _require_utc_datetime(value: object, field: str) -> datetime:
    text = _require_string(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OperationalSampleBatchError(f"{field} must be an ISO-8601 timestamp") from exc
    _validate_utc(parsed, field)
    return parsed


def _require_exact_fields(payload: Mapping[str, object], allowed: set[str], location: str) -> None:
    keys = set(payload)
    unknown = sorted(keys - allowed)
    if unknown:
        raise OperationalSampleBatchError(f"unknown {location} fields: {', '.join(unknown)}")
    missing = sorted(allowed - keys)
    if missing:
        raise OperationalSampleBatchError(f"missing {location} fields: {', '.join(missing)}")


def _require_exact_object_fields(
    payload: Mapping[object, object], allowed: set[str], location: str
) -> None:
    keys: set[str] = set()
    for key in payload:
        if not isinstance(key, str):
            raise OperationalSampleBatchError(f"{location} field names must be strings")
        keys.add(key)
    unknown = sorted(keys - allowed)
    if unknown:
        raise OperationalSampleBatchError(f"unknown {location} fields: {', '.join(unknown)}")
    missing = sorted(allowed - keys)
    if missing:
        raise OperationalSampleBatchError(f"missing {location} fields: {', '.join(missing)}")


def _validate_identifier(value: str, field: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise OperationalSampleBatchError(f"{field} must be a normalized identifier")
    if not _IDENTIFIER_RE.fullmatch(value):
        raise OperationalSampleBatchError(
            f"{field} must use lowercase letters, digits, '.', '_', or '-'"
        )


def _require_identifier(value: object, field: str) -> str:
    text = _require_string(value, field)
    _validate_identifier(text, field)
    return text


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise OperationalSampleBatchError(f"{field} must be a string")
    return value


def _require_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OperationalSampleBatchError(f"{field} must be an integer")
    return value


def _validate_sha256(value: str, field: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise OperationalSampleBatchError(f"{field} must be a sha256 content identifier")


def _require_sha256(value: object, field: str) -> str:
    text = _require_string(value, field)
    _validate_sha256(text, field)
    return text


def _sha256_payload(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
