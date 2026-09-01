"""Controlled vocabularies owned by the provider-neutral contract package."""

from enum import StrEnum


class DataClassification(StrEnum):
    """Controlled data-classification vocabulary."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class RiskLevel(StrEnum):
    """Controlled workload risk vocabulary."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MessageRole(StrEnum):
    """Canonical message roles for the initial request contract."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ExecutionStatus(StrEnum):
    """Provider-neutral terminal execution status."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"


class StreamEventType(StrEnum):
    """Stable provider-neutral SSE lifecycle emitted by the gateway."""

    RESPONSE_STARTED = "response.started"
    CONTENT_DELTA = "content.delta"
    TOOL_CALL_STARTED = "tool_call.started"
    TOOL_CALL_ARGUMENTS_DELTA = "tool_call.arguments.delta"
    TOOL_CALL_COMPLETED = "tool_call.completed"
    USAGE_COMPLETED = "usage.completed"
    RESPONSE_COMPLETED = "response.completed"
    RESPONSE_FAILED = "response.failed"


class RejectionReason(StrEnum):
    """Machine-readable reasons for candidate rejection."""

    WRONG_MODEL_GROUP = "wrong_model_group"
    DEPLOYMENT_DISABLED = "deployment_disabled"
    MISSING_CAPABILITY = "missing_capability"
    CONTEXT_TOO_SMALL = "context_too_small"
    PROVIDER_NOT_AUTHORIZED = "provider_not_authorized"
    PRICING_UNAVAILABLE = "pricing_unavailable"
    RANKING_SCORE_UNAVAILABLE = "ranking_score_unavailable"
    DEPLOYMENT_UNHEALTHY = "deployment_unhealthy"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    COST_LIMIT_EXCEEDED = "cost_limit_exceeded"
    LATENCY_LIMIT_EXCEEDED = "latency_limit_exceeded"


class Capability(StrEnum):
    """Provider-neutral capabilities that registry entries may advertise."""

    TEXT = "text"
    VISION = "vision"
    TOOL_CALLING = "tool_calling"
    STRUCTURED_OUTPUT = "structured_output"
    STREAMING = "streaming"


class Modality(StrEnum):
    """Provider-neutral input modalities relevant to model eligibility."""

    TEXT = "text"
    IMAGE = "image"
