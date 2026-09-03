"""Phase 5 deterministic operational eligibility, ranking, and explainability."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from governed_llm_gateway_contracts import (
    CandidateRejection,
    Capability,
    DataClassification,
    GatewayRequest,
    RejectionReason,
    RoutingProvenance,
)

from governed_llm_gateway_core.domain.model_registry import ModelDeployment, ModelRegistry
from governed_llm_gateway_core.domain.ranking import (
    RankingPolicy,
    RankingWeights,
    StaticDeploymentScore,
)
from governed_llm_gateway_core.domain.resilience import (
    CircuitState,
    DeploymentHealthSnapshot,
    HealthStatus,
)
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext

from .policy import (
    AuthorizedCandidateSet,
    PolicyEnforcementService,
    PolicyProjectionDefaults,
    PolicyRequestMetadata,
    project_policy_request,
)

_CLASSIFICATION_ORDER = {
    DataClassification.PUBLIC: 0,
    DataClassification.INTERNAL: 1,
    DataClassification.CONFIDENTIAL: 2,
    DataClassification.RESTRICTED: 3,
}
_MILLION = Decimal("1000000")


class RankingInvariantViolation(RuntimeError):
    """Raised when ranking inputs contradict the established authorization boundary."""


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """Weighted deterministic score components for one eligible deployment."""

    quality: Decimal
    reliability: Decimal
    latency: Decimal
    cost: Decimal
    availability: Decimal
    total: Decimal


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    """One eligible deployment with deterministic score and bounded cost estimate."""

    deployment: ModelDeployment
    score: ScoreBreakdown
    estimated_cost_usd: Decimal


@dataclass(frozen=True, slots=True)
class RankingDecision:
    """Phase 5 selection result and metadata-only reconstruction evidence."""

    routing: RoutingProvenance
    ranking_policy_digest: str
    score_snapshot_id: str
    selected: RankedCandidate | None
    alternatives: tuple[RankedCandidate, ...]
    rejected_candidates: tuple[CandidateRejection, ...]


class OperationalRankingService:
    """Filter and rank only candidates already authorized by the Phase 4 PDP boundary."""

    def rank(
        self,
        request: GatewayRequest,
        effective_context: EffectivePolicyContext,
        registry: ModelRegistry,
        authorized: AuthorizedCandidateSet,
        policy_request: PolicyRequestMetadata,
        ranking_policy: RankingPolicy,
        runtime_health: Mapping[str, DeploymentHealthSnapshot] | None = None,
    ) -> RankingDecision:
        """Return a deterministic selection/explanation without invoking a provider."""
        self._validate_boundary(
            request,
            effective_context,
            registry,
            authorized,
            policy_request,
        )
        workload_policy = ranking_policy.for_workload(request.workload)

        ranked: list[RankedCandidate] = []
        rejected: list[CandidateRejection] = []
        authorized_groups = authorized.policy.authorization.authorized_model_groups

        for deployment in sorted(
            authorized.candidates,
            key=lambda candidate: candidate.deployment_id,
        ):
            if deployment.model_group not in authorized_groups:
                raise RankingInvariantViolation(
                    "Phase 4 candidate set contained a deployment outside PDP authorization"
                )
            static_score = workload_policy.score_for(deployment.deployment_id)
            rejection = _eligibility_rejection(
                request,
                effective_context,
                policy_request,
                deployment,
                static_score,
                runtime_health,
            )
            if rejection is not None:
                rejected.append(rejection)
                continue

            if static_score is None:
                raise RankingInvariantViolation(
                    "eligible deployment reached scoring without static ranking inputs"
                )
            estimated_cost = _estimate_cost(
                deployment,
                policy_request.context_tokens_estimated,
                policy_request.max_output_tokens_estimated,
            )
            if estimated_cost is None:
                raise RankingInvariantViolation(
                    "eligible deployment reached scoring without pricing metadata"
                )
            ranked.append(
                RankedCandidate(
                    deployment=deployment,
                    score=_score(workload_policy.weights, static_score),
                    estimated_cost_usd=estimated_cost,
                )
            )

        ranked.sort(
            key=lambda candidate: (-candidate.score.total, candidate.deployment.deployment_id)
        )
        selected = ranked[0] if ranked else None
        alternatives = tuple(ranked[1:]) if selected is not None else ()
        rejections = tuple(sorted(rejected, key=lambda item: item.deployment))
        routing_decision_id = _decision_id(
            request=request,
            authorized=authorized,
            policy_request=policy_request,
            ranking_policy=ranking_policy,
            ranked=tuple(ranked),
            rejected=rejections,
        )
        authorized_model_group = next(iter(authorized_groups))
        routing = RoutingProvenance(
            routing_decision_id=routing_decision_id,
            policy=authorized.policy.provenance,
            authorized_model_group=authorized_model_group,
            model_registry_digest=authorized.registry_digest,
            ranking_policy_version=ranking_policy.policy_version,
            ranking_policy_digest=ranking_policy.digest,
            score_snapshot_id=ranking_policy.score_snapshot_id,
            provider=selected.deployment.provider if selected is not None else None,
            model=selected.deployment.model_id if selected is not None else None,
            deployment=selected.deployment.deployment_id if selected is not None else None,
            rejected_candidates=rejections,
        )
        return RankingDecision(
            routing=routing,
            ranking_policy_digest=ranking_policy.digest,
            score_snapshot_id=ranking_policy.score_snapshot_id,
            selected=selected,
            alternatives=alternatives,
            rejected_candidates=rejections,
        )

    @staticmethod
    def _validate_boundary(
        request: GatewayRequest,
        effective_context: EffectivePolicyContext,
        registry: ModelRegistry,
        authorized: AuthorizedCandidateSet,
        policy_request: PolicyRequestMetadata,
    ) -> None:
        if registry.digest != authorized.registry_digest:
            raise RankingInvariantViolation(
                "model registry changed after the Phase 4 authorization candidate set was built"
            )
        if request.workload != effective_context.workload:
            raise RankingInvariantViolation(
                "trusted workload does not match request workload at ranking boundary"
            )
        if policy_request.workload != effective_context.workload:
            raise RankingInvariantViolation(
                "projected policy workload does not match trusted context"
            )
        if policy_request.environment != effective_context.environment:
            raise RankingInvariantViolation(
                "projected policy environment does not match trusted context"
            )
        if authorized.policy.environment != effective_context.environment:
            raise RankingInvariantViolation(
                "PDP decision environment does not match trusted context"
            )
        if len(authorized.policy.authorization.authorized_model_groups) != 1:
            raise RankingInvariantViolation(
                "Phase 5 requires exactly one PDP-authorized logical model group"
            )


class RouteExplainService:
    """Authorize, filter, rank, and explain without performing model inference."""

    def __init__(
        self,
        policy_enforcement: PolicyEnforcementService,
        ranking: OperationalRankingService | None = None,
    ) -> None:
        """Bind the Phase 4 authorization service and deterministic ranking implementation."""
        self._policy_enforcement = policy_enforcement
        self._ranking = ranking or OperationalRankingService()

    async def explain(
        self,
        request: GatewayRequest,
        effective_context: EffectivePolicyContext,
        registry: ModelRegistry,
        ranking_policy: RankingPolicy,
        *,
        context_tokens_estimated: int,
        max_output_tokens_estimated: int,
        defaults: PolicyProjectionDefaults,
        runtime_health: Mapping[str, DeploymentHealthSnapshot] | None = None,
    ) -> RankingDecision:
        """Return the routing explanation and never call a provider."""
        policy_request = project_policy_request(
            request,
            effective_context,
            context_tokens_estimated=context_tokens_estimated,
            max_output_tokens_estimated=max_output_tokens_estimated,
            defaults=defaults,
        )
        authorized = await self._policy_enforcement.authorize_candidates(
            request,
            effective_context,
            registry,
            context_tokens_estimated=context_tokens_estimated,
            max_output_tokens_estimated=max_output_tokens_estimated,
            defaults=defaults,
        )
        return self._ranking.rank(
            request,
            effective_context,
            registry,
            authorized,
            policy_request,
            ranking_policy,
            runtime_health,
        )


def _eligibility_rejection(
    request: GatewayRequest,
    effective_context: EffectivePolicyContext,
    policy_request: PolicyRequestMetadata,
    deployment: ModelDeployment,
    static_score: StaticDeploymentScore | None,
    runtime_health: Mapping[str, DeploymentHealthSnapshot] | None,
) -> CandidateRejection | None:
    if not deployment.enabled:
        return CandidateRejection(
            deployment=deployment.deployment_id,
            reason=RejectionReason.DEPLOYMENT_DISABLED,
        )

    health_rejection = _runtime_health_rejection(deployment, runtime_health)
    if health_rejection is not None:
        return health_rejection

    if effective_context.environment not in deployment.allowed_environments:
        return CandidateRejection(
            deployment=deployment.deployment_id,
            reason=RejectionReason.PROVIDER_NOT_AUTHORIZED,
            detail="environment_not_allowed",
        )
    if (
        _CLASSIFICATION_ORDER[effective_context.data_classification]
        > _CLASSIFICATION_ORDER[deployment.max_data_classification]
    ):
        return CandidateRejection(
            deployment=deployment.deployment_id,
            reason=RejectionReason.PROVIDER_NOT_AUTHORIZED,
            detail="data_classification_exceeds_deployment_max",
        )

    missing = _missing_capabilities(request, deployment)
    if missing:
        return CandidateRejection(
            deployment=deployment.deployment_id,
            reason=RejectionReason.MISSING_CAPABILITY,
            detail=",".join(capability.value for capability in missing),
        )

    required_context = max(
        request.requirements.min_context_tokens,
        policy_request.context_tokens_estimated + policy_request.max_output_tokens_estimated,
    )
    if deployment.context_tokens < required_context:
        return CandidateRejection(
            deployment=deployment.deployment_id,
            reason=RejectionReason.CONTEXT_TOO_SMALL,
            detail=f"required={required_context};available={deployment.context_tokens}",
        )

    if static_score is None:
        return CandidateRejection(
            deployment=deployment.deployment_id,
            reason=RejectionReason.RANKING_SCORE_UNAVAILABLE,
        )

    estimated_cost = _estimate_cost(
        deployment,
        policy_request.context_tokens_estimated,
        policy_request.max_output_tokens_estimated,
    )
    if estimated_cost is None:
        return CandidateRejection(
            deployment=deployment.deployment_id,
            reason=RejectionReason.PRICING_UNAVAILABLE,
        )
    if estimated_cost > policy_request.max_cost_usd:
        return CandidateRejection(
            deployment=deployment.deployment_id,
            reason=RejectionReason.COST_LIMIT_EXCEEDED,
            detail=(
                f"estimated={_canonical_decimal(estimated_cost)};"
                f"limit={_canonical_decimal(policy_request.max_cost_usd)}"
            ),
        )
    if static_score.expected_latency_ms > policy_request.max_latency_ms:
        return CandidateRejection(
            deployment=deployment.deployment_id,
            reason=RejectionReason.LATENCY_LIMIT_EXCEEDED,
            detail=(
                f"expected_ms={static_score.expected_latency_ms};"
                f"limit_ms={policy_request.max_latency_ms}"
            ),
        )
    return None


def _runtime_health_rejection(
    deployment: ModelDeployment,
    runtime_health: Mapping[str, DeploymentHealthSnapshot] | None,
) -> CandidateRejection | None:
    if runtime_health is None:
        return None
    health = runtime_health.get(deployment.deployment_id)
    if health is None:
        return CandidateRejection(
            deployment=deployment.deployment_id,
            reason=RejectionReason.DEPLOYMENT_UNHEALTHY,
            detail="runtime_health_unavailable",
        )
    if health.deployment_id != deployment.deployment_id:
        raise RankingInvariantViolation("runtime health snapshot deployment identity mismatch")
    if health.circuit_state is CircuitState.OPEN:
        return CandidateRejection(
            deployment=deployment.deployment_id,
            reason=RejectionReason.CIRCUIT_BREAKER_OPEN,
        )
    if health.status is HealthStatus.UNHEALTHY:
        return CandidateRejection(
            deployment=deployment.deployment_id,
            reason=RejectionReason.DEPLOYMENT_UNHEALTHY,
        )
    return None


def _missing_capabilities(
    request: GatewayRequest,
    deployment: ModelDeployment,
) -> tuple[Capability, ...]:
    required: list[Capability] = [Capability.TEXT]
    if request.requirements.vision:
        required.append(Capability.VISION)
    if request.requirements.tool_calling:
        required.append(Capability.TOOL_CALLING)
    if request.requirements.structured_output:
        required.append(Capability.STRUCTURED_OUTPUT)
    if request.requirements.streaming:
        required.append(Capability.STREAMING)
    return tuple(capability for capability in required if capability not in deployment.capabilities)


def _estimate_cost(
    deployment: ModelDeployment,
    input_tokens: int,
    output_tokens: int,
) -> Decimal | None:
    pricing = deployment.pricing
    if pricing is None:
        return None
    return (
        pricing.input_usd_per_million_tokens * Decimal(input_tokens) / _MILLION
        + pricing.output_usd_per_million_tokens * Decimal(output_tokens) / _MILLION
    )


def _score(weights: RankingWeights, static: StaticDeploymentScore) -> ScoreBreakdown:
    quality = weights.quality * static.quality
    reliability = weights.reliability * static.reliability
    latency = weights.latency * static.latency
    cost = weights.cost * static.cost
    availability = weights.availability * static.availability
    return ScoreBreakdown(
        quality=quality,
        reliability=reliability,
        latency=latency,
        cost=cost,
        availability=availability,
        total=quality + reliability + latency + cost + availability,
    )


def _decision_id(
    *,
    request: GatewayRequest,
    authorized: AuthorizedCandidateSet,
    policy_request: PolicyRequestMetadata,
    ranking_policy: RankingPolicy,
    ranked: tuple[RankedCandidate, ...],
    rejected: tuple[CandidateRejection, ...],
) -> str:
    payload = {
        "request_id": str(request.request_id),
        "policy_decision_id": authorized.policy.provenance.decision_id,
        "policy_digest": authorized.policy.provenance.policy_digest,
        "authorized_model_groups": sorted(authorized.policy.authorization.authorized_model_groups),
        "registry_digest": authorized.registry_digest,
        "ranking_policy_version": ranking_policy.policy_version,
        "ranking_policy_digest": ranking_policy.digest,
        "score_snapshot_id": ranking_policy.score_snapshot_id,
        "max_latency_ms": policy_request.max_latency_ms,
        "max_cost_usd": _canonical_decimal(policy_request.max_cost_usd),
        "context_tokens_estimated": policy_request.context_tokens_estimated,
        "max_output_tokens_estimated": policy_request.max_output_tokens_estimated,
        "ranked": [
            {
                "deployment": candidate.deployment.deployment_id,
                "score": _canonical_decimal(candidate.score.total),
                "estimated_cost_usd": _canonical_decimal(candidate.estimated_cost_usd),
            }
            for candidate in ranked
        ],
        "rejected": [
            {
                "deployment": item.deployment,
                "reason": item.reason.value,
                "detail": item.detail,
            }
            for item in rejected
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")
