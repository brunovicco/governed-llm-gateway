"""Composition boundary from complexity-eligible candidates to operational ranking."""

from collections.abc import Mapping
from dataclasses import dataclass

from governed_llm_gateway_contracts import GatewayRequest

from governed_llm_gateway_core.domain.model_registry import ModelRegistry
from governed_llm_gateway_core.domain.ranking import RankingPolicy
from governed_llm_gateway_core.domain.resilience import DeploymentHealthSnapshot
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext

from .complexity_routing import (
    ComplexityEligibleCandidateSet,
    ComplexityNarrowingProvenance,
)
from .policy import AuthorizedCandidateSet, PolicyRequestMetadata
from .ranking import OperationalRankingService, RankingDecision


class ComplexityRankingError(RuntimeError):
    """Raised when complexity-aware ranking would violate the subset boundary."""


@dataclass(frozen=True, slots=True)
class ComplexityAwareRankingDecision:
    """Operational ranking result with immutable complexity-narrowing provenance."""

    narrowing: ComplexityNarrowingProvenance
    ranking: RankingDecision


class ComplexityAwareRankingService:
    """Rank only the non-empty subset already retained by complexity narrowing."""

    def __init__(self, ranking: OperationalRankingService | None = None) -> None:
        """Bind the existing non-authoritative operational ranking implementation."""
        self._ranking = ranking or OperationalRankingService()

    def rank(
        self,
        request: GatewayRequest,
        effective_context: EffectivePolicyContext,
        registry: ModelRegistry,
        eligible: ComplexityEligibleCandidateSet,
        policy_request: PolicyRequestMetadata,
        ranking_policy: RankingPolicy,
        runtime_health: Mapping[str, DeploymentHealthSnapshot] | None = None,
    ) -> ComplexityAwareRankingDecision:
        """Delegate ranking over the complexity subset and never broaden it."""
        if not eligible.candidates:
            raise ComplexityRankingError(
                "complexity-aware ranking requires at least one complexity-eligible candidate"
            )
        if ranking_policy.digest != eligible.provenance.ranking_policy_digest:
            raise ComplexityRankingError(
                "operational ranking policy does not match complexity-narrowing provenance"
            )

        narrowed_authorized = AuthorizedCandidateSet(
            policy=eligible.authorized.policy,
            registry_digest=eligible.authorized.registry_digest,
            candidates=eligible.candidates,
        )
        ranking = self._ranking.rank(
            request,
            effective_context,
            registry,
            narrowed_authorized,
            policy_request,
            ranking_policy,
            runtime_health,
        )
        _validate_ranking_subset(eligible, ranking)
        return ComplexityAwareRankingDecision(
            narrowing=eligible.provenance,
            ranking=ranking,
        )


def _validate_ranking_subset(
    eligible: ComplexityEligibleCandidateSet,
    ranking: RankingDecision,
) -> None:
    """Defend against any future ranking implementation accidentally widening candidates."""
    eligible_ids = frozenset(item.deployment_id for item in eligible.candidates)
    ranked_candidates = (
        () if ranking.selected is None else (ranking.selected,)
    ) + ranking.alternatives
    ranked_ids = frozenset(item.deployment.deployment_id for item in ranked_candidates)
    rejected_ids = frozenset(item.deployment for item in ranking.rejected_candidates)
    if not ranked_ids <= eligible_ids:
        raise ComplexityRankingError(
            "operational ranking selected or exposed an alternative outside complexity eligibility"
        )
    if not rejected_ids <= eligible_ids:
        raise ComplexityRankingError(
            "operational ranking rejected a candidate outside complexity eligibility"
        )
