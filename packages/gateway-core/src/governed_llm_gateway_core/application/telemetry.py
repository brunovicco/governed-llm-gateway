"""Phase 9 gateway telemetry semantics built on the a2a-otel-kit privacy boundary."""

from collections.abc import Mapping

from a2a_otel_kit import sanitize_attributes
from opentelemetry.trace import Span
from opentelemetry.trace.status import Status, StatusCode

_GATEWAY_ALLOWED_ATTRIBUTE_KEYS = frozenset(
    {
        "llm.workload",
        "llm.provider",
        "llm.model",
        "llm.deployment",
        "llm.usage.input_count",
        "llm.usage.output_count",
        "llm.latency_ms",
        "llm.ttft_ms",
        "llm.fallback_count",
        "llm.attempt_number",
        "llm.retry_delay_ms",
        "llm.partial",
        "llm.streaming",
        "routing.decision_id",
        "routing.policy_id",
        "routing.policy_version",
        "routing.policy_digest",
        "routing.model_group",
        "registry.digest",
        "ranking.policy_version",
        "ranking.policy_digest",
        "ranking.score_snapshot_id",
    }
)


def set_gateway_span_attributes(span: Span, attributes: Mapping[str, object]) -> None:
    """Set only bounded allowlisted gateway metadata on one OpenTelemetry span."""
    clean = sanitize_attributes(
        attributes,
        extra_allowed_keys=_GATEWAY_ALLOWED_ATTRIBUTE_KEYS,
    )
    for key, value in clean.items():
        if value is not None:
            span.set_attribute(key, value)


def add_gateway_span_event(
    span: Span,
    name: str,
    attributes: Mapping[str, object] | None = None,
) -> None:
    """Add one bounded metadata-only gateway event to a span."""
    clean = sanitize_attributes(
        attributes,
        extra_allowed_keys=_GATEWAY_ALLOWED_ATTRIBUTE_KEYS,
    )
    span.add_event(
        name, attributes={key: value for key, value in clean.items() if value is not None}
    )


def mark_span_success(span: Span) -> None:
    """Mark a span successful without attaching response content."""
    span.set_attribute("outcome", "success")
    span.set_status(Status(StatusCode.OK))


def mark_span_failure(span: Span, error_type: str) -> None:
    """Mark a span failed using only a stable sanitized error category."""
    set_gateway_span_attributes(
        span,
        {
            "outcome": "failure",
            "error.type": error_type,
        },
    )
    span.set_status(Status(StatusCode.ERROR))


def mark_span_cancelled(span: Span) -> None:
    """Record caller cancellation as lifecycle state, not provider failure."""
    span.set_attribute("outcome", "cancelled")
