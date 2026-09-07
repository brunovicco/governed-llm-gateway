"""Contract tests for the metadata-only CR-2d HTTP complexity evidence adapter."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from governed_llm_gateway_api import (
    ComplexityHttpEvidenceInvariantViolation,
    complexity_evidence_from_decision,
)
from governed_llm_gateway_contracts import (
    Capability,
    ComplexityAssessment,
    DataClassification,
    Modality,
    PolicyProvenance,
    RoutingProvenance,
    TaskComplexity,
)
from governed_llm_gateway_core.application import (
    ComplexityNarrowingProvenance,
    ComplexityRouteExplainDecision,
    RankedCandidate,
    RankingDecision,
    ScoreBreakdown,
)
from governed_llm_gateway_core.domain import ModelDeployment, PricingMetadata


def _deployment() -> ModelDeployment:
    return ModelDeployment(
        deployment_id="deployment-a",
        provider="provider-neutral",
        model_id="model-a",
        model_group="general",
        api_family="responses",
        capabilities=frozenset({Capability.TEXT}),
        context_tokens=128_000,
        modalities=frozenset({Modality.TEXT}),
        pricing=PricingMetadata(
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("2"),
            source_date=date(2026, 9, 7),
            snapshot_version="pricing-v1",
        ),
        max_data_classification=DataClassification.INTERNAL,
        allowed_environments=frozenset({"prod"}),
        enabled=True,
        source_date=date(2026, 9, 7),
        catalog_version="catalog-v1",
    )


def _ranked_candidate() -> RankedCandidate:
    deployment = _deployment()
    return RankedCandidate(
        deployment=deployment,
        score=ScoreBreakdown(
            quality=Decimal("0.95"),
            reliability=Decimal("0"),
            latency=Decimal("0"),
            cost=Decimal("0"),
            availability=Decimal("0"),
            total=Decimal("0.95"),
        ),
        estimated_cost_usd=Decimal("0.01"),
    )


def _decision() -> ComplexityRouteExplainDecision:
    ranking_digest = "a" * 64
    benchmark_id = "sha256:" + "b" * 64
    assessment = ComplexityAssessment(
        level=TaskComplexity.HIGH,
        assessment_id="assessment-1",
        evaluator_id="deterministic-complexity",
        evaluator_version="v1",
    )
    narrowing = ComplexityNarrowingProvenance(
        complexity_assessment_id=assessment.assessment_id,
        complexity_level=assessment.level,
        minimum_quality="0.9",
        quality_policy_digest="c" * 64,
        ranking_policy_digest=ranking_digest,
        benchmark_snapshot_id=benchmark_id,
        promotion_evidence_id="sha256:" + "d" * 64,
        excluded_deployments=("deployment-b",),
    )
    selected = _ranked_candidate()
    routing = RoutingProvenance(
        routing_decision_id="sha256:" + "e" * 64,
        policy=PolicyProvenance(
            decision_id="policy-decision",
            policy_id="gateway-policy",
            policy_version="v1",
            policy_digest="sha256:" + "f" * 64,
        ),
        authorized_model_group="general",
        model_registry_digest="1" * 64,
        ranking_policy_version="ranking-v1",
        ranking_policy_digest=ranking_digest,
        score_snapshot_id="benchmark-v1",
        benchmark_snapshot_id=benchmark_id,
        score_provenance_mode="benchmark_hybrid",
        manual_override_id=None,
        provider=selected.deployment.provider,
        model=selected.deployment.model_id,
        deployment=selected.deployment.deployment_id,
    )
    ranking = RankingDecision(
        routing=routing,
        ranking_policy_digest=ranking_digest,
        score_snapshot_id="benchmark-v1",
        selected=selected,
        alternatives=(),
        rejected_candidates=(),
    )
    return ComplexityRouteExplainDecision(
        assessment=assessment,
        narrowing=narrowing,
        complexity_eligible_deployments=(selected.deployment.deployment_id,),
        ranking=ranking,
    )


def test_complexity_http_evidence_is_deterministic_and_metadata_only() -> None:
    first = complexity_evidence_from_decision(_decision()).model_dump(mode="json")
    second = complexity_evidence_from_decision(_decision()).model_dump(mode="json")

    assert first == second
    assert first == {
        "assessment": {
            "level": "high",
            "assessment_id": "assessment-1",
            "evaluator_id": "deterministic-complexity",
            "evaluator_version": "v1",
        },
        "narrowing": {
            "minimum_quality": "0.9",
            "quality_policy_digest": "c" * 64,
            "ranking_policy_digest": "a" * 64,
            "benchmark_snapshot_id": "sha256:" + "b" * 64,
            "promotion_evidence_id": "sha256:" + "d" * 64,
            "eligible_deployments": ["deployment-a"],
            "excluded_deployments": ["deployment-b"],
        },
    }
    serialized = repr(first)
    for forbidden in (
        "prompt",
        "completion",
        "messages",
        "tool.arguments",
        "authorization",
        "api_key",
        "provider_payload",
    ):
        assert forbidden not in serialized


def test_complexity_http_evidence_rejects_assessment_provenance_drift() -> None:
    decision = _decision()
    inconsistent = replace(
        decision,
        narrowing=replace(
            decision.narrowing,
            complexity_assessment_id="assessment-other",
        ),
    )

    with pytest.raises(
        ComplexityHttpEvidenceInvariantViolation,
        match="assessment ID",
    ):
        complexity_evidence_from_decision(inconsistent)


def test_complexity_http_evidence_rejects_ranking_policy_drift() -> None:
    decision = _decision()
    inconsistent = replace(
        decision,
        ranking=replace(decision.ranking, ranking_policy_digest="9" * 64),
    )

    with pytest.raises(
        ComplexityHttpEvidenceInvariantViolation,
        match="ranking policy",
    ):
        complexity_evidence_from_decision(inconsistent)


def test_complexity_http_evidence_rejects_overlap_between_retained_and_excluded() -> None:
    decision = _decision()
    inconsistent = replace(
        decision,
        narrowing=replace(
            decision.narrowing,
            excluded_deployments=("deployment-a",),
        ),
    )

    with pytest.raises(
        ComplexityHttpEvidenceInvariantViolation,
        match="must be disjoint",
    ):
        complexity_evidence_from_decision(inconsistent)


def test_complexity_http_evidence_rejects_unsorted_deployment_ids() -> None:
    decision = _decision()
    inconsistent = replace(
        decision,
        complexity_eligible_deployments=("deployment-z", "deployment-a"),
    )

    with pytest.raises(
        ComplexityHttpEvidenceInvariantViolation,
        match="deterministically sorted",
    ):
        complexity_evidence_from_decision(inconsistent)


def test_complexity_http_evidence_rejects_ranked_candidate_outside_subset() -> None:
    decision = _decision()
    inconsistent = replace(
        decision,
        complexity_eligible_deployments=("deployment-other",),
    )

    with pytest.raises(
        ComplexityHttpEvidenceInvariantViolation,
        match="outside complexity eligibility",
    ):
        complexity_evidence_from_decision(inconsistent)
