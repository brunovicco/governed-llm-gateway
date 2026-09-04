"""Thin async client for the governed gateway HTTP/SSE boundary."""

import json
import os
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from types import TracebackType
from typing import cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from governed_llm_gateway_contracts import (
    DataClassification,
    ExecutionStatus,
    GatewayRequest,
    GatewayResponse,
    GatewayStreamEvent,
    Message,
    MessageRole,
    RequestLimits,
    RiskLevel,
    StreamEventType,
    StructuredOutputSchema,
    ToolCall,
    ToolDefinition,
    WorkloadRequirements,
)

from ._codec import _iter_sse_events
from .errors import (
    GatewayClientError,
    GatewayConfigurationError,
    GatewayHTTPError,
    GatewayProtocolError,
    GatewayRequestError,
    GatewayTransportError,
)

_GATEWAY_URL_ENV = "GOVERNED_LLM_GATEWAY_URL"
_GATEWAY_API_KEY_ENV = "GOVERNED_LLM_GATEWAY_API_KEY"
_DEFAULT_MAX_SSE_EVENT_BYTES = 1024 * 1024
_DEFAULT_MAX_SSE_STREAM_BYTES = 16 * 1024 * 1024
_MAX_CONFIGURED_SSE_STREAM_BYTES = 128 * 1024 * 1024
_MAX_ERROR_BODY_BYTES = 64 * 1024
_IDENTITY_CONTENT_ENCODINGS = frozenset({"", "identity"})


@dataclass(frozen=True, slots=True)
class GatewayClientConfig:
    """Validated connection settings for the thin gateway client."""

    base_url: str
    api_key: str = field(repr=False)
    request_timeout_seconds: float = 60.0
    max_sse_event_bytes: int = _DEFAULT_MAX_SSE_EVENT_BYTES
    max_sse_stream_bytes: int = _DEFAULT_MAX_SSE_STREAM_BYTES

    def __post_init__(self) -> None:
        """Fail closed on unsafe URLs, empty credentials, or invalid transport limits."""
        object.__setattr__(self, "base_url", _validated_base_url(self.base_url))
        if not self.api_key or not self.api_key.strip() or self.api_key.strip() != self.api_key:
            raise GatewayConfigurationError("gateway API key must be a normalized non-empty value")
        if self.request_timeout_seconds <= 0 or self.request_timeout_seconds > 300:
            raise GatewayConfigurationError("request timeout must be in the range (0, 300]")
        if (
            not isinstance(self.max_sse_event_bytes, int)
            or isinstance(self.max_sse_event_bytes, bool)
            or self.max_sse_event_bytes <= 0
        ):
            raise GatewayConfigurationError("max SSE event size must be a positive integer")
        if (
            not isinstance(self.max_sse_stream_bytes, int)
            or isinstance(self.max_sse_stream_bytes, bool)
            or self.max_sse_stream_bytes <= 0
        ):
            raise GatewayConfigurationError("max SSE stream size must be a positive integer")
        if self.max_sse_stream_bytes < self.max_sse_event_bytes:
            raise GatewayConfigurationError(
                "max SSE stream size must cover one maximum-size event"
            )
        if self.max_sse_stream_bytes > _MAX_CONFIGURED_SSE_STREAM_BYTES:
            raise GatewayConfigurationError("max SSE stream size exceeds the client safety ceiling")


class GatewayClient:
    """Provider-neutral async SDK that delegates governance and resilience to the gateway."""

    def __init__(
        self,
        config: GatewayClientConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create one reusable HTTP client without provider credentials or automatic redirects."""
        self._config = config
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(config.request_timeout_seconds),
            transport=transport,
            follow_redirects=False,
            trust_env=False,
        )

    @classmethod
    def from_env(
        cls,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> "GatewayClient":
        """Build a client from the canonical gateway URL and credential environment variables."""
        base_url = os.environ.get(_GATEWAY_URL_ENV)
        api_key = os.environ.get(_GATEWAY_API_KEY_ENV)
        if base_url is None or not base_url.strip():
            raise GatewayConfigurationError(f"{_GATEWAY_URL_ENV} is required")
        if api_key is None or not api_key.strip():
            raise GatewayConfigurationError(f"{_GATEWAY_API_KEY_ENV} is required")
        return cls(GatewayClientConfig(base_url=base_url, api_key=api_key), transport=transport)

    @property
    def base_url(self) -> str:
        """Return the normalized gateway URL without exposing credentials."""
        return self._config.base_url

    def __repr__(self) -> str:
        """Return a credential-free client representation."""
        return f"GatewayClient(base_url={self.base_url!r})"

    async def __aenter__(self) -> "GatewayClient":
        """Return this client for async context-manager use."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the underlying HTTP connection pool."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool explicitly."""
        await self._http.aclose()

    async def stream(
        self,
        *,
        workload: str,
        messages: Sequence[Message],
        risk_level: RiskLevel,
        data_classification: DataClassification,
        requirements: WorkloadRequirements | None = None,
        limits: RequestLimits | None = None,
        agent_identity: str | None = None,
        tools: Sequence[ToolDefinition] = (),
        structured_output: StructuredOutputSchema | None = None,
        context_tokens_estimated: int = 0,
        max_output_tokens: int = 1024,
        provider_timeout_seconds: float = 30.0,
        request_id: UUID | None = None,
    ) -> AsyncIterator[GatewayStreamEvent]:
        """Yield normalized events from one governed generation request with no client retry."""
        payload = _build_generate_payload(
            workload=workload,
            messages=messages,
            risk_level=risk_level,
            data_classification=data_classification,
            requirements=requirements,
            limits=limits,
            agent_identity=agent_identity,
            tools=tools,
            structured_output=structured_output,
            context_tokens_estimated=context_tokens_estimated,
            max_output_tokens=max_output_tokens,
            provider_timeout_seconds=provider_timeout_seconds,
            request_id=request_id,
        )
        expected_request_id = UUID(cast(str, payload["request_id"]))
        try:
            async with self._http.stream(
                "POST",
                f"{self.base_url}/v1/generate",
                headers={
                    "X-Gateway-API-Key": self._config.api_key,
                    "Accept": "text/event-stream",
                    "Accept-Encoding": "identity",
                },
                json=payload,
            ) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    raise await _http_error(response)
                _validate_identity_response(response)
                _validate_success_content_length(
                    response,
                    max_stream_bytes=self._config.max_sse_stream_bytes,
                )
                content_type = response.headers.get("content-type", "")
                media_type = content_type.split(";", 1)[0].strip().lower()
                if media_type != "text/event-stream":
                    raise GatewayProtocolError(
                        "gateway response content-type is not text/event-stream"
                    )
                async for event in _iter_sse_events(
                    response,
                    max_event_bytes=self._config.max_sse_event_bytes,
                    max_stream_bytes=self._config.max_sse_stream_bytes,
                    expected_request_id=expected_request_id,
                ):
                    yield event
        except GatewayClientError:
            raise
        except httpx.HTTPError:
            raise GatewayTransportError("gateway transport request failed") from None

    async def generate(
        self,
        *,
        workload: str,
        messages: Sequence[Message],
        risk_level: RiskLevel,
        data_classification: DataClassification,
        requirements: WorkloadRequirements | None = None,
        limits: RequestLimits | None = None,
        agent_identity: str | None = None,
        tools: Sequence[ToolDefinition] = (),
        structured_output: StructuredOutputSchema | None = None,
        context_tokens_estimated: int = 0,
        max_output_tokens: int = 1024,
        provider_timeout_seconds: float = 30.0,
        request_id: UUID | None = None,
    ) -> GatewayResponse:
        """Aggregate one normalized SSE stream into a provider-neutral terminal response."""
        content_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        terminal: GatewayStreamEvent | None = None
        async for event in self.stream(
            workload=workload,
            messages=messages,
            risk_level=risk_level,
            data_classification=data_classification,
            requirements=requirements,
            limits=limits,
            agent_identity=agent_identity,
            tools=tools,
            structured_output=structured_output,
            context_tokens_estimated=context_tokens_estimated,
            max_output_tokens=max_output_tokens,
            provider_timeout_seconds=provider_timeout_seconds,
            request_id=request_id,
        ):
            if event.event_type is StreamEventType.CONTENT_DELTA and event.delta is not None:
                content_parts.append(event.delta)
            elif event.event_type is StreamEventType.TOOL_CALL_COMPLETED:
                if event.tool_call is None:
                    raise GatewayProtocolError("completed tool-call event is missing tool_call")
                tool_calls.append(event.tool_call)
            if event.event_type in {
                StreamEventType.RESPONSE_COMPLETED,
                StreamEventType.RESPONSE_FAILED,
            }:
                terminal = event

        if terminal is None or terminal.routing is None:
            raise GatewayProtocolError(
                "gateway stream completed without terminal routing provenance"
            )
        content = "".join(content_parts) or None
        if terminal.event_type is StreamEventType.RESPONSE_COMPLETED:
            return GatewayResponse(
                request_id=terminal.request_id,
                status=ExecutionStatus.SUCCEEDED,
                content=content,
                routing=terminal.routing,
                execution=None,
                error=None,
                structured_output=None,
                tool_calls=tuple(tool_calls),
            )
        if terminal.error is None:
            raise GatewayProtocolError("failed terminal event is missing normalized gateway error")
        return GatewayResponse(
            request_id=terminal.request_id,
            status=ExecutionStatus.FAILED,
            content=content,
            routing=terminal.routing,
            execution=None,
            error=terminal.error,
            structured_output=None,
            tool_calls=tuple(tool_calls),
        )


def _validated_base_url(value: str) -> str:
    if not value or value.strip() != value:
        raise GatewayConfigurationError("gateway base URL must be normalized and non-empty")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise GatewayConfigurationError("gateway base URL is invalid") from exc
    if parsed.scheme != "https" or not parsed.hostname:
        raise GatewayConfigurationError("gateway base URL must be an absolute HTTPS URL")
    if parsed.username is not None or parsed.password is not None:
        raise GatewayConfigurationError("gateway base URL must not contain userinfo")
    if parsed.query or parsed.fragment:
        raise GatewayConfigurationError("gateway base URL must not contain query or fragment")
    normalized = value.rstrip("/")
    if not normalized:
        raise GatewayConfigurationError("gateway base URL is invalid")
    return normalized


def _build_generate_payload(
    *,
    workload: str,
    messages: Sequence[Message],
    risk_level: RiskLevel,
    data_classification: DataClassification,
    requirements: WorkloadRequirements | None,
    limits: RequestLimits | None,
    agent_identity: str | None,
    tools: Sequence[ToolDefinition],
    structured_output: StructuredOutputSchema | None,
    context_tokens_estimated: int,
    max_output_tokens: int,
    provider_timeout_seconds: float,
    request_id: UUID | None,
) -> dict[str, object]:
    if not isinstance(risk_level, RiskLevel):
        raise GatewayRequestError("risk_level must use the provider-neutral RiskLevel contract")
    if not isinstance(data_classification, DataClassification):
        raise GatewayRequestError(
            "data_classification must use the provider-neutral DataClassification contract"
        )
    message_tuple = tuple(messages)
    if not message_tuple:
        raise GatewayRequestError("at least one message is required")
    if any(not isinstance(message, Message) for message in message_tuple):
        raise GatewayRequestError("messages must contain provider-neutral Message values")
    if any(not message.content for message in message_tuple):
        raise GatewayRequestError("message content must be non-empty")
    if any(message.role is MessageRole.TOOL for message in message_tuple):
        raise GatewayRequestError(
            "tool-result continuation requires provider-native state and is not supported"
        )
    if not isinstance(context_tokens_estimated, int) or isinstance(context_tokens_estimated, bool):
        raise GatewayRequestError("context_tokens_estimated must be an integer")
    if context_tokens_estimated < 0:
        raise GatewayRequestError("context_tokens_estimated must be non-negative")
    if not isinstance(max_output_tokens, int) or isinstance(max_output_tokens, bool):
        raise GatewayRequestError("max_output_tokens must be an integer")
    if max_output_tokens <= 0:
        raise GatewayRequestError("max_output_tokens must be positive")
    if provider_timeout_seconds <= 0 or provider_timeout_seconds > 300:
        raise GatewayRequestError("provider timeout must be in the range (0, 300]")

    base_requirements = requirements or WorkloadRequirements()
    streaming_requirements = WorkloadRequirements(
        tool_calling=base_requirements.tool_calling,
        structured_output=base_requirements.structured_output,
        vision=base_requirements.vision,
        streaming=True,
        min_context_tokens=base_requirements.min_context_tokens,
    )
    try:
        request = GatewayRequest(
            schema_version="1.0",
            request_id=request_id or uuid4(),
            workload=workload,
            risk_level=risk_level,
            data_classification=data_classification,
            requirements=streaming_requirements,
            limits=limits or RequestLimits(),
            messages=message_tuple,
            agent_identity=agent_identity,
            tools=tuple(tools),
            structured_output=structured_output,
        )
    except (TypeError, ValueError) as exc:
        raise GatewayRequestError(str(exc)) from exc
    return _serialize_generate_request(
        request,
        context_tokens_estimated=context_tokens_estimated,
        max_output_tokens=max_output_tokens,
        provider_timeout_seconds=provider_timeout_seconds,
    )


def _serialize_generate_request(
    request: GatewayRequest,
    *,
    context_tokens_estimated: int,
    max_output_tokens: int,
    provider_timeout_seconds: float,
) -> dict[str, object]:
    limits: dict[str, object] = {
        "max_latency_ms": request.limits.max_latency_ms,
        "max_cost_usd": (
            _canonical_decimal(request.limits.max_cost_usd)
            if request.limits.max_cost_usd is not None
            else None
        ),
    }
    structured_output: dict[str, object] | None = None
    if request.structured_output is not None:
        structured_output = {
            "name": request.structured_output.name,
            "schema": dict(request.structured_output.schema),
        }
    return {
        "schema_version": request.schema_version,
        "request_id": str(request.request_id),
        "workload": request.workload,
        "risk_level": request.risk_level.value,
        "data_classification": request.data_classification.value,
        "stream": True,
        "requirements": {
            "tool_calling": request.requirements.tool_calling,
            "structured_output": request.requirements.structured_output,
            "vision": request.requirements.vision,
            "min_context_tokens": request.requirements.min_context_tokens,
        },
        "limits": limits,
        "messages": [
            {"role": message.role.value, "content": message.content} for message in request.messages
        ],
        "agent_identity": request.agent_identity,
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": dict(tool.input_schema),
            }
            for tool in request.tools
        ],
        "structured_output": structured_output,
        "context_tokens_estimated": context_tokens_estimated,
        "max_output_tokens": max_output_tokens,
        "provider_timeout_seconds": provider_timeout_seconds,
    }


def _validate_identity_response(response: httpx.Response) -> None:
    content_encoding = response.headers.get("content-encoding", "").strip().lower()
    if content_encoding not in _IDENTITY_CONTENT_ENCODINGS:
        raise GatewayProtocolError("gateway response content-encoding must be identity")


def _validate_success_content_length(
    response: httpx.Response,
    *,
    max_stream_bytes: int,
) -> None:
    value = response.headers.get("content-length")
    if value is None:
        return
    try:
        content_length = int(value)
    except ValueError as exc:
        raise GatewayProtocolError("gateway response content-length is invalid") from exc
    if content_length < 0:
        raise GatewayProtocolError("gateway response content-length is invalid")
    if content_length > max_stream_bytes:
        raise GatewayProtocolError("gateway SSE stream exceeds configured total size limit")


async def _http_error(response: httpx.Response) -> GatewayHTTPError:
    body = await _read_bounded_error_body(response)
    code = _extract_http_error_code(body) or f"http_status_{response.status_code}"
    return GatewayHTTPError(status_code=response.status_code, code=code)


async def _read_bounded_error_body(response: httpx.Response) -> bytes:
    content_encoding = response.headers.get("content-encoding", "").strip().lower()
    if content_encoding not in _IDENTITY_CONTENT_ENCODINGS:
        return b""

    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            parsed_length = int(content_length)
        except ValueError:
            return b""
        if parsed_length < 0 or parsed_length > _MAX_ERROR_BODY_BYTES:
            return b""

    body = bytearray()
    async for chunk in response.aiter_raw(chunk_size=_MAX_ERROR_BODY_BYTES):
        if len(body) + len(chunk) > _MAX_ERROR_BODY_BYTES:
            return b""
        body.extend(chunk)
    return bytes(body)


def _extract_http_error_code(body: bytes) -> str | None:
    if not body:
        return None
    try:
        payload = cast(object, json.loads(body))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    detail = payload.get("detail")
    if not isinstance(detail, dict):
        return None
    code = detail.get("code")
    if not isinstance(code, str) or not code:
        return None
    return code


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")
