"""Immutable draft contracts for the Governed LLM Gateway Architecture Gate."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from .enums import DataClassification, ExecutionStatus, MessageRole, RejectionReason, RiskLevel
from .errors import GatewayError


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
class GatewayRequest:
    """Initial provider-neutral request contract.

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

    def __post_init__(self) -> None:
        """Validate schema version and normalized workload identity."""
        if self.schema_version != "1.0":
            raise ValueError("unsupported schema_version")
        if not self.workload or self.workload.strip() != self.workload:
            raise ValueError("workload must be a non-empty normalized identifier")
        segments = self.workload.split(".")
        if len(segments) < 2 or any(not segment.replace("-", "").isalnum() for segment in segments):
            raise ValueError("workload must be a dotted policy-defined identifier")


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Canonical business-tool description; the gateway never executes it."""

    name: str
    description: str
    input_schema: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Canonical model-produced tool call."""

    call_id: str
    name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Canonical tool result supplied by the agent/application runtime."""

    call_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True, slots=True)
class Usage:
    """Normalized token and cost metadata."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_cost_usd: Decimal | None = None


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
    provider: str | None = None
    model: str | None = None
    deployment: str | None = None
    rejected_candidates: tuple[CandidateRejection, ...] = ()
    fallback_sequence: tuple[str, ...] = ()


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
    """Provider-neutral response draft."""

    request_id: UUID
    status: ExecutionStatus
    content: str | None
    routing: RoutingProvenance
    execution: ProviderExecution | None = None
    error: GatewayError | None = None
