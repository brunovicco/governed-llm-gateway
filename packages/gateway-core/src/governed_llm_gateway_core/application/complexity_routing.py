"""Subset-only complexity narrowing over already-authorized model candidates."""

from dataclasses import dataclass
from decimal import Decimal

from governed_llm_gateway_contracts import ComplexityAssessment, TaskComplexity

from governed_llm_gateway_core.domain.complexity_quality import ComplexityQualityPolicy
from governed_llm_gateway_core.domain.evidence_ranking import (
    EvidenceDrivenRankingPolicy,
    ScoreProvenanceMode,
)
from governed_llm_gateway_core.domain.model_registry import ModelDeployment
from governed_llm_gateway_core.domain.ranking import RankingPolicy, RankingPolicyError

from .policy import AuthorizedCandidateSet


class ComplexityNarrowingError(ValueError):
    """Raised when benchmark-grounded complexity narrowing cannot fail closed safely."""


@dataclass(frozen=True, slots=True)
class ComplexityNarrowingProvenance:
    """Metadata-only evidence describing one complexity-based subset operation."""

    complexity_assessment_id: str
    complexity_level: TaskComplexity
    minimum_quality: str
    quality_policy_digest: str
    ranking_policy_digest: str
    benchmark_snapshot_id: str
    promotion_evidence_id: str
    excluded_deployments: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ComplexityEligibleCandidateSet:
    """Candidates retained after benchmark-grounded complexity quality narrowing."""

    authorized: AuthorizedCandidateSet
    candidates: tuple[ModelDeployment, ...]
    provenance: ComplexityNarrowingProvenance

    def __post_init__(self) -> None:
        """Defend the permanent subset invariant even for direct construction."""
        authorized_ids = frozenset(item.deployment_id for item in self.authorized.candidates)
        candidate_ids = tuple(item.deployment_id for item in self.candidates)
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ComplexityNarrowingError("complexity candidates must not contain duplicates")
        if not frozenset(candidate_ids) <= authorized_ids:
            raise ComplexityNarrowingError(
                "complexity candidates must be a subset of the authorized candidate set"
            )
        if candidate_ids != tuple(sorted(candidate_ids)):
            raise ComplexityNarrowingError("complexity candidates must be deterministically sorted")


def narrow_authorized_candidates_by_complexity(
    *,
    workload: str,
    authorized: AuthorizedCandidateSet,
    assessment: ComplexityAssessment,
    ranking_policy: RankingPolicy,
    quality_policy: ComplexityQualityPolicy,
) -> ComplexityEligibleCandidateSet:
    """Intersect authorized candidates with benchmark-derived quality for task complexity."""
    if not workload or workload.strip() != workload or "." not in workload:
        raise ComplexityNarrowingError("complexity narrowing workload must be normalized and dotted")
    if not isinstance(assessment, ComplexityAssessment):
        raise ComplexityNarrowingError("complexity narrowing requires ComplexityAssessment evidence")
    if not isinstance(ranking_policy, EvidenceDrivenRankingPolicy):
        raise ComplexityNarrowingError(
            "complexity narrowing requires evidence-driven ranking policy provenance"
        )
    if ranking_policy.score_provenance_mode is not ScoreProvenanceMode.BENCHMARK_HYBRID:
        raise ComplexityNarrowingError(
            "complexity narrowing requires benchmark_hybrid ranking quality provenance"
        )

    try:
        workload_policy = ranking_policy.for_workload(workload)
    except RankingPolicyError as exc:
        raise ComplexityNarrowingError(
            f"complexity narrowing has no ranking evidence for workload {workload!r}"
        ) from exc

    minimum_quality = quality_policy.minimum_for(assessment.level)
    retained: list[ModelDeployment] = []
    excluded: list[str] = []
    for deployment in sorted(authorized.candidates, key=lambda item: item.deployment_id):
        score = workload_policy.score_for(deployment.deployment_id)
        if score is None:
            raise ComplexityNarrowingError(
                "complexity narrowing is missing benchmark-derived quality for authorized "
                f"deployment {deployment.deployment_id!r}"
            )
        if score.quality >= minimum_quality:
            retained.append(deployment)
        else:
            excluded.append(deployment.deployment_id)

    return ComplexityEligibleCandidateSet(
        authorized=authorized,
        candidates=tuple(retained),
        provenance=ComplexityNarrowingProvenance(
            complexity_assessment_id=assessment.assessment_id,
            complexity_level=assessment.level,
            minimum_quality=_canonical_quality(minimum_quality),
            quality_policy_digest=quality_policy.digest,
            ranking_policy_digest=ranking_policy.digest,
            benchmark_snapshot_id=ranking_policy.benchmark_snapshot_id,
            promotion_evidence_id=ranking_policy.promotion_evidence_id,
            excluded_deployments=tuple(excluded),
        ),
    )


def _canonical_quality(value: Decimal) -> str:
    """Serialize the already-validated Decimal floor without leaking other policy data."""
    text = format(value, "f")
    if "." not in text:
        return text
    return text.rstrip("0").rstrip(".") or "0"
