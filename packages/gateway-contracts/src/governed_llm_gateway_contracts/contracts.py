"""Immutable provider-neutral contracts for the Governed LLM Gateway."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from re import fullmatch
from uuid import UUID

from .enums import (
    DataClassification,
    ExecutionStatus,
    MessageRole,
    RejectionReason,
    RiskLevel,
    StreamEventType,
)
from .errors import GatewayError

_TOOL_NAME_PATTERN = r"[A-Za-z_][A-Za-z0-9_-]{0,127}"
_SCHEMA_NAME_PATTERN = r"[A-Za-z_][A-Za-z0-9_-]{0,63}"


@dataclass(frozen=True, slots=True)
class Message:
    """Provider-neutral message."""

    role: MessageRole
    content: str


@dataclass(frozen=True, slots=True)
class WorkloadRequirements:
    """Capabilities explicitly required by the caller."""

    tool_calling: bool = False
    structured_output: bool = False
    vision: bool = False
    streaming: bool = False
    min_context_tokens: int = 0

    def __post_init__(self) -> None:
        """Validate context-token requirements."""
        if self.min_context_tokens < 0:
            raise ValueError("min_context_tokens must be non-negative")


@dataclass(frozen=True, slots=True)
class RequestLimits:
    """Caller/policy ceilings; effective limits may only become stricter."""

    max_latency_ms: int | None = None
    max_cost_usd: Decimal | None = None

    def __post_init__(self) -> None:
        """Validate request ceilings."""
        if self.max_latency_ms is not None and self.max_latency_ms <= 0:
            raise ValueError("max_latency_ms must be positive")
        if self.max_cost_usd is not None and self.max_cost_usd < 0:
            raise ValueError("max_cost_usd must be non-negative")


@dataclass(frozen=True, slots=True)
class StructuredOutputSchema:
    """Canonical JSON Schema requested for a provider-native structured response."""

    name: str
    schema: Mapping[str, object]

    def __post_init__(self) -> None:
        """Validate only provider-neutral shape; JSON Schema semantics are checked in core."""
        if fullmatch(_SCHEMA_NAME_PATTERN, self.name) is None:
            raise ValueError("structured output schema name is invalid")
        if not self.schema:
            raise ValueError("structured output schema must not be empty")


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Canonical business-tool description; the gateway never executes it."""

    name: str
    description: str
    input_schema: Mapping[str, object]

    def __post_init__(self) -> None:
        """Validate provider-neutral tool identity and root input shape."""
        if fullmatch(_TOOL_NAME_PATTERN, self.name) is None:
            raise ValueError("tool name is invalid")
        if not self.description.strip() or self.description.strip() != self.description:
            raise ValueError("tool description must be a normalized non-empty string")
        if self.input_schema.get("type") != "object":
            raise ValueError("tool input_schema root type must be object")


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Canonical model-produced tool call."""

    call_id: str
    name: str
    arguments: Mapping[str, object]

    def __post_init__(self) -> None:
        """Validate canonical tool-call identity before schema validation."""
        if not self.call_id.strip() or self.call_id.strip() != self.call_id:
            raise ValueError("tool call_id must be a normalized non-empty string")
        if fullmatch(_TOOL_NAME_PATTERN, self.name) is None:
            raise ValueError("tool call name is invalid")


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Canonical tool result supplied by the agent/application runtime."""

    call_id: str
    content: str
    is_error: bool = False

    def __post_init__(self) -> None:
        """Validate correlation identity; business result content remains opaque to the gateway."""
        if not self.call_id.strip() or self.call_id.strip() != self.call_id:
            raise ValueError("tool result call_id must be a normalized non-empty string")


@dataclass(frozen=True, slots=True)
class GatewayRequest:
    """Provider-neutral request contract.

    risk_level and data_classification are caller-declared context, not trusted authorization
    facts. The enforcement layer must derive or validate effective values from authenticated
    workload identity and policy before model selection.
    """

    schema_version: str
    request_id: UUID
    workload: str
    risk_level: RiskLevel
    data_classification: DataClassification
    requirements: WorkloadRequirements = field(default_factory=WorkloadRequirements)
    limits: RequestLimits = field(default_factory=RequestLimits)
    messages: tuple[Message, ...] = ()
    agent_identity: str | None = None
    tools: tuple[ToolDefinition, ...] = ()
    structured_output: StructuredOutputSchema | None = None

    def __post_init__(self) -> None:
        """Validate schema version, workload identity, and optional execution contracts."""
        if self.schema_version != "1.0":
            raise ValueError("unsupported schema_version")
        if not self.workload or self.workload.strip() != self.workload:
            raise ValueError("workload must be a non-empty normalized identifier")
        segments = self.workload.split(".")
        if len(segments) < 2 or any(not segment.replace("-", "").isalnum() for segment in segments):
            raise ValueError("workload must be a dotted policy-defined identifier")
        tool_names = tuple(tool.name for tool in self.tools)
        if len(set(tool_names)) != len(tool_names):
            raise ValueError("tool definitions must have unique names")
        if self.tools and not self.requirements.tool_calling:
            raise ValueError("tool definitions require tool_calling capability")
        if self.structured_output is not None and not self.requirements.structured_output:
            raise ValueError("structured output schema requires structured_output capability")


@dataclass(frozen=True, slots=True)
class Usage:
    """Normalized token and cost metadata."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd: Decimal | None = None

    def __post_init__(self) -> None:
        """Reject impossible usage values rather than silently normalizing them."""
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("usage token counts must be non-negative")
        if self.total_cost_usd is not None and self.total_cost_usd < 0:
            raise ValueError("usage total_cost_usd must be non-negative")


@dataclass(frozen=True, slots=True)
class PolicyProvenance:
    """Evidence returned by the Policy Decision Point."""

    decision_id: str
    policy_id: str
    policy_version: str
    policy_digest: str


@dataclass(frozen=True, slots=True)
class CandidateRejection:
    """Explainable candidate rejection."""

    deployment: str
    reason: RejectionReason
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class RoutingProvenance:
    """Metadata sufficient to reconstruct the routing decision without prompt storage."""

    routing_decision_id: str
    policy: PolicyProvenance
    authorized_model_group: str
    model_registry_digest: str
    ranking_policy_version: str
    ranking_policy_digest: str | None = None
    score_snapshot_id: str | None = None
    benchmark_snapshot_id: str | None = None
    score_provenance_mode: str | None = None
    manual_override_id: str | None = None
    provider: str | None = None
    model: str | None = None
    deployment: str | None = None
    rejected_candidates: tuple[CandidateRejection, ...] = ()
    fallback_sequence: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GatewayStreamEvent:
    """One normalized SSE event emitted by the gateway streaming boundary."""

    event_type: StreamEventType
    request_id: UUID
    sequence_number: int
    routing: RoutingProvenance | None = None
    delta: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_call: ToolCall | None = None
    usage: Usage | None = None
    finish_reason: str | None = None
    error: GatewayError | None = None
    partial: bool = False

    def __post_init__(self) -> None:
        """Enforce event-specific payload invariants and deterministic sequence numbering."""
        if self.sequence_number <= 0:
            raise ValueError("stream sequence_number must be positive")
        if self.event_type is StreamEventType.RESPONSE_STARTED:
            self._require(routing=True)
        elif self.event_type is StreamEventType.CONTENT_DELTA:
            if self.delta is None or not self.delta:
                raise ValueError("content.delta requires a non-empty delta")
            self._require()
        elif self.event_type is StreamEventType.TOOL_CALL_STARTED:
            if self.tool_call_id is None or not self.tool_call_id.strip():
                raise ValueError("tool_call.started requires tool_call_id")
            if self.tool_name is None or fullmatch(_TOOL_NAME_PATTERN, self.tool_name) is None:
                raise ValueError("tool_call.started requires a valid tool_name")
            self._require()
        elif self.event_type is StreamEventType.TOOL_CALL_ARGUMENTS_DELTA:
            if self.tool_call_id is None or not self.tool_call_id.strip():
                raise ValueError("tool_call.arguments.delta requires tool_call_id")
            if self.delta is None or not self.delta:
                raise ValueError("tool_call.arguments.delta requires a non-empty delta")
            self._require()
        elif self.event_type is StreamEventType.TOOL_CALL_COMPLETED:
            if self.tool_call is None:
                raise ValueError("tool_call.completed requires tool_call")
            self._require()
        elif self.event_type is StreamEventType.USAGE_COMPLETED:
            if self.usage is None:
                raise ValueError("usage.completed requires usage")
            self._require()
        elif self.event_type is StreamEventType.RESPONSE_COMPLETED:
            self._require(routing=True)
        elif self.event_type is StreamEventType.RESPONSE_FAILED:
            if self.error is None:
                raise ValueError("response.failed requires error")
            self._require(routing=True)

    def _require(self, *, routing: bool = False) -> None:
        if routing and self.routing is None:
            raise ValueError(f"{self.event_type.value} requires routing provenance")
        if (
            self.finish_reason is not None
            and self.event_type is not StreamEventType.RESPONSE_COMPLETED
        ):
            raise ValueError("finish_reason is only valid on response.completed")
        if self.partial and self.event_type is not StreamEventType.RESPONSE_FAILED:
            raise ValueError("partial is only valid on response.failed")
        if self.error is not None and self.event_type is not StreamEventType.RESPONSE_FAILED:
            raise ValueError("error is only valid on response.failed")


@dataclass(frozen=True, slots=True)
class ProviderExecution:
    """Normalized execution metadata without provider-specific response objects."""

    provider: str
    model: str
    deployment: str
    status: ExecutionStatus
    latency_ms: int
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True, slots=True)
class GatewayResponse:
    """Provider-neutral response contract."""

    request_id: UUID
    status: ExecutionStatus
    content: str | None
    routing: RoutingProvenance
    execution: ProviderExecution | None = None
    error: GatewayError | None = None
    structured_output: object | None = None
    tool_calls: tuple[ToolCall, ...] = ()
