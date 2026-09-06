"""Materialize reviewed operational evidence from bounded metadata-only samples."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from governed_llm_gateway_core.domain.operational_evidence import (
    OperationalEvidenceRecord,
    OperationalEvidenceSnapshot,
    create_operational_evidence_snapshot,
)

_IDENTIFIER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
UtcClock = Callable[[], datetime]


class OperationalEvidenceMaterializationError(ValueError):
    """Raised when a recent operational window cannot be materialized safely."""


class OperationalSampleOutcome(StrEnum):
    """Bounded outcomes for one actual provider attempt."""

    SUCCEEDED = "succeeded"
    PROVIDER_ERROR = "provider_error"


class OperationalProviderErrorKind(StrEnum):
    """Provider-error categories required by operational evidence schema 1.0."""

    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class OperationalAttemptSample:
    """Timestamped metadata-only evidence for one actual provider attempt."""

    observed_at: datetime
    gateway_request_id: UUID
    runtime_workload: str
    deployment_id: str
    attempt_number: int
    fallback_index: int
    outcome: OperationalSampleOutcome
    error_kind: OperationalProviderErrorKind | None
    latency_ms: int

    def __post_init__(self) -> None:
        """Reject ambiguous identities, timestamps, counters, and outcome drift."""
        _validate_utc(self.observed_at, "observed_at")
        if not isinstance(self.gateway_request_id, UUID):
            raise OperationalEvidenceMaterializationError("gateway_request_id must be a UUID")
        _validate_identifier(self.runtime_workload, "runtime_workload")
        if "." not in self.runtime_workload:
            raise OperationalEvidenceMaterializationError("runtime_workload must be dotted")
        _validate_identifier(self.deployment_id, "deployment_id")
        _validate_positive_int(self.attempt_number, "attempt_number")
        _validate_nonnegative_int(self.fallback_index, "fallback_index")
        _validate_nonnegative_int(self.latency_ms, "latency_ms")
        if not isinstance(self.outcome, OperationalSampleOutcome):
            raise OperationalEvidenceMaterializationError(
                "outcome must be an OperationalSampleOutcome"
            )
        if self.outcome is OperationalSampleOutcome.SUCCEEDED:
            if self.error_kind is not None:
                raise OperationalEvidenceMaterializationError(
                    "successful operational sample cannot carry error_kind"
                )
        elif not isinstance(self.error_kind, OperationalProviderErrorKind):
            raise OperationalEvidenceMaterializationError(
                "provider-error operational sample must carry error_kind"
            )


class OperationalSampleSource(Protocol):
    """Read a complete half-open window of operational attempt samples."""

    async def read_window(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[OperationalAttemptSample, ...]:
        """Return complete samples in `[window_start, window_end)`."""
        ...


class OperationalEvidenceMaterializer:
    """Aggregate complete attempt samples into immutable schema-1.0 evidence."""

    def __init__(
        self,
        source: OperationalSampleSource,
        *,
        collector_id: str,
        collector_version: str,
        clock: UtcClock,
    ) -> None:
        """Bind a sample source and explicit collector provenance."""
        _validate_identifier(collector_id, "collector_id")
        _validate_identifier(collector_version, "collector_version")
        self._source = source
        self._collector_id = collector_id
        self._collector_version = collector_version
        self._clock = clock

    async def materialize(
        self,
        *,
        snapshot_version: str,
        window_start: datetime,
        window_end: datetime,
    ) -> OperationalEvidenceSnapshot:
        """Create one deterministic evidence snapshot for a complete recent window."""
        _validate_identifier(snapshot_version, "snapshot_version")
        _validate_window(window_start, window_end)
        samples = await self._source.read_window(
            window_start=window_start,
            window_end=window_end,
        )
        if not samples:
            raise OperationalEvidenceMaterializationError(
                "operational evidence window contains no provider-attempt samples"
            )
        ordered = tuple(sorted(samples, key=_sample_sort_key))
        _validate_source_window(ordered, window_start=window_start, window_end=window_end)
        _reject_duplicate_attempts(ordered)
        records = _aggregate_records(ordered)
        captured_at = self._clock()
        _validate_utc(captured_at, "captured_at")
        if captured_at < window_end:
            raise OperationalEvidenceMaterializationError(
                "captured_at cannot precede operational evidence window_end"
            )
        return create_operational_evidence_snapshot(
            snapshot_version=snapshot_version,
            collector_id=self._collector_id,
            collector_version=self._collector_version,
            window_start=window_start,
            window_end=window_end,
            captured_at=captured_at,
            records=records,
        )


def _aggregate_records(
    samples: tuple[OperationalAttemptSample, ...],
) -> tuple[OperationalEvidenceRecord, ...]:
    grouped: dict[tuple[str, str], list[OperationalAttemptSample]] = defaultdict(list)
    for sample in samples:
        grouped[(sample.runtime_workload, sample.deployment_id)].append(sample)

    records: list[OperationalEvidenceRecord] = []
    for runtime_key in sorted(grouped):
        group = grouped[runtime_key]
        request_ids = {sample.gateway_request_id for sample in group}
        fallback_request_ids = {
            sample.gateway_request_id for sample in group if sample.fallback_index > 0
        }
        successes = sum(sample.outcome is OperationalSampleOutcome.SUCCEEDED for sample in group)
        provider_errors = len(group) - successes
        rate_limits = sum(
            sample.error_kind is OperationalProviderErrorKind.RATE_LIMIT for sample in group
        )
        timeouts = sum(
            sample.error_kind is OperationalProviderErrorKind.TIMEOUT for sample in group
        )
        latencies = sorted(sample.latency_ms for sample in group)
        records.append(
            OperationalEvidenceRecord(
                runtime_workload=runtime_key[0],
                deployment_id=runtime_key[1],
                gateway_request_count=len(request_ids),
                provider_attempt_count=len(group),
                successful_provider_attempt_count=successes,
                provider_error_count=provider_errors,
                rate_limit_error_count=rate_limits,
                timeout_count=timeouts,
                fallback_request_count=len(fallback_request_ids),
                provider_latency_p50_ms=_nearest_rank(latencies, 50),
                provider_latency_p95_ms=_nearest_rank(latencies, 95),
            )
        )
    return tuple(records)


def _nearest_rank(values: list[int], percentile: int) -> int:
    if not values:
        raise OperationalEvidenceMaterializationError(
            "cannot compute operational percentile from an empty sample set"
        )
    rank = math.ceil((percentile / 100) * len(values))
    return values[rank - 1]


def _reject_duplicate_attempts(samples: tuple[OperationalAttemptSample, ...]) -> None:
    identities: set[tuple[UUID, str, str, int, int]] = set()
    for sample in samples:
        identity = (
            sample.gateway_request_id,
            sample.runtime_workload,
            sample.deployment_id,
            sample.fallback_index,
            sample.attempt_number,
        )
        if identity in identities:
            raise OperationalEvidenceMaterializationError(
                "duplicate operational provider-attempt identity"
            )
        identities.add(identity)


def _validate_source_window(
    samples: tuple[OperationalAttemptSample, ...],
    *,
    window_start: datetime,
    window_end: datetime,
) -> None:
    for sample in samples:
        if sample.observed_at < window_start or sample.observed_at >= window_end:
            raise OperationalEvidenceMaterializationError(
                "operational sample source returned data outside requested window"
            )


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


def _validate_window(window_start: datetime, window_end: datetime) -> None:
    _validate_utc(window_start, "window_start")
    _validate_utc(window_end, "window_end")
    if window_start >= window_end:
        raise OperationalEvidenceMaterializationError("window_start must precede window_end")


def _validate_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise OperationalEvidenceMaterializationError(
            f"{field} must be an offset-aware UTC timestamp"
        )


def _validate_identifier(value: str, field: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise OperationalEvidenceMaterializationError(f"{field} must be a normalized identifier")
    if not _IDENTIFIER_RE.fullmatch(value):
        raise OperationalEvidenceMaterializationError(
            f"{field} must use lowercase letters, digits, '.', '_', or '-'"
        )


def _validate_positive_int(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise OperationalEvidenceMaterializationError(f"{field} must be a positive integer")


def _validate_nonnegative_int(value: int, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise OperationalEvidenceMaterializationError(f"{field} must be a non-negative integer")
