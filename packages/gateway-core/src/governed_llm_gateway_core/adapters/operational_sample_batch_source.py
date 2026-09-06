"""Batch-backed source for complete source-instance operational sample windows."""

from datetime import datetime, timedelta

from governed_llm_gateway_core.application.operational_evidence import (
    OperationalAttemptSample,
    OperationalEvidenceMaterializationError,
)
from governed_llm_gateway_core.application.operational_sample_batch import OperationalSampleBatch


class OperationalSampleBatchSource:
    """Read complete subwindows from one validated source-instance batch."""

    def __init__(self, batch: OperationalSampleBatch) -> None:
        """Bind one already-validated immutable sample batch."""
        self._batch = batch

    @property
    def source_instance_id(self) -> str:
        """Return the source-instance scope whose completeness the batch can prove."""
        return self._batch.source_instance_id

    @property
    def window_start(self) -> datetime:
        """Return the earliest timestamp covered by the batch."""
        return self._batch.window_start

    @property
    def window_end(self) -> datetime:
        """Return the exclusive upper bound covered by the batch."""
        return self._batch.window_end

    async def read_window(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[OperationalAttemptSample, ...]:
        """Return a complete source-instance subwindow or fail closed outside coverage."""
        _validate_utc(window_start, "window_start")
        _validate_utc(window_end, "window_end")
        if window_start >= window_end:
            raise OperationalEvidenceMaterializationError(
                "window_start must precede window_end"
            )
        if window_start < self._batch.window_start or window_end > self._batch.window_end:
            raise OperationalEvidenceMaterializationError(
                "operational sample batch source cannot prove requested window coverage"
            )
        return tuple(
            sample
            for sample in self._batch.samples
            if window_start <= sample.observed_at < window_end
        )


def _validate_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise OperationalEvidenceMaterializationError(
            f"{field} must be an offset-aware UTC timestamp"
        )
