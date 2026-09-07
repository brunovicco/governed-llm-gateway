"""Contract tests for end-to-end complexity-aware no-inference route explanation."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from governed_llm_gateway_contracts import (
    Capability,
    ComplexityAssessment,
    DataClassification,
    GatewayRequest,
    Modality,
    PolicyProvenance,
    RiskLevel,
    TaskComplexity,
)
from governed_llm_gateway_core.application import (
    ComplexityEvaluator,
    ComplexityNarrowingError,
    ComplexityRankingError,
    ComplexityRouteExplainService,
    PolicyAuthorizationDecision,
    PolicyDecisionError,
    PolicyDecisionErrorCode,
    PolicyEnforcementService,
    PolicyProjectionDefaults,
    PolicyRequestMetadata,
)
from governed_llm_gateway_core.domain import (
    ComplexityPolicy,
    ComplexityQualityPolicy,
    DeterministicComplexityEvaluator,
    ModelDeployment,
    ModelRegistry,
    PolicyAuthorization,
    PricingMetadata,
    RankingWeights,
    StaticDeploymentScore,
    WorkloadComplexityFloor,
    WorkloadRankingPolicy,
)
from governed_llm_gateway_core.domain.evidence_ranking import (
    EvidenceDrivenRankingPolicy,
    ScoreProvenanceMode,
)
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext

_WORKLOAD = "demo.reasoning"
_REQUEST_ID = UUID("00000000-0000-0000-0000-000000000321")


class RecordingPolicyPort:
    """Deterministic PDP fixture that records authorization ordering."""

    def __init__(self, events: list[str], *, reject: bool = False) -> None:
        self._events = events
        self._reject = reject

    async def authorize(self, metadata: PolicyRequestMetadata) -> PolicyAuthorizationDecision:
        self._events.append("authorize")
        if self._reject:
            raise PolicyDecisionError(
                code=PolicyDecisionErrorCode.AUTHORIZATION,
                message="policy rejected request",
                retryable=False,
            )
        return PolicyAuthorizationDecision(
            authorization=PolicyAuthorization(
                decision_id="decision-321",
                authorized_model_groups=frozenset({"general"}),
            ),
            provenance=PolicyProvenance(
                decision_id="decision-321",
                policy_id="router",
                policy_version="v1",
                policy_digest="sha256:" + "1" * 64,
            ),
            decided_at=datetime(2026, 9, 7, tzinfo=UTC),
            reason="allowed",
            service_version="v1",
            environment=metadata.environment,
        )


class RecordingComplexityEvaluator:
    """Record assessment ordering while delegating deterministic CR-1 behavior."""

    def __init__(
        self,
        events: list[str],
        delegate: DeterministicComplexityEvaluator,
    ) -> None:
        self._events = events
        self._delegate = delegate

    def assess(
        self,
        request: GatewayRequest,
        *,
        context_tokens_estimated: int,
        max_output_tokens_estimated: int,
    ) -> ComplexityAssessment:
        self._events.append("assess")
        return self._delegate.assess(
            request,
            context_tokens_estimated=context_tokens_estimated,
            max_output_tokens_estimated=max_output_tokens_estimated,
        )


def _deployment(
    deployment_id: str,
    *,
    model_group: str = "general",
) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider="provider-neutral",
        model_id=f"model-{deployment_id}",
        model_group=model_group,
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


def _registry(*deployments: ModelDeployment) -> ModelRegistry:
    return ModelRegistry(
        schema_version="1.0",
        catalog_version="catalog-v1",
        source_date=date(2026, 9, 7),
        deployments=tuple(sorted(deployments, key=lambda item: item.deployment_id)),
    )


def _ranking_policy(*scores: StaticDeploymentScore) -> EvidenceDrivenRankingPolicy:
    workload = WorkloadRankingPolicy(
        workload=_WORKLOAD,
        weights=RankingWeights(
            quality=Decimal("1"),
            reliability=Decimal("0"),
            latency=Decimal("0"),
            cost=Decimal("0"),
            availability=Decimal("0"),
        ),
        deployments=tuple(sorted(scores, key=lambda item: item.deployment_id)),
    )
    return EvidenceDrivenRankingPolicy(
        schema_version="1.1",
        policy_version="ranking-v1",
        score_snapshot_id="snapshot-v1",
        source_date=date(2026, 9, 7),
        workloads=(workload,),
        score_provenance_mode=ScoreProvenanceMode.BENCHMARK_HYBRID,
        benchmark_snapshot_id="sha256:" + "a" * 64,
        promotion_evidence_id="sha256:" + "b" * 64,
    )


def _score(deployment_id: str, quality: str) -> StaticDeploymentScore:
    return StaticDeploymentScore(
        deployment_id=deployment_id,
        quality=Decimal(quality),
        reliability=Decimal("1"),
        latency=Decimal("1"),
        cost=Decimal("1"),
        availability=Decimal("1"),
        expected_latency_ms=100,
    )


def _complexity_evaluator(events: list[str]) -> ComplexityEvaluator:
    policy = ComplexityPolicy(
        policy_id="deterministic-complexity",
        version="v1",
        medium_context_tokens=8_000,
        high_context_tokens=32_000,
        medium_output_tokens=2_000,
        high_output_tokens=8_000,
        tool_calling_floor=TaskComplexity.MEDIUM,
        structured_output_floor=TaskComplexity.MEDIUM,
        vision_floor=TaskComplexity.HIGH,
        workload_floors=(
            WorkloadComplexityFloor(
                workload=_WORKLOAD,
                minimum=TaskComplexity.HIGH,
            ),
        ),
    )
    return RecordingComplexityEvaluator(events, DeterministicComplexityEvaluator(policy))


def _quality_policy() -> ComplexityQualityPolicy:
    return ComplexityQualityPolicy(
        policy_id="complexity-quality",
        version="v1",
        low_min_quality=Decimal("0.50"),
        medium_min_quality=Decimal("0.75"),
        high_min_quality=Decimal("0.90"),
    )


def _service(events: list[str], *, reject: bool = False) -> ComplexityRouteExplainService:
    return ComplexityRouteExplainService(
        policy_enforcement=PolicyEnforcementService(
            RecordingPolicyPort(events, reject=reject)
        ),
        complexity_evaluator=_complexity_evaluator(events),
        quality_policy=_quality_policy(),
    )


def _request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=_REQUEST_ID,
        workload=_WORKLOAD,
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.INTERNAL,
    )


def _effective_context() -> EffectivePolicyContext:
    return EffectivePolicyContext(
        client_id="client-1",
        environment="prod",
        workload=_WORKLOAD,
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.INTERNAL,
    )


def _defaults() -> PolicyProjectionDefaults:
    return PolicyProjectionDefaults(
        max_latency_ms=5_000,
        max_cost_usd=Decimal("1"),
    )


@pytest.mark.asyncio
async def test_authorization_precedes_complexity_and_unauthorized_model_never_resurrects() -> None:
    events: list[str] = []
    low = _deployment("deployment-low")
    high = _deployment("deployment-high")
    forbidden = _deployment("deployment-forbidden", model_group="forbidden")
    registry = _registry(low, high, forbidden)
    ranking_policy = _ranking_policy(
        _score(low.deployment_id, "0.60"),
        _score(high.deployment_id, "0.95"),
        _score(forbidden.deployment_id, "1.00"),
    )

    result = await _service(events).explain(
        _request(),
        _effective_context(),
        registry,
        ranking_policy,
        context_tokens_estimated=1_000,
        max_output_tokens_estimated=500,
        defaults=_defaults(),
    )

    assert events == ["authorize", "assess"]
    assert result.assessment.level is TaskComplexity.HIGH
    assert result.complexity_eligible_deployments == (high.deployment_id,)
    assert result.ranking.selected is not None
    assert result.ranking.selected.deployment.deployment_id == high.deployment_id
    assert forbidden.deployment_id not in result.complexity_eligible_deployments
    assert forbidden.deployment_id not in result.narrowing.excluded_deployments


@pytest.mark.asyncio
async def test_policy_rejection_stops_before_complexity_assessment() -> None:
    events: list[str] = []
    deployment = _deployment("deployment-one")

    with pytest.raises(PolicyDecisionError, match="policy rejected request"):
        await _service(events, reject=True).explain(
            _request(),
            _effective_context(),
            _registry(deployment),
            _ranking_policy(_score(deployment.deployment_id, "0.95")),
            context_tokens_estimated=1_000,
            max_output_tokens_estimated=500,
            defaults=_defaults(),
        )

    assert events == ["authorize"]


@pytest.mark.asyncio
async def test_empty_complexity_subset_fails_closed_without_authorized_fallback() -> None:
    events: list[str] = []
    low = _deployment("deployment-low")

    with pytest.raises(ComplexityRankingError, match="at least one complexity-eligible"):
        await _service(events).explain(
            _request(),
            _effective_context(),
            _registry(low),
            _ranking_policy(_score(low.deployment_id, "0.60")),
            context_tokens_estimated=1_000,
            max_output_tokens_estimated=500,
            defaults=_defaults(),
        )

    assert events == ["authorize", "assess"]


@pytest.mark.asyncio
async def test_missing_benchmark_quality_fails_closed_after_authorization() -> None:
    events: list[str] = []
    deployment = _deployment("deployment-missing")

    with pytest.raises(ComplexityNarrowingError, match="missing benchmark-derived quality"):
        await _service(events).explain(
            _request(),
            _effective_context(),
            _registry(deployment),
            _ranking_policy(),
            context_tokens_estimated=1_000,
            max_output_tokens_estimated=500,
            defaults=_defaults(),
        )

    assert events == ["authorize", "assess"]


@pytest.mark.asyncio
async def test_identical_inputs_produce_identical_composite_evidence() -> None:
    deployment = _deployment("deployment-high")
    registry = _registry(deployment)
    ranking_policy = _ranking_policy(_score(deployment.deployment_id, "0.95"))

    first_events: list[str] = []
    second_events: list[str] = []
    first = await _service(first_events).explain(
        _request(),
        _effective_context(),
        registry,
        ranking_policy,
        context_tokens_estimated=1_000,
        max_output_tokens_estimated=500,
        defaults=_defaults(),
    )
    second = await _service(second_events).explain(
        _request(),
        _effective_context(),
        registry,
        ranking_policy,
        context_tokens_estimated=1_000,
        max_output_tokens_estimated=500,
        defaults=_defaults(),
    )

    assert first == second
    assert first_events == second_events == ["authorize", "assess"]
    assert first.narrowing.ranking_policy_digest == ranking_policy.digest
    assert first.ranking.routing.policy.decision_id == "decision-321"
    assert first.ranking.routing.model_registry_digest == registry.digest
