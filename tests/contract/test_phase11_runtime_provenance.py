from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from governed_llm_gateway_contracts import (
    Capability,
    DataClassification,
    GatewayRequest,
    Modality,
    PolicyProvenance,
    RejectionReason,
    RequestLimits,
    RiskLevel,
    WorkloadRequirements,
)
from governed_llm_gateway_core.application.policy import (
    AuthorizedCandidateSet,
    PolicyAuthorizationDecision,
    PolicyRequestMetadata,
)
from governed_llm_gateway_core.application.ranking import (
    OperationalRankingService,
    RankingDecision,
)
from governed_llm_gateway_core.domain.authorization import PolicyAuthorization
from governed_llm_gateway_core.domain.evidence_ranking import (
    EvidenceDrivenRankingPolicy,
    ScoreProvenanceMode,
)
from governed_llm_gateway_core.domain.model_registry import (
    ModelDeployment,
    ModelRegistry,
    PricingMetadata,
)
from governed_llm_gateway_core.domain.ranking import (
    RankingPolicy,
    RankingWeights,
    StaticDeploymentScore,
    WorkloadRankingPolicy,
)
from governed_llm_gateway_core.domain.ranking_override import (
    ManualOverrideBundle,
    ManualScoreOverride,
    apply_manual_override,
)
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext

TODAY = date(2026, 9, 3)
REQUEST_ID = UUID("22222222-2222-4222-8222-222222222222")


def _deployment(deployment_id: str, *, enabled: bool = True) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider="provider-a",
        model_id=f"model/{deployment_id}",
        model_group="agentic-strong",
        api_family="openai-compatible",
        capabilities=frozenset({Capability.TEXT, Capability.TOOL_CALLING}),
        context_tokens=100_000,
        modalities=frozenset({Modality.TEXT}),
        pricing=PricingMetadata(
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("2"),
            source_date=TODAY,
            snapshot_version="pricing-v1",
        ),
        max_data_classification=DataClassification.INTERNAL,
        allowed_environments=frozenset({"development"}),
        enabled=enabled,
        source_date=TODAY,
        catalog_version="catalog-v1",
    )


def _registry(*deployments: ModelDeployment) -> ModelRegistry:
    return ModelRegistry(
        schema_version="1.0",
        catalog_version="catalog-v1",
        source_date=TODAY,
        deployments=tuple(sorted(deployments, key=lambda item: item.deployment_id)),
    )


def _score(deployment_id: str, value: str) -> StaticDeploymentScore:
    score = Decimal(value)
    return StaticDeploymentScore(
        deployment_id=deployment_id,
        quality=score,
        reliability=score,
        latency=score,
        cost=score,
        availability=score,
        expected_latency_ms=500,
    )


def _workload(*scores: StaticDeploymentScore) -> tuple[WorkloadRankingPolicy, ...]:
    return (
        WorkloadRankingPolicy(
            workload="agent.orchestration",
            weights=RankingWeights(
                quality=Decimal("0.4"),
                reliability=Decimal("0.2"),
                latency=Decimal("0.15"),
                cost=Decimal("0.15"),
                availability=Decimal("0.1"),
            ),
            deployments=tuple(sorted(scores, key=lambda item: item.deployment_id)),
        ),
    )


def _static_policy(*scores: StaticDeploymentScore) -> RankingPolicy:
    return RankingPolicy(
        schema_version="1.0",
        policy_version="ranking-static-v1",
        score_snapshot_id="static-v1",
        source_date=TODAY,
        workloads=_workload(*scores),
    )


def _evidence_policy(
    *scores: StaticDeploymentScore,
    benchmark_digest: str = "b",
) -> EvidenceDrivenRankingPolicy:
    return EvidenceDrivenRankingPolicy(
        schema_version="1.1",
        policy_version="ranking-benchmark-v1",
        score_snapshot_id="benchmark-hybrid-v1",
        source_date=TODAY,
        workloads=_workload(*scores),
        score_provenance_mode=ScoreProvenanceMode.BENCHMARK_HYBRID,
        benchmark_snapshot_id="sha256:" + benchmark_digest * 64,
        promotion_evidence_id="sha256:" + "c" * 64,
    )


def _override_policy(
    *scores: StaticDeploymentScore,
    reason: str = "incident mitigation",
) -> EvidenceDrivenRankingPolicy:
    baseline = _evidence_policy(*scores)
    target = scores[0].deployment_id
    bundle = ManualOverrideBundle(
        schema_version="1.0",
        override_version="override-v1",
        approval_date=TODAY,
        approved_by="platform-oncall",
        reason=reason,
        overrides=(
            ManualScoreOverride(
                workload="agent.orchestration",
                deployment_id=target,
                quality=scores[0].quality,
            ),
        ),
    )
    return apply_manual_override(
        baseline,
        bundle,
        policy_version="ranking-override-v1",
        score_snapshot_id="override-v1",
        source_date=TODAY,
    )


def _request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(tool_calling=True),
        limits=RequestLimits(max_latency_ms=10_000, max_cost_usd=Decimal("1")),
    )


def _context() -> EffectivePolicyContext:
    return EffectivePolicyContext(
        client_id="service-a",
        environment="development",
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
    )


def _policy_request() -> PolicyRequestMetadata:
    return PolicyRequestMetadata(
        request_id=REQUEST_ID,
        client_id="service-a",
        environment="development",
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        context_tokens_estimated=2_000,
        max_output_tokens_estimated=1_000,
        structured_output_required=False,
        max_latency_ms=10_000,
        max_cost_usd=Decimal("1"),
    )


def _authorized(
    registry: ModelRegistry,
    *,
    candidates: tuple[ModelDeployment, ...] | None = None,
) -> AuthorizedCandidateSet:
    authorization = PolicyAuthorization(
        decision_id="decision-phase11",
        authorized_model_groups=frozenset({"agentic-strong"}),
    )
    decision = PolicyAuthorizationDecision(
        authorization=authorization,
        provenance=PolicyProvenance(
            decision_id="decision-phase11",
            policy_id="gateway-policy",
            policy_version="1.0.0",
            policy_digest="sha256:" + "a" * 64,
        ),
        decided_at=datetime(2026, 9, 3, 12, tzinfo=UTC),
        reason="authorized",
        service_version="0.4.0",
        environment="development",
    )
    return AuthorizedCandidateSet(
        policy=decision,
        registry_digest=registry.digest,
        candidates=candidates if candidates is not None else registry.deployments,
    )


def _rank(
    registry: ModelRegistry,
    policy: RankingPolicy,
    *,
    candidates: tuple[ModelDeployment, ...] | None = None,
) -> RankingDecision:
    return OperationalRankingService().rank(
        _request(),
        _context(),
        registry,
        _authorized(registry, candidates=candidates),
        _policy_request(),
        policy,
    )


def test_static_policy_keeps_phase11_provenance_unset() -> None:
    deployment = _deployment("candidate-a")
    decision = _rank(_registry(deployment), _static_policy(_score("candidate-a", "0.8")))

    assert decision.routing.benchmark_snapshot_id is None
    assert decision.routing.score_provenance_mode is None
    assert decision.routing.manual_override_id is None


def test_evidence_policy_exposes_exact_approved_benchmark_snapshot() -> None:
    deployment = _deployment("candidate-a")
    decision = _rank(_registry(deployment), _evidence_policy(_score("candidate-a", "0.8")))

    assert decision.routing.benchmark_snapshot_id == "sha256:" + "b" * 64
    assert decision.routing.score_provenance_mode == "benchmark_hybrid"
    assert decision.routing.manual_override_id is None


def test_benchmark_snapshot_identity_changes_routing_decision_id() -> None:
    deployment = _deployment("candidate-a")
    registry = _registry(deployment)
    score = _score("candidate-a", "0.8")

    first = _rank(registry, _evidence_policy(score, benchmark_digest="b"))
    second = _rank(registry, _evidence_policy(score, benchmark_digest="d"))

    assert first.selected == second.selected
    assert first.routing.routing_decision_id != second.routing.routing_decision_id


def test_manual_override_exposes_attributable_runtime_provenance() -> None:
    deployment = _deployment("candidate-a")
    policy = _override_policy(_score("candidate-a", "0.8"))

    decision = _rank(_registry(deployment), policy)

    assert decision.routing.benchmark_snapshot_id == policy.benchmark_snapshot_id
    assert decision.routing.score_provenance_mode == "manual_override"
    assert decision.routing.manual_override_id == policy.manual_override_id


def test_manual_override_identity_changes_routing_decision_id() -> None:
    deployment = _deployment("candidate-a")
    registry = _registry(deployment)
    score = _score("candidate-a", "0.8")

    first = _rank(registry, _override_policy(score, reason="incident one"))
    second = _rank(registry, _override_policy(score, reason="incident two"))

    assert first.selected == second.selected
    assert first.selected is not None
    assert second.selected is not None
    assert first.selected.score == second.selected.score
    assert first.routing.manual_override_id != second.routing.manual_override_id
    assert first.routing.routing_decision_id != second.routing.routing_decision_id


def test_benchmark_policy_cannot_resurrect_candidate_outside_authorized_set() -> None:
    allowed = _deployment("allowed")
    excluded = _deployment("excluded")
    registry = _registry(allowed, excluded)
    policy = _evidence_policy(_score("allowed", "0.2"), _score("excluded", "1"))

    decision = _rank(registry, policy, candidates=(allowed,))

    assert decision.selected is not None
    assert decision.selected.deployment.deployment_id == "allowed"
    assert all(item.deployment.deployment_id != "excluded" for item in decision.alternatives)


def test_manual_override_cannot_resurrect_candidate_outside_authorized_set() -> None:
    allowed = _deployment("allowed")
    excluded = _deployment("excluded")
    registry = _registry(allowed, excluded)
    policy = _override_policy(_score("excluded", "1"), _score("allowed", "0.2"))

    decision = _rank(registry, policy, candidates=(allowed,))

    assert decision.selected is not None
    assert decision.selected.deployment.deployment_id == "allowed"
    assert all(item.deployment.deployment_id != "excluded" for item in decision.alternatives)


def test_benchmark_policy_cannot_override_disabled_eligibility() -> None:
    disabled = _deployment("disabled-best", enabled=False)
    allowed = _deployment("allowed")
    registry = _registry(disabled, allowed)
    policy = _evidence_policy(_score("disabled-best", "1"), _score("allowed", "0.2"))

    decision = _rank(registry, policy)

    assert decision.selected is not None
    assert decision.selected.deployment.deployment_id == "allowed"
    disabled_rejection = next(
        item for item in decision.rejected_candidates if item.deployment == "disabled-best"
    )
    assert disabled_rejection.reason is RejectionReason.DEPLOYMENT_DISABLED


def test_manual_override_cannot_override_disabled_eligibility() -> None:
    disabled = _deployment("disabled-best", enabled=False)
    allowed = _deployment("allowed")
    registry = _registry(disabled, allowed)
    policy = _override_policy(_score("disabled-best", "1"), _score("allowed", "0.2"))

    decision = _rank(registry, policy)

    assert decision.selected is not None
    assert decision.selected.deployment.deployment_id == "allowed"
    disabled_rejection = next(
        item for item in decision.rejected_candidates if item.deployment == "disabled-best"
    )
    assert disabled_rejection.reason is RejectionReason.DEPLOYMENT_DISABLED
