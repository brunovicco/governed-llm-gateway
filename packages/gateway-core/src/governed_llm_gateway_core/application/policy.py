"""Policy Decision Point integration primitives and Phase 4 PEP orchestration."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from a2a_otel_kit import Observability
from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayRequest,
    PolicyProvenance,
    RiskLevel,
)

from governed_llm_gateway_core.domain.authorization import (
    AuthorizationBoundaryViolation,
    PolicyAuthorization,
    authorized_registry_candidates,
    enforce_selected_group,
)
from governed_llm_gateway_core.domain.model_registry import ModelDeployment, ModelRegistry
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext

from .provider import ProviderPort, ProviderRequest, ProviderResponse
from .telemetry import mark_span_failure, mark_span_success, set_gateway_span_attributes


class PolicyProjectionError(ValueError):
    """Raised when trusted context cannot be projected safely into the PDP contract."""


class PolicyDecisionErrorCode(StrEnum):
    """Stable, fail-closed Policy Model Router failure categories."""

    REJECTED = "rejected"
    INVALID_REQUEST = "invalid_request"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    MISCONFIGURED = "misconfigured"
    UNAVAILABLE = "unavailable"
    TRANSPORT = "transport"
    INVALID_RESPONSE = "invalid_response"


class PolicyDecisionError(RuntimeError):
    """Sanitized Policy Model Router failure with optional decision provenance."""

    def __init__(
        self,
        *,
        code: PolicyDecisionErrorCode,
        message: str,
        retryable: bool,
        status_code: int | None = None,
        provenance: PolicyProvenance | None = None,
        reason_code: str | None = None,
    ) -> None:
        """Create a bounded PDP failure that never stores raw response bodies or secrets."""
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.provenance = provenance
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class PolicyProjectionDefaults:
    """Gateway-owned ceilings used when a consumer does not provide a stricter limit."""

    max_latency_ms: int
    max_cost_usd: Decimal

    def __post_init__(self) -> None:
        """Require defaults representable by Policy Model Router API 1.0."""
        if self.max_latency_ms <= 0:
            raise ValueError("default max_latency_ms must be positive")
        if self.max_cost_usd <= 0:
            raise ValueError("default max_cost_usd must be positive")


@dataclass(frozen=True, slots=True)
class PolicyRequestMetadata:
    """Prompt-free metadata sent to the Policy Model Router."""

    request_id: UUID
    client_id: str
    environment: str
    workload: str
    risk_level: RiskLevel
    data_classification: DataClassification
    context_tokens_estimated: int
    max_output_tokens_estimated: int
    structured_output_required: bool
    max_latency_ms: int
    max_cost_usd: Decimal

    def __post_init__(self) -> None:
        """Validate the subset required by Policy Model Router API 1.0."""
        if not self.client_id or self.client_id.strip() != self.client_id:
            raise ValueError("client_id must be a non-empty normalized string")
        if not self.environment or self.environment.strip() != self.environment:
            raise ValueError("environment must be a non-empty normalized string")
        if not self.workload or self.workload.strip() != self.workload:
            raise ValueError("workload must be a non-empty normalized string")
        if self.context_tokens_estimated < 0:
            raise ValueError("context_tokens_estimated must be non-negative")
        if self.max_output_tokens_estimated <= 0:
            raise ValueError("max_output_tokens_estimated must be positive")
        if self.max_latency_ms <= 0:
            raise ValueError("max_latency_ms must be positive")
        if self.max_cost_usd <= 0:
            raise ValueError("max_cost_usd must be positive")


@dataclass(frozen=True, slots=True)
class PolicyAuthorizationDecision:
    """Accepted PDP decision and the provenance needed to audit it."""

    authorization: PolicyAuthorization
    provenance: PolicyProvenance
    decided_at: datetime
    reason: str
    service_version: str
    environment: str

    def __post_init__(self) -> None:
        """Require the authorization and provenance to refer to the same PDP decision."""
        if self.authorization.decision_id != self.provenance.decision_id:
            raise ValueError("authorization and provenance decision IDs must match")
        if self.decided_at.tzinfo is None or self.decided_at.utcoffset() is None:
            raise ValueError("PDP decided_at must be timezone-aware")
        if not self.reason:
            raise ValueError("PDP reason must be non-empty")
        if not self.service_version or not self.environment:
            raise ValueError("PDP service_version and environment must be non-empty")


class PolicyDecisionPort(Protocol):
    """Prompt-free boundary to the deterministic Policy Model Router."""

    async def authorize(self, request: PolicyRequestMetadata) -> PolicyAuthorizationDecision:
        """Return one accepted logical model-group authorization or fail closed."""
        ...


@dataclass(frozen=True, slots=True)
class AuthorizedCandidateSet:
    """Registry deployments remaining after the Phase 4 PDP group intersection."""

    policy: PolicyAuthorizationDecision
    registry_digest: str
    candidates: tuple[ModelDeployment, ...]


@dataclass(frozen=True, slots=True)
class PolicyEnforcedExecution:
    """Successful provider execution together with the PDP authorization that permitted it."""

    policy: PolicyAuthorizationDecision
    registry_digest: str
    deployment: ModelDeployment
    response: ProviderResponse


def project_policy_request(
    request: GatewayRequest,
    effective_context: EffectivePolicyContext,
    *,
    context_tokens_estimated: int,
    max_output_tokens_estimated: int,
    defaults: PolicyProjectionDefaults,
) -> PolicyRequestMetadata:
    """Project only trusted policy metadata; prompt/message content is intentionally unreachable."""
    if request.request_id.int == 0:
        raise PolicyProjectionError("request_id must not be the nil UUID")
    if effective_context.workload != request.workload:
        raise PolicyProjectionError("trusted workload does not match the gateway request workload")
    if (
        not effective_context.client_id
        or effective_context.client_id.strip() != effective_context.client_id
    ):
        raise PolicyProjectionError("trusted client_id must be a non-empty normalized string")
    if (
        not effective_context.environment
        or effective_context.environment.strip() != effective_context.environment
    ):
        raise PolicyProjectionError("trusted environment must be a non-empty normalized string")
    if context_tokens_estimated < 0:
        raise PolicyProjectionError("context_tokens_estimated must be non-negative")
    if max_output_tokens_estimated <= 0:
        raise PolicyProjectionError("max_output_tokens_estimated must be positive")

    caller_latency = request.limits.max_latency_ms
    max_latency_ms = (
        defaults.max_latency_ms
        if caller_latency is None
        else min(caller_latency, defaults.max_latency_ms)
    )
    caller_cost = request.limits.max_cost_usd
    if caller_cost is not None and caller_cost <= 0:
        raise PolicyProjectionError(
            "Policy Model Router API 1.0 cannot represent a non-positive cost ceiling"
        )
    max_cost_usd = (
        defaults.max_cost_usd if caller_cost is None else min(caller_cost, defaults.max_cost_usd)
    )

    return PolicyRequestMetadata(
        request_id=request.request_id,
        client_id=effective_context.client_id,
        environment=effective_context.environment,
        workload=effective_context.workload,
        risk_level=effective_context.risk_level,
        data_classification=effective_context.data_classification,
        context_tokens_estimated=context_tokens_estimated,
        max_output_tokens_estimated=max_output_tokens_estimated,
        structured_output_required=request.requirements.structured_output,
        max_latency_ms=max_latency_ms,
        max_cost_usd=max_cost_usd,
    )


class PolicyEnforcementService:
    """Phase 4 PEP flow: authorize first, then enforce one externally selected deployment."""

    def __init__(
        self,
        policy: PolicyDecisionPort,
        *,
        observability: Observability | None = None,
    ) -> None:
        """Bind the deterministic PDP port and optional Phase 9 telemetry foundation."""
        self._policy = policy
        self._observability = observability

    async def authorize_candidates(
        self,
        request: GatewayRequest,
        effective_context: EffectivePolicyContext,
        registry: ModelRegistry,
        *,
        context_tokens_estimated: int,
        max_output_tokens_estimated: int,
        defaults: PolicyProjectionDefaults,
    ) -> AuthorizedCandidateSet:
        """Return the registry intersection with the PDP-authorized logical model group."""
        metadata = project_policy_request(
            request,
            effective_context,
            context_tokens_estimated=context_tokens_estimated,
            max_output_tokens_estimated=max_output_tokens_estimated,
            defaults=defaults,
        )
        decision = await self._authorize(metadata)
        candidates = authorized_registry_candidates(registry, decision.authorization)
        return AuthorizedCandidateSet(
            policy=decision,
            registry_digest=registry.digest,
            candidates=candidates,
        )

    async def _authorize(self, metadata: PolicyRequestMetadata) -> PolicyAuthorizationDecision:
        if self._observability is None:
            return await self._policy.authorize(metadata)

        with self._observability.start_span(
            "policy.route",
            attributes={
                "request_id": str(metadata.request_id),
                "operation": "authorize",
                "environment": metadata.environment,
            },
            record_exception=False,
        ) as span:
            set_gateway_span_attributes(span, {"llm.workload": metadata.workload})
            try:
                decision = await self._policy.authorize(metadata)
            except PolicyDecisionError as exc:
                attributes: dict[str, object] = {"error.type": exc.code.value}
                if exc.status_code is not None:
                    attributes["http.status_code"] = exc.status_code
                set_gateway_span_attributes(span, attributes)
                mark_span_failure(span, exc.code.value)
                raise
            except Exception:
                mark_span_failure(span, "policy_unexpected_error")
                raise

            authorized_groups = decision.authorization.authorized_model_groups
            set_gateway_span_attributes(
                span,
                {
                    "routing.policy_id": decision.provenance.policy_id,
                    "routing.policy_version": decision.provenance.policy_version,
                    "routing.policy_digest": decision.provenance.policy_digest,
                    "routing.model_group": (
                        next(iter(authorized_groups)) if len(authorized_groups) == 1 else None
                    ),
                },
            )
            mark_span_success(span)
            return decision

    async def execute_selected(
        self,
        request: GatewayRequest,
        effective_context: EffectivePolicyContext,
        registry: ModelRegistry,
        *,
        selected_deployment_id: str,
        provider: ProviderPort,
        context_tokens_estimated: int,
        max_output_tokens_estimated: int,
        defaults: PolicyProjectionDefaults,
        provider_timeout_seconds: float = 30.0,
    ) -> PolicyEnforcedExecution:
        """Authorize before any provider call and reject an out-of-group selected deployment."""
        authorized = await self.authorize_candidates(
            request,
            effective_context,
            registry,
            context_tokens_estimated=context_tokens_estimated,
            max_output_tokens_estimated=max_output_tokens_estimated,
            defaults=defaults,
        )
        try:
            deployment = registry.by_id(selected_deployment_id)
        except KeyError as exc:
            raise AuthorizationBoundaryViolation(
                f"selected deployment {selected_deployment_id!r} is absent from the model registry"
            ) from exc

        enforce_selected_group(deployment.model_group, authorized.policy.authorization)
        if deployment not in authorized.candidates:
            raise AuthorizationBoundaryViolation(
                f"selected deployment {selected_deployment_id!r} is outside "
                "the authorized candidate set"
            )

        provider_request = ProviderRequest(
            model=deployment.model_id,
            messages=request.messages,
            max_output_tokens=max_output_tokens_estimated,
            timeout_seconds=provider_timeout_seconds,
        )
        response = await provider.generate(provider_request)
        return PolicyEnforcedExecution(
            policy=authorized.policy,
            registry_digest=authorized.registry_digest,
            deployment=deployment,
            response=response,
        )
