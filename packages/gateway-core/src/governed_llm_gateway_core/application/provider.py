"""Provider-neutral execution boundary for model inference."""

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from governed_llm_gateway_contracts import (
    Message,
    MessageRole,
    StructuredOutputSchema,
    ToolCall,
    ToolDefinition,
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


@dataclass(frozen=True, slots=True)
class ProviderFeatureSupport:
    """API-family features the adapter can translate natively.

    Deployment/model capability remains registry data. These flags describe only the adapter wire
    contract and never grant routing authorization.
    """

    native_structured_output: bool = False
    native_tool_calling: bool = False
    native_image_input: bool = False
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

    def __post_init__(self) -> None:
        """Validate bounded provider-neutral execution input."""
        if not self.model or self.model.strip() != self.model:
            raise ValueError("provider model must be a non-empty normalized string")
        if not self.messages:
            raise ValueError("provider request must contain at least one message")
        if any(message.role is MessageRole.TOOL for message in self.messages):
            raise ValueError(
                "tool-result message continuation is not representable "
                "without prior tool-call state"
            )
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.structured_output is not None:
            validate_structured_output_schema(self.structured_output)
        if self.tools:
            validate_tool_definitions(self.tools)

    @property
    def has_image_input(self) -> bool:
        """Return whether the request contains provider-neutral image input."""
        return any(message.images for message in self.messages)


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

    def stream(self, request: ProviderRequest) -> AsyncGenerator[ProviderStreamEvent]:
        """Yield normalized provider events and close upstream resources on cancellation."""
        ...
