"""Phase 9 gateway telemetry vocabulary.

This module owns *what* the gateway is allowed to say about itself: stable span names,
stable event names, and the bounded attribute allowlist. That is application policy, so
it stays here and carries no telemetry-library import. Enforcing the allowlist against a
real span is infrastructure and lives in the adapter that implements
``ObservabilityPort``.
"""

from enum import StrEnum


class GatewaySpanName(StrEnum):
    """Stable metadata-only gateway span names used by Phase 9 instrumentation."""

    REQUEST = "llm.gateway.request"
    POLICY_ROUTE = "policy.route"
    PROVIDER_ATTEMPT = "provider.inference"
    STREAM = "llm.gateway.stream"


class GatewaySpanEventName(StrEnum):
    """Stable metadata-only gateway span-event names for resilience transitions."""

    RETRY = "llm.gateway.retry"
    FALLBACK = "llm.gateway.fallback"


GATEWAY_ALLOWED_ATTRIBUTE_KEYS = frozenset(
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
