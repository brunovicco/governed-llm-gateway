"""Provider-neutral observability port for the gateway application layer.

The application decides *what* is worth recording and which metadata vocabulary is
allowed to leave the process. It must not decide *how* a span reaches a backend, which
is why nothing here imports OpenTelemetry or any specific telemetry kit — the concrete
binding lives in ``governed_llm_gateway_core.adapters.observability_otel``.

Telemetry stays descriptive throughout: a span records what happened and never becomes
an authorization input for a later request.
"""

from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable


@runtime_checkable
class GatewaySpan(Protocol):
    """One in-flight unit of gateway work that accepts bounded metadata only."""

    def set_attributes(self, attributes: Mapping[str, object]) -> None:
        """Record allowlisted metadata; anything outside the vocabulary is dropped."""
        ...

    def add_event(self, name: str, attributes: Mapping[str, object] | None = None) -> None:
        """Record one bounded metadata-only lifecycle event."""
        ...

    def mark_success(self) -> None:
        """Mark the unit of work successful without attaching response content."""
        ...

    def mark_failure(self, error_type: str) -> None:
        """Mark the unit of work failed using only a stable sanitized error category."""
        ...

    def mark_cancelled(self) -> None:
        """Record caller cancellation as lifecycle state, not as provider failure."""
        ...

    @property
    def trace_id(self) -> str | None:
        """Return the 32-character lowercase-hex trace ID, or None when unavailable.

        A disabled or non-recording span has no valid identity, so callers get None
        rather than a synthesized one — descriptive evidence must never be fabricated.
        """
        ...


class ObservabilityPort(Protocol):
    """Boundary the application uses to open spans without binding to a backend."""

    def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, object] | None = None,
        record_exception: bool = False,
    ) -> AbstractContextManager[GatewaySpan]:
        """Open one span for the duration of a ``with`` block.

        ``record_exception`` defaults to False here, unlike the underlying telemetry
        library: gateway boundaries routinely wrap failures whose messages may carry
        provider content this repository must never record verbatim. Callers set a
        safe status explicitly instead.
        """
        ...
