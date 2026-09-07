"""Metadata-only HTTP representation for complexity-aware route evidence."""

from governed_llm_gateway_contracts import TaskComplexity
from governed_llm_gateway_core.application import ComplexityRouteExplainDecision
from governed_llm_gateway_core.domain.evidence_ranking import ScoreProvenanceMode
from pydantic import BaseModel, ConfigDict


class ComplexityHttpEvidenceInvariantViolation(ValueError):
    """Raised when composite complexity evidence is inconsistent before serialization."""


class ComplexityAssessmentExplainModel(BaseModel):
    """Provider-neutral task-complexity assessment provenance for HTTP responses."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    level: TaskComplexity
    assessment_id: str
    evaluator_id: str
    evaluator_version: str


class ComplexityNarrowingExplainModel(BaseModel):
    """Benchmark-grounded narrowing provenance for HTTP responses."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_quality: str
    quality_policy_digest: str
    ranking_policy_digest: str
    benchmark_snapshot_id: str
    promotion_evidence_id: str
    eligible_deployments: tuple[str, ...]
    excluded_deployments: tuple[str, ...]


class ComplexityExplainModel(BaseModel):
    """Bounded metadata-only complexity evidence subdocument."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    assessment: ComplexityAssessmentExplainModel
    narrowing: ComplexityNarrowingExplainModel


def complexity_evidence_from_decision(
    decision: ComplexityRouteExplainDecision,
) -> ComplexityExplainModel:
    """Validate and serialize one composite CR-2c decision without content-bearing data."""
    _validate_consistency(decision)
    assessment = decision.assessment
    narrowing = decision.narrowing
    return ComplexityExplainModel(
        assessment=ComplexityAssessmentExplainModel(
            level=assessment.level,
            assessment_id=assessment.assessment_id,
            evaluator_id=assessment.evaluator_id,
            evaluator_version=assessment.evaluator_version,
        ),
        narrowing=ComplexityNarrowingExplainModel(
            minimum_quality=narrowing.minimum_quality,
            quality_policy_digest=narrowing.quality_policy_digest,
            ranking_policy_digest=narrowing.ranking_policy_digest,
            benchmark_snapshot_id=narrowing.benchmark_snapshot_id,
            promotion_evidence_id=narrowing.promotion_evidence_id,
            eligible_deployments=decision.complexity_eligible_deployments,
            excluded_deployments=narrowing.excluded_deployments,
        ),
    )


def _validate_consistency(decision: ComplexityRouteExplainDecision) -> None:
    assessment = decision.assessment
    narrowing = decision.narrowing
    ranking = decision.ranking

    if narrowing.complexity_assessment_id != assessment.assessment_id:
        raise ComplexityHttpEvidenceInvariantViolation(
            "complexity narrowing assessment ID does not match assessment provenance"
        )
    if narrowing.complexity_level is not assessment.level:
        raise ComplexityHttpEvidenceInvariantViolation(
            "complexity narrowing level does not match assessment provenance"
        )
    if narrowing.ranking_policy_digest != ranking.ranking_policy_digest:
        raise ComplexityHttpEvidenceInvariantViolation(
            "complexity narrowing ranking policy does not match ranking provenance"
        )
    if ranking.routing.ranking_policy_digest != narrowing.ranking_policy_digest:
        raise ComplexityHttpEvidenceInvariantViolation(
            "routing ranking policy does not match complexity narrowing provenance"
        )
    if ranking.routing.benchmark_snapshot_id != narrowing.benchmark_snapshot_id:
        raise ComplexityHttpEvidenceInvariantViolation(
            "routing benchmark snapshot does not match complexity narrowing provenance"
        )
    if ranking.routing.score_provenance_mode != ScoreProvenanceMode.BENCHMARK_HYBRID.value:
        raise ComplexityHttpEvidenceInvariantViolation(
            "complexity HTTP evidence requires benchmark_hybrid ranking provenance"
        )
    if ranking.routing.manual_override_id is not None:
        raise ComplexityHttpEvidenceInvariantViolation(
            "complexity HTTP evidence cannot represent manual-override ranking provenance"
        )

    eligible = decision.complexity_eligible_deployments
    excluded = narrowing.excluded_deployments
    _validate_deployment_ids(eligible, "eligible")
    _validate_deployment_ids(excluded, "excluded")
    if not frozenset(eligible).isdisjoint(excluded):
        raise ComplexityHttpEvidenceInvariantViolation(
            "complexity eligible and excluded deployments must be disjoint"
        )

    ranked_ids = {
        candidate.deployment.deployment_id
        for candidate in (
            *((ranking.selected,) if ranking.selected is not None else ()),
            *ranking.alternatives,
        )
    }
    rejected_ids = frozenset(item.deployment for item in ranking.rejected_candidates)
    eligible_ids = frozenset(eligible)
    if not ranked_ids <= eligible_ids:
        raise ComplexityHttpEvidenceInvariantViolation(
            "ranking selected or exposed an alternative outside complexity eligibility"
        )
    if not rejected_ids <= eligible_ids:
        raise ComplexityHttpEvidenceInvariantViolation(
            "ranking rejected a deployment outside complexity eligibility"
        )


def _validate_deployment_ids(deployments: tuple[str, ...], label: str) -> None:
    if deployments != tuple(sorted(deployments)):
        raise ComplexityHttpEvidenceInvariantViolation(
            f"complexity {label} deployments must be deterministically sorted"
        )
    if len(deployments) != len(set(deployments)):
        raise ComplexityHttpEvidenceInvariantViolation(
            f"complexity {label} deployments must not contain duplicates"
        )
