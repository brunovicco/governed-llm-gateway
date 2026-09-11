"""End-to-end no-inference composition for complexity-aware route explanation."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from governed_llm_gateway_contracts import ComplexityAssessment, GatewayRequest

from governed_llm_gateway_core.domain.complexity_quality import ComplexityQualityPolicy
from governed_llm_gateway_core.domain.evidence_ranking import EvidenceDrivenRankingPolicy
from governed_llm_gateway_core.domain.governance import ForwardableGovernanceAuthorization
from governed_llm_gateway_core.domain.model_registry import ModelRegistry
from governed_llm_gateway_core.domain.resilience import DeploymentHealthSnapshot
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext

from .complexity_ranking import ComplexityAwareRankingService
from .complexity_routing import (
    ComplexityNarrowingProvenance,
    narrow_authorized_candidates_by_complexity,
)
from .policy import (
    PolicyEnforcementService,
    PolicyProjectionDefaults,
    project_policy_request,
)
from .ranking import RankingDecision


class ComplexityEvaluator(Protocol):
    """Provider-neutral metadata evaluator with no authorization authority."""

    def assess(
        self,
        request: GatewayRequest,
        *,
        context_tokens_estimated: int,
        max_output_tokens_estimated: int,
    ) -> ComplexityAssessment:
        """Return deterministic complexity evidence for one request."""
        ...


@dataclass(frozen=True, slots=True)
class ComplexityRouteExplainDecision:
    """Composite metadata-only evidence for complexity-aware operational routing."""

    assessment: ComplexityAssessment
    narrowing: ComplexityNarrowingProvenance
    complexity_eligible_deployments: tuple[str, ...]
    ranking: RankingDecision


class ComplexityRouteExplainService:
    """Authorize first, then assess, narrow, and rank without invoking a provider."""

    def __init__(
        self,
        *,
        policy_enforcement: PolicyEnforcementService,
        complexity_evaluator: ComplexityEvaluator,
        quality_policy: ComplexityQualityPolicy,
        complexity_ranking: ComplexityAwareRankingService | None = None,
    ) -> None:
        """Bind immutable routing dependencies while preserving authority ordering."""
        self._policy_enforcement = policy_enforcement
        self._complexity_evaluator = complexity_evaluator
        self._quality_policy = quality_policy
        self._complexity_ranking = complexity_ranking or ComplexityAwareRankingService()

    async def explain(
        self,
        request: GatewayRequest,
        effective_context: EffectivePolicyContext,
        registry: ModelRegistry,
        ranking_policy: EvidenceDrivenRankingPolicy,
        *,
        context_tokens_estimated: int,
        max_output_tokens_estimated: int,
        defaults: PolicyProjectionDefaults,
        runtime_health: Mapping[str, DeploymentHealthSnapshot] | None = None,
        runtime_authorization: ForwardableGovernanceAuthorization | None = None,
    ) -> ComplexityRouteExplainDecision:
        """Compose the complete post-authorization complexity routing chain."""
        policy_request = project_policy_request(
            request,
            effective_context,
            context_tokens_estimated=context_tokens_estimated,
            max_output_tokens_estimated=max_output_tokens_estimated,
            defaults=defaults,
            runtime_authorization=runtime_authorization,
        )
        authorized = await self._policy_enforcement.authorize_candidates(
            request,
            effective_context,
            registry,
            context_tokens_estimated=context_tokens_estimated,
            max_output_tokens_estimated=max_output_tokens_estimated,
            defaults=defaults,
            runtime_authorization=runtime_authorization,
        )
        assessment = self._complexity_evaluator.assess(
            request,
            context_tokens_estimated=context_tokens_estimated,
            max_output_tokens_estimated=max_output_tokens_estimated,
        )
        eligible = narrow_authorized_candidates_by_complexity(
            workload=request.workload,
            authorized=authorized,
            assessment=assessment,
            ranking_policy=ranking_policy,
            quality_policy=self._quality_policy,
        )
        ranked = self._complexity_ranking.rank(
            request,
            effective_context,
            registry,
            eligible,
            policy_request,
            ranking_policy,
            runtime_health,
        )
        return ComplexityRouteExplainDecision(
            assessment=assessment,
            narrowing=ranked.narrowing,
            complexity_eligible_deployments=tuple(
                item.deployment_id for item in eligible.candidates
            ),
            ranking=ranked.ranking,
        )
