"""Bounded process-local source for metadata-only operational attempt samples."""

from collections.abc import Callable
from datetime import datetime, timedelta

from governed_llm_gateway_core.application.operational_evidence import (
    OperationalAttemptSample,
    OperationalEvidenceMaterializationError,
)

UtcClock = Callable[[], datetime]


class InMemoryOperationalSampleStore:
    """Keep bounded chronological samples without claiming distributed completeness."""

    def __init__(self, *, max_samples: int, clock: UtcClock) -> None:
        """Start process-local coverage at construction time."""
        if (
            isinstance(max_samples, bool)
            or not isinstance(max_samples, int)
            or max_samples <= 0
        ):
            raise OperationalEvidenceMaterializationError("max_samples must be a positive integer")
        coverage_start = clock()
        _validate_utc(coverage_start, "coverage_start")
        self._max_samples = max_samples
        self._clock = clock
        self._coverage_start = coverage_start
        self._samples: list[OperationalAttemptSample] = []
        self._latest_observed_at: datetime | None = None
        self._evicted_through: datetime | None = None

    @property
    def coverage_start(self) -> datetime:
        """Return the earliest timestamp from which this process observed all recorded samples."""
        return self._coverage_start

    @property
    def evicted_through(self) -> datetime | None:
        """Return the latest timestamp whose history may have been truncated by capacity."""
        return self._evicted_through

    def record(self, sample: OperationalAttemptSample) -> None:
        """Append one chronological actual-attempt sample within current source coverage."""
        now = self._clock()
        _validate_utc(now, "source clock")
        if sample.observed_at < self._coverage_start:
            raise OperationalEvidenceMaterializationError(
                "operational sample predates process-local source coverage"
            )
        if sample.observed_at > now:
            raise OperationalEvidenceMaterializationError(
                "operational sample cannot be recorded from the future"
            )
        if (
            self._latest_observed_at is not None
            and sample.observed_at < self._latest_observed_at
        ):
            raise OperationalEvidenceMaterializationError(
                "operational samples must be recorded in non-decreasing timestamp order"
            )
        self._samples.append(sample)
        self._latest_observed_at = sample.observed_at
        while len(self._samples) > self._max_samples:
            evicted = self._samples.pop(0)
            if self._evicted_through is None or evicted.observed_at > self._evicted_through:
                self._evicted_through = evicted.observed_at

    async def read_window(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[OperationalAttemptSample, ...]:
        """Return a complete half-open window or fail closed on uncertain coverage."""
        _validate_utc(window_start, "window_start")
        _validate_utc(window_end, "window_end")
        if window_start >= window_end:
            raise OperationalEvidenceMaterializationError(
                "window_start must precede window_end"
            )
        now = self._clock()
        _validate_utc(now, "source clock")
        if window_end > now:
            raise OperationalEvidenceMaterializationError(
                "operational sample window_end cannot be in the future"
            )
        if window_start < self._coverage_start:
            raise OperationalEvidenceMaterializationError(
                "operational sample window starts before process-local source coverage"
            )
        if self._evicted_through is not None and window_start <= self._evicted_through:
            raise OperationalEvidenceMaterializationError(
                "operational sample window may intersect capacity-evicted history"
            )
        return tuple(
            sample
            for sample in self._samples
            if window_start <= sample.observed_at < window_end
        )


def _validate_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise OperationalEvidenceMaterializationError(
            f"{field} must be an offset-aware UTC timestamp"
        )
