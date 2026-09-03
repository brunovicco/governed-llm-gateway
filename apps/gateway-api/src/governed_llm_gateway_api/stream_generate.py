"""Authenticated SSE generation surface for governed streaming execution."""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import aclosing, nullcontext
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from a2a_otel_kit import Observability, continue_trace, inject_trace_context
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayRequest,
    GatewayStreamEvent,
    Message,
    MessageRole,
    RequestLimits,
    RiskLevel,
    StreamEventType,
    StructuredOutputSchema,
    ToolDefinition,
    WorkloadRequirements,
)
from governed_llm_gateway_core.application import (
    InMemoryHealthTracker,
    PolicyDecisionError,
    PolicyDecisionErrorCode,
    PolicyProjectionDefaults,
    PolicyProjectionError,
)
from governed_llm_gateway_core.application.ranking import (
    RankingDecision,
    RankingInvariantViolation,
    RouteExplainService,
)
from governed_llm_gateway_core.application.streaming import StreamingExecutionService
from governed_llm_gateway_core.application.telemetry import (
    mark_span_cancelled,
    mark_span_failure,
    mark_span_success,
    set_gateway_span_attributes,
)
from governed_llm_gateway_core.domain.model_registry import ModelRegistry
from governed_llm_gateway_core.domain.ranking import RankingPolicy, RankingPolicyError
from governed_llm_gateway_core.domain.structured import (
    validate_structured_output_schema,
    validate_tool_definitions,
)
from pydantic import BaseModel, ConfigDict, Field

from .route_explain import ClientAuthenticationError, EffectiveContextResolver

_WORKLOAD_PATTERN = r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
_TRACE_HEADERS = ("traceparent", "tracestate")


class GenerateMessageModel(BaseModel):
    """One provider-neutral message accepted by the streaming API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: MessageRole
    content: str = Field(min_length=1)


class GenerateRequirementsModel(BaseModel):
    """Caller-declared capabilities; streaming itself is mandatory for this endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_calling: bool = False
    structured_output: bool = False
    vision: bool = False
    min_context_tokens: int = Field(default=0, ge=0)


class GenerateLimitsModel(BaseModel):
    """Caller ceilings that policy/ranking may only narrow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_latency_ms: int | None = Field(default=None, gt=0)
    max_cost_usd: Decimal | None = Field(default=None, ge=0)


class GenerateToolModel(BaseModel):
    """Business-tool definition forwarded for model tool calling but never executed here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str
    input_schema: dict[str, object]

    def to_contract(self) -> ToolDefinition:
        """Build the provider-neutral immutable tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
        )


class GenerateStructuredOutputModel(BaseModel):
    """Provider-neutral structured-output request schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    schema_definition: dict[str, object] = Field(alias="schema")

    def to_contract(self) -> StructuredOutputSchema:
        """Build the immutable structured-output contract."""
        return StructuredOutputSchema(name=self.name, schema=self.schema_definition)


class GenerateRequestModel(BaseModel):
    """Request contract for ``POST /v1/generate`` streaming execution."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_version: Literal["1.0"] = "1.0"
    request_id: UUID
    workload: str = Field(min_length=3, max_length=128, pattern=_WORKLOAD_PATTERN)
    risk_level: RiskLevel
    data_classification: DataClassification
    stream: Literal[True] = True
    requirements: GenerateRequirementsModel = Field(default_factory=GenerateRequirementsModel)
    limits: GenerateLimitsModel = Field(default_factory=GenerateLimitsModel)
    messages: tuple[GenerateMessageModel, ...] = Field(min_length=1)
    agent_identity: str | None = None
    tools: tuple[GenerateToolModel, ...] = ()
    structured_output: GenerateStructuredOutputModel | None = None
    context_tokens_estimated: int = Field(ge=0)
    max_output_tokens: int = Field(gt=0)
    provider_timeout_seconds: float = Field(default=30.0, gt=0, le=300.0)

    def to_gateway_request(self) -> GatewayRequest:
        """Validate all execution contracts before an HTTP 200 streaming response can begin."""
        messages = tuple(Message(role=item.role, content=item.content) for item in self.messages)
        if any(message.role is MessageRole.TOOL for message in messages):
            raise ValueError(
                "tool-result continuation is not supported without exact provider-native state"
            )

        tools = tuple(item.to_contract() for item in self.tools)
        structured_output = (
            self.structured_output.to_contract() if self.structured_output is not None else None
        )
        if tools:
            validate_tool_definitions(tools)
        if structured_output is not None:
            validate_structured_output_schema(structured_output)

        return GatewayRequest(
            schema_version=self.schema_version,
            request_id=self.request_id,
            workload=self.workload,
            risk_level=self.risk_level,
            data_classification=self.data_classification,
            requirements=WorkloadRequirements(
                tool_calling=self.requirements.tool_calling,
                structured_output=self.requirements.structured_output,
                vision=self.requirements.vision,
                streaming=True,
                min_context_tokens=self.requirements.min_context_tokens,
            ),
            limits=RequestLimits(
                max_latency_ms=self.limits.max_latency_ms,
                max_cost_usd=self.limits.max_cost_usd,
            ),
            messages=messages,
            agent_identity=self.agent_identity,
            tools=tools,
            structured_output=structured_output,
        )


@dataclass(frozen=True, slots=True)
class PreparedStreamingExecution:
    """Authorized/ranked execution state established before the SSE response begins."""

    request: GatewayRequest
    decision: RankingDecision
    max_output_tokens: int
    provider_timeout_seconds: float


class NoEligibleStreamingDeploymentError(RuntimeError):
    """Raised when pre-stream ranking finds no authorized healthy streaming deployment."""


class GenerateCoordinator:
    """Authenticate, authorize, rank, then stream without widening the PDP candidate set."""

    def __init__(
        self,
        *,
        context_resolver: EffectiveContextResolver,
        route_service: RouteExplainService,
        streaming_service: StreamingExecutionService,
        health: InMemoryHealthTracker,
        registry: ModelRegistry,
        ranking_policy: RankingPolicy,
        defaults: PolicyProjectionDefaults,
    ) -> None:
        """Bind trusted context, deterministic routing inputs, runtime health, and execution."""
        self._context_resolver = context_resolver
        self._route_service = route_service
        self._streaming_service = streaming_service
        self._health = health
        self._registry = registry
        self._ranking_policy = ranking_policy
        self._defaults = defaults

    async def prepare(
        self,
        *,
        api_key: str,
        payload: GenerateRequestModel,
    ) -> PreparedStreamingExecution:
        """Finish authentication/PDP/ranking before returning an SSE HTTP response."""
        request = payload.to_gateway_request()
        effective_context = await self._context_resolver.resolve(
            api_key=api_key,
            request=request,
        )
        deployment_ids = tuple(
            sorted(deployment.deployment_id for deployment in self._registry.deployments)
        )
        runtime_health = self._health.snapshots(deployment_ids)
        decision = await self._route_service.explain(
            request,
            effective_context,
            self._registry,
            self._ranking_policy,
            context_tokens_estimated=payload.context_tokens_estimated,
            max_output_tokens_estimated=payload.max_output_tokens,
            defaults=self._defaults,
            runtime_health=runtime_health,
        )
        if decision.selected is None:
            raise NoEligibleStreamingDeploymentError(
                "no eligible authorized streaming deployment is available"
            )
        return PreparedStreamingExecution(
            request=request,
            decision=decision,
            max_output_tokens=payload.max_output_tokens,
            provider_timeout_seconds=payload.provider_timeout_seconds,
        )

    def stream(
        self,
        prepared: PreparedStreamingExecution,
    ) -> AsyncGenerator[GatewayStreamEvent]:
        """Start provider execution only from the already-authorized/ranked prepared state."""
        return self._streaming_service.stream(
            prepared.request,
            prepared.decision,
            max_output_tokens=prepared.max_output_tokens,
            provider_timeout_seconds=prepared.provider_timeout_seconds,
        )


def attach_generate_route(
    app: FastAPI,
    coordinator: GenerateCoordinator,
    *,
    observability: Observability | None = None,
) -> None:
    """Attach governed SSE generation with optional Phase 9 trace continuation."""

    @app.post("/v1/generate", response_class=StreamingResponse)
    async def generate(
        request: Request,
        payload: GenerateRequestModel,
        gateway_api_key: Annotated[str, Header(alias="X-Gateway-API-Key", min_length=1)],
    ) -> StreamingResponse:
        trace_carrier = _trace_carrier(request)
        trace_context = continue_trace(trace_carrier) if trace_carrier else nullcontext()
        stream_parent_carrier: dict[str, str] = {}

        with trace_context:
            if observability is None:
                prepared = await _prepare_generation(
                    coordinator,
                    api_key=gateway_api_key,
                    payload=payload,
                )
            else:
                with observability.start_span(
                    "llm.gateway.request",
                    attributes={
                        "request_id": str(payload.request_id),
                        "operation": "generate",
                    },
                    record_exception=False,
                ) as span:
                    set_gateway_span_attributes(
                        span,
                        {
                            "llm.workload": payload.workload,
                            "llm.streaming": True,
                        },
                    )
                    try:
                        prepared = await _prepare_generation(
                            coordinator,
                            api_key=gateway_api_key,
                            payload=payload,
                        )
                    except HTTPException as exc:
                        set_gateway_span_attributes(span, {"http.status_code": exc.status_code})
                        mark_span_failure(span, _http_error_code(exc))
                        raise
                    except Exception:
                        mark_span_failure(span, "gateway_unexpected_error")
                        raise

                    set_gateway_span_attributes(
                        span,
                        _routing_attributes(prepared.decision),
                    )
                    inject_trace_context(stream_parent_carrier)
                    mark_span_success(span)

        return StreamingResponse(
            _sse_body(
                coordinator,
                prepared,
                observability=observability,
                trace_carrier=stream_parent_carrier,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )


async def _prepare_generation(
    coordinator: GenerateCoordinator,
    *,
    api_key: str,
    payload: GenerateRequestModel,
) -> PreparedStreamingExecution:
    try:
        return await coordinator.prepare(
            api_key=api_key,
            payload=payload,
        )
    except ClientAuthenticationError as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_gateway_credential"},
        ) from exc
    except NoEligibleStreamingDeploymentError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "no_eligible_streaming_deployment"},
        ) from exc
    except RankingPolicyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "ranking_policy_unavailable"},
        ) from exc
    except RankingInvariantViolation as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "ranking_invariant_violation"},
        ) from exc
    except PolicyDecisionError as exc:
        raise _policy_http_exception(exc) from exc
    except (ValueError, PolicyProjectionError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_generation_request"},
        ) from exc


async def _sse_body(
    coordinator: GenerateCoordinator,
    prepared: PreparedStreamingExecution,
    *,
    observability: Observability | None,
    trace_carrier: dict[str, str],
) -> AsyncGenerator[str]:
    if observability is None:
        stream = coordinator.stream(prepared)
        async with aclosing(stream) as events:
            async for event in events:
                yield _encode_sse(event)
        return

    trace_context = continue_trace(trace_carrier) if trace_carrier else nullcontext()
    with trace_context:
        with observability.start_span(
            "llm.gateway.stream",
            attributes={
                "request_id": str(prepared.request.request_id),
                "operation": "stream",
            },
            record_exception=False,
        ) as span:
            set_gateway_span_attributes(
                span,
                {
                    "llm.workload": prepared.request.workload,
                    "llm.streaming": True,
                    **_routing_attributes(prepared.decision),
                },
            )
            terminal = False
            stream = coordinator.stream(prepared)
            try:
                async with aclosing(stream) as events:
                    async for event in events:
                        if event.usage is not None:
                            set_gateway_span_attributes(
                                span,
                                {
                                    "llm.input_tokens": event.usage.input_tokens,
                                    "llm.output_tokens": event.usage.output_tokens,
                                },
                            )
                        if event.event_type is StreamEventType.RESPONSE_FAILED:
                            terminal = True
                            set_gateway_span_attributes(
                                span,
                                {"llm.partial": event.partial},
                            )
                            mark_span_failure(
                                span,
                                event.error.code if event.error is not None else "stream_failed",
                            )
                        elif event.event_type is StreamEventType.RESPONSE_COMPLETED:
                            terminal = True
                            if event.routing is not None:
                                set_gateway_span_attributes(
                                    span,
                                    _routing_attributes_from_provenance(event.routing),
                                )
                            mark_span_success(span)
                        yield _encode_sse(event)
            except asyncio.CancelledError:
                mark_span_cancelled(span)
                raise
            except Exception:
                mark_span_failure(span, "stream_unexpected_error")
                raise
            finally:
                if not terminal:
                    set_gateway_span_attributes(span, {"llm.partial": False})


def _trace_carrier(request: Request) -> dict[str, str]:
    return {
        name: value
        for name in _TRACE_HEADERS
        if (value := request.headers.get(name)) is not None
    }


def _routing_attributes(decision: RankingDecision) -> dict[str, object]:
    return _routing_attributes_from_provenance(decision.routing)


def _routing_attributes_from_provenance(routing: object) -> dict[str, object]:
    if not isinstance(routing, type(prepared_routing := _routing_type_marker())):
        del prepared_routing
    return {
        "routing.decision_id": routing.routing_decision_id,
        "routing.policy_id": routing.policy.policy_id,
        "routing.policy_version": routing.policy.policy_version,
        "routing.policy_digest": routing.policy.policy_digest,
        "routing.model_group": routing.authorized_model_group,
        "registry.digest": routing.model_registry_digest,
        "ranking.policy_version": routing.ranking_policy_version,
        "ranking.policy_digest": routing.ranking_policy_digest,
        "ranking.score_snapshot_id": routing.score_snapshot_id,
        "llm.provider": routing.provider,
        "llm.model": routing.model,
        "llm.deployment": routing.deployment,
        "llm.fallback_count": max(0, len(routing.fallback_sequence) - 1),
    }


def _routing_type_marker() -> object:
    from governed_llm_gateway_contracts import RoutingProvenance

    return RoutingProvenance


def _http_error_code(error: HTTPException) -> str:
    if isinstance(error.detail, dict):
        code = error.detail.get("code")
        if isinstance(code, str) and code:
            return code
    return "http_error"


def _encode_sse(event: GatewayStreamEvent) -> str:
    payload = _event_payload(event)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"event: {event.event_type.value}\nid: {event.sequence_number}\ndata: {encoded}\n\n"


def _event_payload(event: GatewayStreamEvent) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_type": event.event_type.value,
        "request_id": str(event.request_id),
        "sequence_number": event.sequence_number,
    }
    if event.routing is not None:
        payload["routing"] = _routing_payload(event)
    if event.delta is not None:
        payload["delta"] = event.delta
    if event.tool_call_id is not None:
        payload["tool_call_id"] = event.tool_call_id
    if event.tool_name is not None:
        payload["tool_name"] = event.tool_name
    if event.tool_call is not None:
        payload["tool_call"] = {
            "call_id": event.tool_call.call_id,
            "name": event.tool_call.name,
            "arguments": dict(event.tool_call.arguments),
        }
    if event.usage is not None:
        usage: dict[str, object] = {
            "input_tokens": event.usage.input_tokens,
            "output_tokens": event.usage.output_tokens,
        }
        if event.usage.total_cost_usd is not None:
            usage["total_cost_usd"] = _canonical_decimal(event.usage.total_cost_usd)
        payload["usage"] = usage
    if event.finish_reason is not None:
        payload["finish_reason"] = event.finish_reason
    if event.error is not None:
        payload["error"] = {
            "code": event.error.code,
            "message": event.error.message,
            "retryable": event.error.retryable,
        }
    if event.partial:
        payload["partial"] = True
    return payload


def _routing_payload(event: GatewayStreamEvent) -> dict[str, object]:
    routing = event.routing
    if routing is None:
        raise ValueError("routing payload requested without routing provenance")
    payload: dict[str, object] = {
        "routing_decision_id": routing.routing_decision_id,
        "policy": {
            "decision_id": routing.policy.decision_id,
            "policy_id": routing.policy.policy_id,
            "policy_version": routing.policy.policy_version,
            "policy_digest": routing.policy.policy_digest,
        },
        "authorized_model_group": routing.authorized_model_group,
        "model_registry_digest": routing.model_registry_digest,
        "ranking_policy_version": routing.ranking_policy_version,
        "fallback_sequence": list(routing.fallback_sequence),
    }
    optional_fields = {
        "ranking_policy_digest": routing.ranking_policy_digest,
        "score_snapshot_id": routing.score_snapshot_id,
        "benchmark_snapshot_id": routing.benchmark_snapshot_id,
        "provider": routing.provider,
        "model": routing.model,
        "deployment": routing.deployment,
    }
    for name, value in optional_fields.items():
        if value is not None:
            payload[name] = value
    if routing.rejected_candidates:
        payload["rejected_candidates"] = [
            {
                "deployment": item.deployment,
                "reason": item.reason.value,
                **({"detail": item.detail} if item.detail is not None else {}),
            }
            for item in routing.rejected_candidates
        ]
    return payload


def _policy_http_exception(error: PolicyDecisionError) -> HTTPException:
    if error.code is PolicyDecisionErrorCode.AUTHENTICATION:
        return HTTPException(
            status_code=502,
            detail={"code": "policy_router_authentication_failed"},
        )
    if error.code in {
        PolicyDecisionErrorCode.AUTHORIZATION,
        PolicyDecisionErrorCode.REJECTED,
    }:
        return HTTPException(status_code=403, detail={"code": "policy_denied"})
    if error.code is PolicyDecisionErrorCode.INVALID_REQUEST:
        return HTTPException(status_code=422, detail={"code": "policy_request_rejected"})
    return HTTPException(status_code=503, detail={"code": "policy_router_unavailable"})


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")
