"""OpenTelemetry binding for the application's observability port.

Every telemetry-library import the gateway makes outside its composition roots is
concentrated here. Attribute sanitization stays with the library that owns it: the
gateway contributes its own allowlist as data, and ``sanitize_attributes`` merges that
with the kit's defaults so the two vocabularies cannot drift apart.
"""

from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass

from a2a_otel_kit import Observability, sanitize_attributes
from opentelemetry.trace import Span
from opentelemetry.trace.status import Status, StatusCode

from governed_llm_gateway_core.application.observability import GatewaySpan
from governed_llm_gateway_core.application.telemetry import GATEWAY_ALLOWED_ATTRIBUTE_KEYS

# The sanitizer yields scalars only; OpenTelemetry rejects None, so callers drop those.
type _Scalar = str | int | float | bool


@dataclass(frozen=True, slots=True)
class OpenTelemetryGatewaySpan:
    """One OpenTelemetry span presented through the application's bounded span contract."""

    span: Span

    def set_attributes(self, attributes: Mapping[str, object]) -> None:
        """Set only allowlisted scalar gateway metadata on the underlying span."""
        for key, value in self._clean(attributes).items():
            if value is not None:
                self.span.set_attribute(key, value)

    def add_event(self, name: str, attributes: Mapping[str, object] | None = None) -> None:
        """Add one bounded metadata-only event to the underlying span."""
        clean = self._clean(attributes)
        self.span.add_event(
            name, attributes={key: value for key, value in clean.items() if value is not None}
        )

    def mark_success(self) -> None:
        """Mark the span successful without attaching response content."""
        self.span.set_attribute("outcome", "success")
        self.span.set_status(Status(StatusCode.OK))

    def mark_failure(self, error_type: str) -> None:
        """Mark the span failed using only a stable sanitized error category."""
        self.set_attributes({"outcome": "failure", "error.type": error_type})
        self.span.set_status(Status(StatusCode.ERROR))

    def mark_cancelled(self) -> None:
        """Record caller cancellation as lifecycle state, not provider failure."""
        self.span.set_attribute("outcome", "cancelled")

    @property
    def trace_id(self) -> str | None:
        """Return the span's trace ID, or None when its context is not valid."""
        span_context = self.span.get_span_context()
        if not span_context.is_valid:
            return None
        return format(span_context.trace_id, "032x")

    @staticmethod
    def _clean(attributes: Mapping[str, object] | None) -> dict[str, _Scalar | None]:
        return sanitize_attributes(
            attributes,
            extra_allowed_keys=GATEWAY_ALLOWED_ATTRIBUTE_KEYS,
        )


@dataclass(frozen=True, slots=True)
class OpenTelemetryObservability:
    """Adapt a configured ``Observability`` instance to the application's port."""

    observability: Observability

    def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, object] | None = None,
        record_exception: bool = False,
    ) -> AbstractContextManager[GatewaySpan]:
        """Open one span and present it through the bounded gateway span contract."""
        return self._span(name, attributes=attributes, record_exception=record_exception)

    @contextmanager
    def _span(
        self,
        name: str,
        *,
        attributes: Mapping[str, object] | None,
        record_exception: bool,
    ) -> Iterator[GatewaySpan]:
        with self.observability.start_span(
            name,
            attributes=attributes,
            record_exception=record_exception,
        ) as span:
            yield OpenTelemetryGatewaySpan(span)
