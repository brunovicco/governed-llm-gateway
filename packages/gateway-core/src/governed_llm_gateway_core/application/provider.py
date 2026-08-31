"""Provider-neutral execution boundary for Phase 3."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from governed_llm_gateway_contracts import Message, MessageRole


class ProviderErrorCode(StrEnum):
    """Stable provider failure categories used by orchestration and later retry policy."""

    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    INVALID_REQUEST = "invalid_request"
    UNAVAILABLE = "unavailable"
    TRANSPORT = "transport"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    """Provider-normalized token usage for one inference call."""

    input_tokens: int = 0
    output_tokens: int = 0

    def __post_init__(self) -> None:
        """Reject impossible token counts instead of normalizing bad provider data silently."""
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("provider token usage must be non-negative")


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """Concrete-model request passed only after upstream authorization/selection."""

    model: str
    messages: tuple[Message, ...]
    max_output_tokens: int = 1024
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        """Validate the bounded Phase 3 text-only execution request."""
        if not self.model or self.model.strip() != self.model:
            raise ValueError("provider model must be a non-empty normalized string")
        if not self.messages:
            raise ValueError("provider request must contain at least one message")
        if any(message.role is MessageRole.TOOL for message in self.messages):
            raise ValueError("tool-result messages are not supported in Phase 3")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Provider-neutral successful text-generation response."""

    text: str
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    response_id: str | None = None
    finish_reason: str | None = None

    def __post_init__(self) -> None:
        """Require actual text for the Phase 3 text-generation contract."""
        if not self.text.strip():
            raise ValueError("provider response text must not be empty")


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
        """Generate one text response from an already-selected concrete model."""
        ...
