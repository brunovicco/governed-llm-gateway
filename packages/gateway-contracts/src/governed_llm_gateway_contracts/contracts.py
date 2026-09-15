"""Immutable provider-neutral contracts for the Governed LLM Gateway."""

import base64
import binascii
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from re import fullmatch
from urllib.parse import urlsplit
from uuid import UUID

from .enums import (
    AudioMediaType,
    ClientProtocol,
    DataClassification,
    DocumentMediaType,
    ExecutionStatus,
    ImageMediaType,
    MessageRole,
    RejectionReason,
    RiskLevel,
    StreamEventType,
)
from .errors import GatewayError

_TOOL_NAME_PATTERN = r"[A-Za-z_][A-Za-z0-9_-]{0,127}"
_SCHEMA_NAME_PATTERN = r"[A-Za-z_][A-Za-z0-9_-]{0,63}"
_TRACE_ID_PATTERN = r"[0-9a-f]{32}"
_MAX_IMAGE_URL_LENGTH = 2048
_MAX_IMAGES_PER_MESSAGE = 8
_MAX_IMAGES_PER_REQUEST = 16
_MAX_INLINE_MEDIA_BYTES = 4 * 1024 * 1024
_MAX_INLINE_MEDIA_ENCODED_LENGTH = 6 * 1024 * 1024


def _validate_https_url(url: str, *, label: str) -> None:
    if not url or url.strip() != url:
        raise ValueError(f"{label} URL must be a normalized non-empty string")
    if len(url) > _MAX_IMAGE_URL_LENGTH:
        raise ValueError(f"{label} URL exceeds the maximum supported length")
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"{label} URL is invalid") from exc
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(f"{label} URL must be an absolute HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{label} URL must not contain userinfo")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{label} URL must not contain query or fragment")


@dataclass(frozen=True, slots=True)
class ImageInput:
    """Provider-neutral HTTPS image reference forwarded without gateway fetching."""

    media_type: ImageMediaType
    url: str

    def __post_init__(self) -> None:
        """Reject ambiguous or credential-bearing image references before provider I/O."""
        if not isinstance(self.media_type, ImageMediaType):
            raise ValueError("image media_type must use the provider-neutral vocabulary")
        _validate_https_url(self.url, label="image")


@dataclass(frozen=True, slots=True)
class HttpsUrlSource:
    """An HTTPS media reference which adapters forward but the gateway never fetches."""

    url: str

    def __post_init__(self) -> None:
        """Reject unsafe or ambiguous remote references."""
        _validate_https_url(self.url, label="media")


@dataclass(frozen=True, slots=True)
class Base64Source:
    """Bounded canonical base64 bytes validated before provider selection or I/O."""

    data: str

    def __post_init__(self) -> None:
        """Decode only for validation and enforce both encoded and decoded ceilings."""
        if not self.data or self.data.strip() != self.data:
            raise ValueError("base64 media data must be a normalized non-empty string")
        if len(self.data) > _MAX_INLINE_MEDIA_ENCODED_LENGTH:
            raise ValueError("base64 media data exceeds the encoded-size limit")
        try:
            decoded = base64.b64decode(self.data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("base64 media data is invalid") from exc
        if len(decoded) > _MAX_INLINE_MEDIA_BYTES:
            raise ValueError("base64 media data exceeds the decoded-size limit")


MediaSource = HttpsUrlSource | Base64Source


@dataclass(frozen=True, slots=True)
class TextBlock:
    """Canonical text content block."""

    text: str

    def __post_init__(self) -> None:
        """Reject empty deltas at the canonical boundary."""
        if not self.text:
            raise ValueError("text block must not be empty")


@dataclass(frozen=True, slots=True)
class ImageBlock:
    """Canonical image block using an unfetched HTTPS URL or bounded inline bytes.

    URL-oriented client protocols do not always declare a media type. Keeping that value
    unknown is safer than inventing one; inline bytes always require an explicit type.
    """

    media_type: ImageMediaType | None
    source: MediaSource

    def __post_init__(self) -> None:
        """Require a controlled media type and source-compatible metadata."""
        if self.media_type is not None and not isinstance(self.media_type, ImageMediaType):
            raise ValueError("image block media_type is invalid")
        if not isinstance(self.source, HttpsUrlSource | Base64Source):
            raise ValueError("image block source is invalid")
        if isinstance(self.source, Base64Source) and self.media_type is None:
            raise ValueError("inline image blocks require a media_type")


@dataclass(frozen=True, slots=True)
class AudioBlock:
    """Canonical audio block; remote audio fetching is intentionally unsupported."""

    media_type: AudioMediaType
    source: Base64Source

    def __post_init__(self) -> None:
        """Require bounded inline bytes and a controlled audio media type."""
        if not isinstance(self.media_type, AudioMediaType):
            raise ValueError("audio block media_type is invalid")
        if not isinstance(self.source, Base64Source):
            raise ValueError("audio blocks require bounded base64 data")


@dataclass(frozen=True, slots=True)
class DocumentBlock:
    """Canonical document block; remote document fetching is intentionally unsupported."""

    media_type: DocumentMediaType
    source: Base64Source
    filename: str | None = None

    def __post_init__(self) -> None:
        """Require bounded inline bytes and a safe optional basename."""
        if not isinstance(self.media_type, DocumentMediaType):
            raise ValueError("document block media_type is invalid")
        if not isinstance(self.source, Base64Source):
            raise ValueError("document blocks require bounded base64 data")
        if self.filename is not None and (
            not self.filename.strip()
            or self.filename.strip() != self.filename
            or "/" in self.filename
            or "\\" in self.filename
        ):
            raise ValueError("document filename must be a normalized basename")


@dataclass(frozen=True, slots=True)
class ToolUseBlock:
    """Canonical assistant tool-use block retained for tool-result continuation."""

    call: "ToolCall"

    def __post_init__(self) -> None:
        """Reject structurally invalid transcript blocks at construction time."""
        if not isinstance(self.call, ToolCall):
            raise ValueError("tool-use block call is invalid")


@dataclass(frozen=True, slots=True)
class ToolResultBlock:
    """Canonical application-supplied tool-result block; the gateway never executes it."""

    result: "ToolResult"

    def __post_init__(self) -> None:
        """Reject structurally invalid transcript blocks at construction time."""
        if not isinstance(self.result, ToolResult):
            raise ValueError("tool-result block result is invalid")


ContentBlock = TextBlock | ImageBlock | AudioBlock | DocumentBlock | ToolUseBlock | ToolResultBlock


@dataclass(frozen=True, slots=True)
class Message:
    """Provider-neutral message supporting legacy text/images and canonical content blocks."""

    role: MessageRole
    content: str
    images: tuple[ImageInput, ...] = ()
    blocks: tuple[ContentBlock, ...] = ()

    def __post_init__(self) -> None:
        """Reject ambiguous mixed representations and invalid role/block combinations."""
        if self.blocks and (self.content or self.images):
            raise ValueError("message must use legacy content/images or canonical blocks, not both")
        if len(self.images) > _MAX_IMAGES_PER_MESSAGE:
            raise ValueError("message exceeds the maximum image count")
        if any(not isinstance(image, ImageInput) for image in self.images):
            raise ValueError("message images must use the provider-neutral ImageInput contract")
        if self.images and self.role is not MessageRole.USER:
            raise ValueError("image input is supported only on user messages")
        if any(
            not isinstance(
                block,
                TextBlock
                | ImageBlock
                | AudioBlock
                | DocumentBlock
                | ToolUseBlock
                | ToolResultBlock,
            )
            for block in self.blocks
        ):
            raise ValueError("message blocks must use the canonical content-block contracts")
        if (
            any(isinstance(block, ImageBlock | AudioBlock | DocumentBlock) for block in self.blocks)
            and self.role is not MessageRole.USER
        ):
            raise ValueError("media input blocks are supported only on user messages")
        if any(isinstance(block, ToolUseBlock) for block in self.blocks) and (
            self.role is not MessageRole.ASSISTANT
        ):
            raise ValueError("tool-use blocks require the assistant role")
        if any(isinstance(block, ToolResultBlock) for block in self.blocks) and self.role not in {
            MessageRole.USER,
            MessageRole.TOOL,
        }:
            raise ValueError("tool-result blocks require the user or tool role")

    @property
    def canonical_blocks(self) -> tuple[ContentBlock, ...]:
        """Return one unambiguous canonical block sequence for legacy and new callers."""
        if self.blocks:
            return self.blocks
        blocks: list[ContentBlock] = [
            ImageBlock(media_type=image.media_type, source=HttpsUrlSource(image.url))
            for image in self.images
        ]
        if self.content:
            blocks.append(TextBlock(self.content))
        return tuple(blocks)

    @property
    def text_content(self) -> str:
        """Join canonical text blocks for API families with a separate system field."""
        return "\n".join(
            block.text for block in self.canonical_blocks if isinstance(block, TextBlock)
        )


@dataclass(frozen=True, slots=True)
class WorkloadRequirements:
    """Capabilities explicitly required by the caller."""

    tool_calling: bool = False
    structured_output: bool = False
    vision: bool = False
    streaming: bool = False
    audio: bool = False
    document: bool = False
    parallel_tool_calling: bool = False
    min_context_tokens: int = 0

    def __post_init__(self) -> None:
        """Validate context-token requirements."""
        if self.min_context_tokens < 0:
            raise ValueError("min_context_tokens must be non-negative")
        if self.parallel_tool_calling and not self.tool_calling:
            raise ValueError("parallel_tool_calling requires tool_calling capability")


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
    strict: bool = True

    def __post_init__(self) -> None:
        """Validate provider-neutral tool identity and root input shape."""
        if fullmatch(_TOOL_NAME_PATTERN, self.name) is None:
            raise ValueError("tool name is invalid")
        if not self.description.strip() or self.description.strip() != self.description:
            raise ValueError("tool description must be a normalized non-empty string")
        if self.input_schema.get("type") != "object":
            raise ValueError("tool input_schema root type must be object")
        if not isinstance(self.strict, bool):
            raise ValueError("tool strict flag must be boolean")


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
    client_protocol: ClientProtocol = ClientProtocol.NATIVE

    def __post_init__(self) -> None:
        """Validate schema version, workload identity, and optional execution contracts."""
        if self.schema_version != "1.0":
            raise ValueError("unsupported schema_version")
        if not isinstance(self.client_protocol, ClientProtocol):
            raise ValueError("client_protocol must use the controlled vocabulary")
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
        blocks = tuple(block for message in self.messages for block in message.canonical_blocks)
        image_count = sum(isinstance(block, ImageBlock) for block in blocks)
        if image_count > _MAX_IMAGES_PER_REQUEST:
            raise ValueError("request exceeds the maximum image count")
        if image_count and not self.requirements.vision:
            raise ValueError("image input requires vision capability")
        if any(isinstance(block, AudioBlock) for block in blocks) and not self.requirements.audio:
            raise ValueError("audio input requires audio capability")
        if (
            any(isinstance(block, DocumentBlock) for block in blocks)
            and not self.requirements.document
        ):
            raise ValueError("document input requires document capability")
        tool_uses = tuple(block.call for block in blocks if isinstance(block, ToolUseBlock))
        tool_results = tuple(block.result for block in blocks if isinstance(block, ToolResultBlock))
        if (tool_uses or tool_results) and not self.requirements.tool_calling:
            raise ValueError("tool transcript blocks require tool_calling capability")
        use_ids: set[str] = set()
        result_ids: set[str] = set()
        for message in self.messages:
            message_uses = tuple(
                block.call for block in message.canonical_blocks if isinstance(block, ToolUseBlock)
            )
            if len(message_uses) > 1 and not self.requirements.parallel_tool_calling:
                raise ValueError("multiple tool calls require parallel_tool_calling capability")
            for block in message.canonical_blocks:
                if isinstance(block, ToolUseBlock):
                    if block.call.call_id in use_ids:
                        raise ValueError("tool-use call identifiers must be unique")
                    use_ids.add(block.call.call_id)
                elif isinstance(block, ToolResultBlock):
                    if block.result.call_id not in use_ids:
                        raise ValueError(
                            "each tool result must correlate to a prior tool-use block"
                        )
                    if block.result.call_id in result_ids:
                        raise ValueError("tool-result call identifiers must be unique")
                    result_ids.add(block.result.call_id)


@dataclass(frozen=True, slots=True)
class Usage:
    """Normalized token and cost metadata with optional provider-returned detail."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None
    total_cost_usd: Decimal | None = None

    def __post_init__(self) -> None:
        """Reject impossible usage values rather than silently normalizing them."""
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("usage token counts must be non-negative")
        if self.total_tokens is not None:
            if self.total_tokens < 0:
                raise ValueError("usage total_tokens must be non-negative")
            if self.total_tokens != self.input_tokens + self.output_tokens:
                raise ValueError("usage total_tokens must equal input_tokens plus output_tokens")
        for name, value in (
            ("cache_read_input_tokens", self.cache_read_input_tokens),
            ("cache_write_input_tokens", self.cache_write_input_tokens),
        ):
            if value is not None and value < 0:
                raise ValueError(f"usage {name} must be non-negative")
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
class ProviderExecution:
    """Normalized terminal execution evidence without provider-specific response objects."""

    provider: str
    model: str
    deployment: str
    status: ExecutionStatus
    latency_ms: int
    usage: Usage | None = None
    provider_request_id: str | None = None
    finish_reason: str | None = None
    attempt_number: int = 1
    fallback_index: int = 0
    api_family: str | None = None
    max_output_tokens: int | None = None
    trace_id: str | None = None
    # A served cache hit reports the deployment that originally produced the content,
    # so this flag is what keeps that from reading as a fresh provider call. Usage is
    # likewise the original call's, and any spend accounting must exclude a cached
    # execution rather than count those tokens twice.
    cached: bool = False

    def __post_init__(self) -> None:
        """Validate concrete provider identity and measured execution metadata."""
        if any(not value.strip() for value in (self.provider, self.model, self.deployment)):
            raise ValueError("provider execution identity must be non-empty")
        if self.latency_ms < 0:
            raise ValueError("provider execution latency_ms must be non-negative")
        for name, value in (
            ("provider_request_id", self.provider_request_id),
            ("finish_reason", self.finish_reason),
            ("api_family", self.api_family),
        ):
            if value is not None and (not value.strip() or value.strip() != value):
                raise ValueError(f"provider execution {name} must be normalized when present")
        if self.attempt_number <= 0:
            raise ValueError("provider execution attempt_number must be positive")
        if self.fallback_index < 0:
            raise ValueError("provider execution fallback_index must be non-negative")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise ValueError("provider execution max_output_tokens must be positive when present")
        if self.trace_id is not None and fullmatch(_TRACE_ID_PATTERN, self.trace_id) is None:
            raise ValueError(
                "provider execution trace_id must be a 32-character lowercase hex string"
                " when present"
            )


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
    execution: ProviderExecution | None = None
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
            self._validate_execution(ExecutionStatus.SUCCEEDED, required=False)
        elif self.event_type is StreamEventType.RESPONSE_FAILED:
            if self.error is None:
                raise ValueError("response.failed requires error")
            self._require(routing=True)
            self._validate_execution(ExecutionStatus.FAILED, required=False)

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
        if self.execution is not None and self.event_type not in {
            StreamEventType.RESPONSE_COMPLETED,
            StreamEventType.RESPONSE_FAILED,
        }:
            raise ValueError("execution is only valid on terminal response events")

    def _validate_execution(self, status: ExecutionStatus, *, required: bool) -> None:
        execution = self.execution
        if execution is None:
            if required:
                raise ValueError(f"{self.event_type.value} requires provider execution evidence")
            return
        if not isinstance(execution, ProviderExecution):
            raise ValueError("execution must use the provider-neutral ProviderExecution contract")
        if execution.status is not status:
            raise ValueError("terminal execution status does not match response event status")
        routing = self.routing
        if routing is None:
            raise ValueError("terminal execution evidence requires routing provenance")
        if (execution.provider, execution.model, execution.deployment) != (
            routing.provider,
            routing.model,
            routing.deployment,
        ):
            raise ValueError("terminal execution evidence does not match routing provenance")


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
