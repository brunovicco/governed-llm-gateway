"""FastAPI composition for the metadata-only route explanation surface."""

from contextlib import nullcontext
from decimal import Decimal
from typing import Annotated, Literal, Protocol
from uuid import UUID

from a2a_otel_kit import Observability, continue_trace
from fastapi import FastAPI, Header, HTTPException, Request
from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayRequest,
    RequestLimits,
    RiskLevel,
    WorkloadRequirements,
)
from governed_llm_gateway_core.application import (
    PolicyDecisionError,
    PolicyDecisionErrorCode,
    PolicyProjectionDefaults,
    PolicyProjectionError,
)
from governed_llm_gateway_core.application.ranking import (
    RankedCandidate,
    RankingDecision,
    RankingInvariantViolation,
    RouteExplainService,
)
from governed_llm_gateway_core.application.telemetry import (
    mark_span_failure,
    mark_span_success,
    set_gateway_span_attributes,
)
from governed_llm_gateway_core.domain.model_registry import ModelRegistry
from governed_llm_gateway_core.domain.ranking import RankingPolicy, RankingPolicyError
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext
from pydantic import BaseModel, ConfigDict, Field

_WORKLOAD_PATTERN = r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
_TRACE_HEADERS = ("traceparent", "tracestate")


class ClientAuthenticationError(RuntimeError):
    """Raised when the API credential cannot resolve an authoritative client context."""


class EffectiveContextResolver(Protocol):
    """Resolve an API credential to trusted policy context for one request."""

    async def resolve(
        self,
        *,
        api_key: str,
        request: GatewayRequest,
    ) -> EffectivePolicyContext:
        """Return authenticated/effective policy context or reject the credential."""
        ...


class ExplainRequirementsModel(BaseModel):
    """Caller-declared capability requirements used only for eligibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_calling: bool = False
    structured_output: bool = False
    vision: bool = False
    min_context_tokens: int = Field(default=0, ge=0)


class ExplainLimitsModel(BaseModel):
    """Caller ceilings; the core can only make them stricter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_latency_ms: int | None = Field(default=None, gt=0)
    max_cost_usd: Decimal | None = Field(default=None, ge=0)


class RouteExplainRequestModel(BaseModel):
    """Prompt-free request contract for ``POST /v1/route/explain``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    request_id: UUID
    workload: str = Field(min_length=3, max_length=128, pattern=_WORKLOAD_PATTERN)
    risk_level: RiskLevel
    data_classification: DataClassification
    requirements: ExplainRequirementsModel = Field(default_factory=ExplainRequirementsModel)
    limits: ExplainLimitsModel = Field(default_factory=ExplainLimitsModel)
    agent_identity: str | None = None
    context_tokens_estimated: int = Field(ge=0)
    max_output_tokens_estimated: int = Field(gt=0)

    def to_gateway_request(self) -> GatewayRequest:
        """Build the provider-neutral request without accepting prompt/message content."""
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
                min_context_tokens=self.requirements.min_context_tokens,
            ),
            limits=RequestLimits(
                max_latency_ms=self.limits.max_latency_ms,
                max_cost_usd=self.limits.max_cost_usd,
            ),
            messages=(),
            agent_identity=self.agent_identity,
        )


class PolicyExplainModel(BaseModel):
    """PDP provenance returned without policy internals or prompt data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str
    policy_id: str
    policy_version: str
    policy_digest: str


class RankedCandidateModel(BaseModel):
    """Explainable score for one eligible authorized deployment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    deployment: str
    score: str
    estimated_cost_usd: str


class RejectedCandidateModel(BaseModel):
    """Machine-readable eligibility rejection inside the authorized model group."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    deployment: str
    reason: str
    detail: str | None = None


class RankingExplainModel(BaseModel):
    """Deterministic ranking evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str
    policy_version: str
    policy_digest: str
    score_snapshot_id: str
    benchmark_snapshot_id: str | None = None
    score_provenance_mode: str | None = None
    manual_override_id: str | None = None
    selected_score: str | None
    alternatives: tuple[RankedCandidateModel, ...]
    rejected_candidates: tuple[RejectedCandidateModel, ...]


class RouteExplainResponseModel(BaseModel):
    """Response for the no-inference route explanation endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID
    authorized_model_group: str
    selected_deployment: str | None
    policy: PolicyExplainModel
    model_registry_digest: str
    ranking: RankingExplainModel


class RouteExplainCoordinator:
    """Compose credential resolution, PDP authorization, and deterministic ranking."""

    def __init__(
        self,
        *,
        context_resolver: EffectiveContextResolver,
        service: RouteExplainService,
        registry: ModelRegistry,
        ranking_policy: RankingPolicy,
        defaults: PolicyProjectionDefaults,
    ) -> None:
        """Bind trusted context resolution and immutable routing inputs."""
        self._context_resolver = context_resolver
        self._service = service
        self._registry = registry
        self._ranking_policy = ranking_policy
        self._defaults = defaults

    async def explain(
        self,
        *,
        api_key: str,
        payload: RouteExplainRequestModel,
    ) -> RouteExplainResponseModel:
        """Resolve trusted context and return ranking evidence without provider execution."""
        request = payload.to_gateway_request()
        effective_context = await self._context_resolver.resolve(
            api_key=api_key,
            request=request,
        )
        decision = await self._service.explain(
            request,
            effective_context,
            self._registry,
            self._ranking_policy,
            context_tokens_estimated=payload.context_tokens_estimated,
            max_output_tokens_estimated=payload.max_output_tokens_estimated,
            defaults=self._defaults,
        )
        return _response(payload.request_id, decision)


def create_app(
    coordinator: RouteExplainCoordinator,
    *,
    observability: Observability | None = None,
) -> FastAPI:
    """Create the API with authenticated explain routing and optional Phase 9 tracing."""
    app = FastAPI(title="Governed LLM Gateway", version="0.1.0")

    @app.post("/v1/route/explain", response_model=RouteExplainResponseModel)
    async def route_explain(
        request: Request,
        payload: RouteExplainRequestModel,
        gateway_api_key: Annotated[str, Header(alias="X-Gateway-API-Key", min_length=1)],
    ) -> RouteExplainResponseModel:
        trace_carrier = _trace_carrier(request)
        trace_context = continue_trace(trace_carrier) if trace_carrier else nullcontext()
        with trace_context:
            if observability is None:
                return await _execute_route_explain(
                    coordinator,
                    api_key=gateway_api_key,
                    payload=payload,
                )

            with observability.start_span(
                "llm.gateway.request",
                attributes={
                    "request_id": str(payload.request_id),
                    "operation": "route.explain",
                },
                record_exception=False,
            ) as span:
                set_gateway_span_attributes(
                    span,
                    {
                        "llm.workload": payload.workload,
                        "llm.streaming": False,
                    },
                )
                try:
                    response = await _execute_route_explain(
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
                    {
                        "routing.decision_id": response.ranking.decision_id,
                        "routing.policy_id": response.policy.policy_id,
                        "routing.policy_version": response.policy.policy_version,
                        "routing.policy_digest": response.policy.policy_digest,
                        "routing.model_group": response.authorized_model_group,
                        "registry.digest": response.model_registry_digest,
                        "ranking.policy_version": response.ranking.policy_version,
                        "ranking.policy_digest": response.ranking.policy_digest,
                        "ranking.score_snapshot_id": response.ranking.score_snapshot_id,
                        "llm.deployment": response.selected_deployment,
                    },
                )
                mark_span_success(span)
                return response

    return app


async def _execute_route_explain(
    coordinator: RouteExplainCoordinator,
    *,
    api_key: str,
    payload: RouteExplainRequestModel,
) -> RouteExplainResponseModel:
    try:
        return await coordinator.explain(
            api_key=api_key,
            payload=payload,
        )
    except ClientAuthenticationError as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_gateway_credential"},
        ) from exc
    except PolicyProjectionError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_policy_projection"},
        ) from exc
    except PolicyDecisionError as exc:
        raise _policy_http_exception(exc) from exc
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


def _trace_carrier(request: Request) -> dict[str, str]:
    return {
        name: value for name in _TRACE_HEADERS if (value := request.headers.get(name)) is not None
    }


def _http_error_code(error: HTTPException) -> str:
    if isinstance(error.detail, dict):
        code = error.detail.get("code")
        if isinstance(code, str) and code:
            return code
    return "http_error"


def _policy_http_exception(error: PolicyDecisionError) -> HTTPException:
    if error.code is PolicyDecisionErrorCode.AUTHENTICATION:
        status = 502
        code = "policy_router_authentication_failed"
    elif error.code in {
        PolicyDecisionErrorCode.AUTHORIZATION,
        PolicyDecisionErrorCode.REJECTED,
    }:
        status = 403
        code = "policy_denied"
    elif error.code is PolicyDecisionErrorCode.INVALID_REQUEST:
        status = 422
        code = "policy_request_rejected"
    else:
        status = 503
        code = "policy_router_unavailable"
    return HTTPException(status_code=status, detail={"code": code})


def _response(request_id: UUID, decision: RankingDecision) -> RouteExplainResponseModel:
    selected = decision.selected
    policy = decision.routing.policy
    return RouteExplainResponseModel(
        request_id=request_id,
        authorized_model_group=decision.routing.authorized_model_group,
        selected_deployment=(selected.deployment.deployment_id if selected is not None else None),
        policy=PolicyExplainModel(
            decision_id=policy.decision_id,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            policy_digest=policy.policy_digest,
        ),
        model_registry_digest=decision.routing.model_registry_digest,
        ranking=RankingExplainModel(
            decision_id=decision.routing.routing_decision_id,
            policy_version=decision.routing.ranking_policy_version,
            policy_digest=decision.ranking_policy_digest,
            score_snapshot_id=decision.score_snapshot_id,
            benchmark_snapshot_id=decision.routing.benchmark_snapshot_id,
            score_provenance_mode=decision.routing.score_provenance_mode,
            manual_override_id=decision.routing.manual_override_id,
            selected_score=(
                _canonical_decimal(selected.score.total) if selected is not None else None
            ),
            alternatives=tuple(_ranked_candidate(item) for item in decision.alternatives),
            rejected_candidates=tuple(
                RejectedCandidateModel(
                    deployment=item.deployment,
                    reason=item.reason.value,
                    detail=item.detail,
                )
                for item in decision.rejected_candidates
            ),
        ),
    )


def _ranked_candidate(candidate: RankedCandidate) -> RankedCandidateModel:
    return RankedCandidateModel(
        deployment=candidate.deployment.deployment_id,
        score=_canonical_decimal(candidate.score.total),
        estimated_cost_usd=_canonical_decimal(candidate.estimated_cost_usd),
    )


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")
