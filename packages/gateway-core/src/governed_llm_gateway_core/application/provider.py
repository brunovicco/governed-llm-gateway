"""Provider-neutral execution boundary for model inference."""

from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from governed_llm_gateway_contracts import (
    AudioBlock,
    DocumentBlock,
    ImageBlock,
    Message,
    StructuredOutputSchema,
    ToolCall,
    ToolDefinition,
    ToolResultBlock,
)

from governed_llm_gateway_core.domain.structured import (
    validate_structured_output_schema,
    validate_tool_definitions,
)


class ProviderErrorCode(StrEnum):
    """Stable provider failure categories used by orchestration and retry policy."""

    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    INVALID_REQUEST = "invalid_request"
    UNAVAILABLE = "unavailable"
    TRANSPORT = "transport"
    INVALID_RESPONSE = "invalid_response"
    INVALID_STRUCTURED_OUTPUT = "invalid_structured_output"
    INVALID_TOOL_CALL = "invalid_tool_call"
    UNKNOWN = "unknown"


def is_transient_provider_error(error: "ProviderError") -> bool:
    """Return whether a provider failure may be retried on the same deployment.

    One definition, used by retry, fallback and every health tracker. A second copy that
    drifted by one condition would silently change when a circuit opens.
    """
    return error.retryable and error.code in {
        ProviderErrorCode.RATE_LIMIT,
        ProviderErrorCode.TIMEOUT,
        ProviderErrorCode.UNAVAILABLE,
        ProviderErrorCode.TRANSPORT,
    }


@dataclass(frozen=True, slots=True)
class ProviderFeatureSupport:
    """API-family features the adapter can translate natively.

    Deployment/model capability remains registry data. These flags describe only the adapter wire
    contract and never grant routing authorization.
    """

    native_structured_output: bool = False
    native_tool_calling: bool = False
    native_image_input: bool = False
    native_inline_image_input: bool = False
    native_audio_input: bool = False
    native_document_input: bool = False
    native_tool_result_input: bool = False
    native_streaming: bool = False
    streaming_usage: bool = False


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    """Provider-normalized token usage preserving optional provider-returned detail."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None
    total_cost_usd: Decimal | None = None

    def __post_init__(self) -> None:
        """Reject impossible token counts instead of normalizing bad provider data silently."""
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("provider token usage must be non-negative")
        if self.total_tokens is not None:
            if self.total_tokens < 0:
                raise ValueError("provider total_tokens must be non-negative")
            if self.total_tokens != self.input_tokens + self.output_tokens:
                raise ValueError("provider total_tokens must equal input_tokens plus output_tokens")
        for name, value in (
            ("cache_read_input_tokens", self.cache_read_input_tokens),
            ("cache_write_input_tokens", self.cache_write_input_tokens),
        ):
            if value is not None and value < 0:
                raise ValueError(f"provider {name} must be non-negative")
        if self.total_cost_usd is not None and self.total_cost_usd < 0:
            raise ValueError("provider total_cost_usd must be non-negative")


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """Concrete-model request passed only after upstream authorization/selection."""

    model: str
    messages: tuple[Message, ...]
    max_output_tokens: int = 1024
    timeout_seconds: float = 30.0
    structured_output: StructuredOutputSchema | None = None
    tools: tuple[ToolDefinition, ...] = ()
    parallel_tool_calling: bool = False

    def __post_init__(self) -> None:
        """Validate bounded provider-neutral execution input."""
        if not self.model or self.model.strip() != self.model:
            raise ValueError("provider model must be a non-empty normalized string")
        if not self.messages:
            raise ValueError("provider request must contain at least one message")
        if any(
            message.role.value == "tool"
            and not any(isinstance(block, ToolResultBlock) for block in message.blocks)
            for message in self.messages
        ):
            raise ValueError(
                "tool-result message continuation requires a canonical correlated tool-result block"
            )
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.structured_output is not None:
            validate_structured_output_schema(self.structured_output)
        if self.tools:
            validate_tool_definitions(self.tools)
        if self.parallel_tool_calling and not self.tools:
            raise ValueError("parallel tool calling requires tool definitions")

    @property
    def has_image_input(self) -> bool:
        """Return whether the request contains provider-neutral image input."""
        return any(
            isinstance(block, ImageBlock)
            for message in self.messages
            for block in message.canonical_blocks
        )

    @property
    def has_inline_image_input(self) -> bool:
        """Return whether any image uses bounded inline bytes rather than an HTTPS reference."""
        from governed_llm_gateway_contracts import Base64Source

        return any(
            isinstance(block, ImageBlock) and isinstance(block.source, Base64Source)
            for message in self.messages
            for block in message.canonical_blocks
        )

    @property
    def has_audio_input(self) -> bool:
        """Return whether the request contains canonical audio input."""
        return any(
            isinstance(block, AudioBlock)
            for message in self.messages
            for block in message.canonical_blocks
        )

    @property
    def has_document_input(self) -> bool:
        """Return whether the request contains canonical document input."""
        return any(
            isinstance(block, DocumentBlock)
            for message in self.messages
            for block in message.canonical_blocks
        )

    @property
    def has_tool_results(self) -> bool:
        """Return whether replay could duplicate a tool-side effect already performed externally."""
        return any(
            isinstance(block, ToolResultBlock)
            for message in self.messages
            for block in message.canonical_blocks
        )


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Provider-neutral successful inference response."""

    text: str | None = None
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    response_id: str | None = None
    finish_reason: str | None = None
    structured_output: object | None = None
    tool_calls: tuple[ToolCall, ...] = ()

    def __post_init__(self) -> None:
        """Require at least one usable normalized output channel."""
        if self.text is not None and not self.text.strip():
            raise ValueError("provider response text must not be blank")
        if self.text is None and self.structured_output is None and not self.tool_calls:
            raise ValueError(
                "provider response must contain text, structured output, or tool calls"
            )


@dataclass(frozen=True, slots=True)
class ProviderResponseStarted:
    """Provider stream opened successfully; no semantic model output is implied."""

    response_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderContentDelta:
    """Incremental text emitted by the selected provider."""

    delta: str

    def __post_init__(self) -> None:
        """Reject empty deltas rather than create ambiguous stream events."""
        if not self.delta:
            raise ValueError("provider content delta must not be empty")


@dataclass(frozen=True, slots=True)
class ProviderToolCallStarted:
    """Provider began one client-side business-tool call."""

    call_id: str
    name: str

    def __post_init__(self) -> None:
        """Require normalized tool-call identity before emitting semantic output."""
        if not self.call_id.strip() or not self.name.strip():
            raise ValueError("provider tool-call start requires normalized identity")


@dataclass(frozen=True, slots=True)
class ProviderToolCallArgumentsDelta:
    """Incremental JSON text for one provider tool-call argument object."""

    call_id: str
    delta: str

    def __post_init__(self) -> None:
        """Require call correlation and a non-empty argument delta."""
        if not self.call_id.strip() or not self.delta:
            raise ValueError("provider tool-call argument delta is invalid")


@dataclass(frozen=True, slots=True)
class ProviderToolCallCompleted:
    """Fully parsed and locally validated provider tool call."""

    call: ToolCall


@dataclass(frozen=True, slots=True)
class ProviderUsageCompleted:
    """Final token usage for the successful stream."""

    usage: ProviderUsage


@dataclass(frozen=True, slots=True)
class ProviderResponseCompleted:
    """Provider stream reached a normal terminal state."""

    response_id: str | None = None
    finish_reason: str | None = None


ProviderStreamEvent = (
    ProviderResponseStarted
    | ProviderContentDelta
    | ProviderToolCallStarted
    | ProviderToolCallArgumentsDelta
    | ProviderToolCallCompleted
    | ProviderUsageCompleted
    | ProviderResponseCompleted
)


ProviderStreamFactory = Callable[[], AsyncGenerator[ProviderStreamEvent]]


@dataclass(frozen=True, slots=True)
class PreparedProviderStream:
    """Opaque, reusable provider stream state built without provider I/O."""

    request: ProviderRequest
    _factory: ProviderStreamFactory = field(repr=False, compare=False)

    def stream(self) -> AsyncGenerator[ProviderStreamEvent]:
        """Open one runtime attempt from the already-validated provider state."""
        return self._factory()


class ProviderError(RuntimeError):
    """Safe typed provider failure without raw response bodies or secrets."""

    def __init__(
        self,
        *,
        provider: str,
        code: ProviderErrorCode,
        message: str,
        retryable: bool,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        """Create a sanitized error carrying only bounded operational metadata."""
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


class ProviderPort(Protocol):
    """Execution port implemented by one provider API-family adapter."""

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate one response from an already-selected concrete model."""
        ...


@runtime_checkable
class ProviderStreamingPort(Protocol):
    """Optional streaming port implemented only by explicitly supported API families."""

    feature_support: ProviderFeatureSupport

    def prepare_stream(self, request: ProviderRequest) -> PreparedProviderStream:
        """Build immutable provider-specific state without performing provider I/O."""
        ...

    def stream(self, request: ProviderRequest) -> AsyncGenerator[ProviderStreamEvent]:
        """Compatibility entry point that prepares, then opens, one provider stream."""
        ...
