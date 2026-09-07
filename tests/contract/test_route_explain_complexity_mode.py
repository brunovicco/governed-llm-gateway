"""HTTP contract tests for the opt-in CR-2e route explanation mode."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient
from governed_llm_gateway_api import (
    ComplexityRouteExplainCoordinator,
    RouteExplainCoordinator,
    create_app,
)
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
    ComplexityRouteExplainService,
    PolicyAuthorizationDecision,
    PolicyEnforcementService,
    PolicyProjectionDefaults,
    PolicyRequestMetadata,
)
from governed_llm_gateway_core.application.ranking import RouteExplainService
from governed_llm_gateway_core.domain import (
    ComplexityPolicy,
    ComplexityQualityPolicy,
    DeterministicComplexityEvaluator,
    ModelDeployment,
    ModelRegistry,
    PolicyAuthorization,
    PricingMetadata,
    RankingPolicy,
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

_REQUEST_ID = UUID("00000000-0000-0000-0000-000000000654")
_WORKLOAD = "demo.reasoning"
_TODAY = date(2026, 9, 7)
_TEST_CREDENTIAL = "gateway-secret-must-not-echo"
_PROVIDER_SENTINEL = "provider-internal-must-not-echo"


class RecordingPolicy:
    """Deterministic PDP fixture that records authorization ordering."""

    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def authorize(self, metadata: PolicyRequestMetadata) -> PolicyAuthorizationDecision:
        self._events.append("authorize")
        return PolicyAuthorizationDecision(
            authorization=PolicyAuthorization(
                decision_id="decision-654",
                authorized_model_groups=frozenset({"general"}),
            ),
            provenance=PolicyProvenance(
                decision_id="decision-654",
                policy_id="router",
                policy_version="v1",
                policy_digest="sha256:" + "1" * 64,
            ),
            decided_at=datetime(2026, 9, 7, tzinfo=UTC),
            reason="allowed",
            service_version="v1",
            environment=metadata.environment,
        )


class Resolver:
    async def resolve(
        self,
        *,
        api_key: str,
        request: GatewayRequest,
    ) -> EffectivePolicyContext:
        assert api_key == _TEST_CREDENTIAL
        return EffectivePolicyContext(
            client_id="client-654",
            environment="prod",
            workload=request.workload,
            risk_level=RiskLevel.HIGH,
            data_classification=DataClassification.INTERNAL,
        )


class RecordingEvaluator:
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


def _deployment(deployment_id: str) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider=_PROVIDER_SENTINEL,
        model_id=f"model-{deployment_id}",
        model_group="general",
        api_family="responses",
        capabilities=frozenset({Capability.TEXT}),
        context_tokens=128_000,
        modalities=frozenset({Modality.TEXT}),
        pricing=PricingMetadata(
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("2"),
            source_date=_TODAY,
            snapshot_version="pricing-v1",
        ),
        max_data_classification=DataClassification.INTERNAL,
        allowed_environments=frozenset({"prod"}),
        enabled=True,
        source_date=_TODAY,
        catalog_version="catalog-v1",
    )


def _registry() -> ModelRegistry:
    return ModelRegistry(
        schema_version="1.0",
        catalog_version="catalog-v1",
        source_date=_TODAY,
        deployments=(
            _deployment("deployment-high"),
            _deployment("deployment-low"),
        ),
    )


def _workload_policy() -> WorkloadRankingPolicy:
    return WorkloadRankingPolicy(
        workload=_WORKLOAD,
        weights=RankingWeights(
            quality=Decimal("1"),
            reliability=Decimal("0"),
            latency=Decimal("0"),
            cost=Decimal("0"),
            availability=Decimal("0"),
        ),
        deployments=(
            _score("deployment-high", "0.95"),
            _score("deployment-low", "0.60"),
        ),
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


def _operational_ranking_policy() -> RankingPolicy:
    return RankingPolicy(
        schema_version="1.0",
        policy_version="ranking-v1",
        score_snapshot_id="static-v1",
        source_date=_TODAY,
        workloads=(_workload_policy(),),
    )


def _evidence_ranking_policy(
    *,
    mode: ScoreProvenanceMode = ScoreProvenanceMode.BENCHMARK_HYBRID,
) -> EvidenceDrivenRankingPolicy:
    return EvidenceDrivenRankingPolicy(
        schema_version="1.1",
        policy_version="ranking-v1",
        score_snapshot_id="benchmark-v1",
        source_date=_TODAY,
        workloads=(_workload_policy(),),
        score_provenance_mode=mode,
        benchmark_snapshot_id="sha256:" + "a" * 64,
        promotion_evidence_id="sha256:" + "b" * 64,
        manual_override_id=("sha256:" + "c" * 64 if mode is ScoreProvenanceMode.MANUAL_OVERRIDE else None),
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
    return RecordingEvaluator(events, DeterministicComplexityEvaluator(policy))


def _quality_policy() -> ComplexityQualityPolicy:
    return ComplexityQualityPolicy(
        policy_id="complexity-quality",
        version="v1",
        low_min_quality=Decimal("0.50"),
        medium_min_quality=Decimal("0.75"),
        high_min_quality=Decimal("0.90"),
    )


def _defaults() -> PolicyProjectionDefaults:
    return PolicyProjectionDefaults(
        max_latency_ms=5_000,
        max_cost_usd=Decimal("1"),
    )


def _client(
    events: list[str],
    *,
    configure_complexity: bool = True,
    complexity_policy: EvidenceDrivenRankingPolicy | None = None,
) -> TestClient:
    registry = _registry()
    operational = RouteExplainCoordinator(
        context_resolver=Resolver(),
        service=RouteExplainService(PolicyEnforcementService(RecordingPolicy(events))),
        registry=registry,
        ranking_policy=_operational_ranking_policy(),
        defaults=_defaults(),
    )
    complexity: ComplexityRouteExplainCoordinator | None = None
    if configure_complexity:
        complexity = ComplexityRouteExplainCoordinator(
            context_resolver=Resolver(),
            service=ComplexityRouteExplainService(
                policy_enforcement=PolicyEnforcementService(RecordingPolicy(events)),
                complexity_evaluator=_complexity_evaluator(events),
                quality_policy=_quality_policy(),
            ),
            registry=registry,
            ranking_policy=complexity_policy or _evidence_ranking_policy(),
            defaults=_defaults(),
        )
    return TestClient(create_app(operational, complexity_coordinator=complexity))


def _payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": str(_REQUEST_ID),
        "workload": _WORKLOAD,
        "risk_level": "low",
        "data_classification": "public",
        "requirements": {
            "tool_calling": False,
            "structured_output": False,
            "vision": False,
            "min_context_tokens": 0,
        },
        "limits": {
            "max_latency_ms": 5_000,
            "max_cost_usd": "1",
        },
        "agent_identity": "caller-spoofed",
        "context_tokens_estimated": 1_000,
        "max_output_tokens_estimated": 500,
    }


def _post(client: TestClient, *, mode: str | None = None):
    path = "/v1/route/explain" if mode is None else f"/v1/route/explain?mode={mode}"
    return client.post(
        path,
        json=_payload(),
        headers={"X-Gateway-API-Key": _TEST_CREDENTIAL},
    )


def test_default_mode_preserves_existing_response_shape_when_complexity_is_configured() -> None:
    events: list[str] = []
    response = _post(_client(events))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "request_id",
        "authorized_model_group",
        "selected_deployment",
        "policy",
        "model_registry_digest",
        "ranking",
    }
    assert "complexity" not in body
    assert events == ["authorize"]


def test_explicit_complexity_mode_returns_benchmark_grounded_metadata_only_evidence() -> None:
    events: list[str] = []
    response = _post(_client(events), mode="complexity")

    assert response.status_code == 200
    body = response.json()
    assert body["selected_deployment"] == "deployment-high"
    assert body["ranking"]["score_provenance_mode"] == "benchmark_hybrid"
    assert body["complexity"]["assessment"]["level"] == "high"
    assert body["complexity"]["narrowing"]["minimum_quality"] == "0.9"
    assert body["complexity"]["narrowing"]["eligible_deployments"] == ["deployment-high"]
    assert body["complexity"]["narrowing"]["excluded_deployments"] == ["deployment-low"]
    assert events == ["authorize", "assess"]

    serialized = response.text
    assert _TEST_CREDENTIAL not in serialized
    assert _PROVIDER_SENTINEL not in serialized
    assert "messages" not in serialized
    assert "prompt" not in serialized
    assert "completion" not in serialized
    assert "tool.arguments" not in serialized


def test_complexity_mode_fails_closed_when_not_configured() -> None:
    events: list[str] = []
    response = _post(_client(events, configure_complexity=False), mode="complexity")

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "complexity_routing_unavailable"}}
    assert events == []
    assert _TEST_CREDENTIAL not in response.text


def test_complexity_mode_rejects_manual_override_evidence_without_leaking_reason() -> None:
    events: list[str] = []
    manual = _evidence_ranking_policy(mode=ScoreProvenanceMode.MANUAL_OVERRIDE)
    response = _post(
        _client(events, complexity_policy=manual),
        mode="complexity",
    )

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "complexity_routing_unavailable"}}
    assert events == ["authorize", "assess"]
    assert "benchmark_hybrid" not in response.text
    assert manual.manual_override_id not in response.text
    assert _TEST_CREDENTIAL not in response.text


def test_unknown_route_explain_mode_is_rejected_at_http_boundary() -> None:
    events: list[str] = []
    response = _post(_client(events), mode="adaptive")

    assert response.status_code == 422
    assert events == []
