"""Contract tests for opt-in complexity-aware streaming generation."""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from governed_llm_gateway_api import (
    ComplexityGenerateCoordinator,
    GenerateCoordinator,
    GenerateRequestModel,
    PreparedStreamingExecution,
    attach_generate_route,
)
from governed_llm_gateway_api.stream_generate import NoEligibleStreamingDeploymentError
from governed_llm_gateway_contracts import (
    Capability,
    ComplexityAssessment,
    DataClassification,
    GatewayRequest,
    GatewayStreamEvent,
    Modality,
    PolicyProvenance,
    RiskLevel,
    RoutingProvenance,
    StreamEventType,
)
from governed_llm_gateway_core.adapters import load_complexity_routing_document
from governed_llm_gateway_core.application import (
    ComplexityEvaluator,
    ComplexityRouteExplainService,
    InMemoryHealthTracker,
    PolicyAuthorizationDecision,
    PolicyEnforcementService,
    PolicyProjectionDefaults,
    PolicyRequestMetadata,
    RankingDecision,
)
from governed_llm_gateway_core.application.streaming import StreamingExecutionService
from governed_llm_gateway_core.domain import (
    CircuitState,
    DeploymentHealthSnapshot,
    HealthStatus,
    ModelDeployment,
    ModelRegistry,
    PolicyAuthorization,
    PricingMetadata,
    RankingWeights,
    StaticDeploymentScore,
    WorkloadRankingPolicy,
)
from governed_llm_gateway_core.domain.complexity import DeterministicComplexityEvaluator
from governed_llm_gateway_core.domain.evidence_ranking import (
    EvidenceDrivenRankingPolicy,
    ScoreProvenanceMode,
)
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext

_REQUEST_ID = UUID("00000000-0000-4000-8000-000000000774")
_WORKLOAD = "demo.reasoning"
_TODAY = date(2026, 9, 7)
_API_KEY = "gateway-test-key"


class RecordingPolicy:
    """Deterministic PDP fixture that records the authorization boundary."""

    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def authorize(self, metadata: PolicyRequestMetadata) -> PolicyAuthorizationDecision:
        self._events.append("authorize")
        return PolicyAuthorizationDecision(
            authorization=PolicyAuthorization(
                decision_id="decision-774",
                authorized_model_groups=frozenset({"general"}),
            ),
            provenance=PolicyProvenance(
                decision_id="decision-774",
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
        assert api_key == _API_KEY
        return EffectivePolicyContext(
            client_id="client-774",
            environment="prod",
            workload=request.workload,
            risk_level=RiskLevel.HIGH,
            data_classification=DataClassification.INTERNAL,
        )


class RecordingEvaluator:
    """Record assessment ordering while delegating the CR-1 evaluator."""

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


class FixedHealth:
    """Health fixture used to prove complexity exclusions cannot be resurrected."""

    def __init__(self, *, high_unhealthy: bool = False) -> None:
        self._high_unhealthy = high_unhealthy

    def snapshots(self, deployment_ids: tuple[str, ...]) -> dict[str, DeploymentHealthSnapshot]:
        result: dict[str, DeploymentHealthSnapshot] = {}
        for deployment_id in deployment_ids:
            if deployment_id == "deployment-high" and self._high_unhealthy:
                result[deployment_id] = DeploymentHealthSnapshot(
                    deployment_id=deployment_id,
                    status=HealthStatus.UNHEALTHY,
                    circuit_state=CircuitState.OPEN,
                )
            else:
                result[deployment_id] = DeploymentHealthSnapshot(
                    deployment_id=deployment_id,
                    status=HealthStatus.HEALTHY,
                    circuit_state=CircuitState.CLOSED,
                )
        return result


class FakeHttpCoordinator:
    """Small API-dispatch fixture with deterministic deployment provenance."""

    def __init__(self, deployment: str) -> None:
        self.deployment = deployment
        self.prepare_calls = 0
        self.stream_calls = 0

    async def prepare(
        self,
        *,
        api_key: str,
        payload: GenerateRequestModel,
    ) -> PreparedStreamingExecution:
        assert api_key == _API_KEY
        self.prepare_calls += 1
        return PreparedStreamingExecution(
            request=payload.to_gateway_request(),
            decision=cast(RankingDecision, object()),
            max_output_tokens=payload.max_output_tokens,
            provider_timeout_seconds=payload.provider_timeout_seconds,
        )

    async def stream(
        self,
        prepared: PreparedStreamingExecution,
    ) -> AsyncGenerator[GatewayStreamEvent]:
        self.stream_calls += 1
        routing = _routing(self.deployment)
        yield GatewayStreamEvent(
            event_type=StreamEventType.RESPONSE_STARTED,
            request_id=prepared.request.request_id,
            sequence_number=1,
            routing=routing,
        )
        yield GatewayStreamEvent(
            event_type=StreamEventType.RESPONSE_COMPLETED,
            request_id=prepared.request.request_id,
            sequence_number=2,
            routing=routing,
            finish_reason="stop",
        )


def _routing(deployment: str) -> RoutingProvenance:
    return RoutingProvenance(
        routing_decision_id="sha256:" + "2" * 64,
        policy=PolicyProvenance(
            decision_id="decision-http",
            policy_id="router",
            policy_version="v1",
            policy_digest="sha256:" + "3" * 64,
        ),
        authorized_model_group="general",
        model_registry_digest="4" * 64,
        ranking_policy_version="ranking-v1",
        ranking_policy_digest="5" * 64,
        score_snapshot_id="benchmark-v1",
        benchmark_snapshot_id="sha256:" + "6" * 64,
        score_provenance_mode="benchmark_hybrid",
        provider="provider-test",
        model=f"model-{deployment}",
        deployment=deployment,
    )


def _deployment(deployment_id: str) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider="provider-test",
        model_id=f"model-{deployment_id}",
        model_group="general",
        api_family="responses",
        capabilities=frozenset({Capability.TEXT, Capability.STREAMING}),
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


def _ranking_policy() -> EvidenceDrivenRankingPolicy:
    workload = WorkloadRankingPolicy(
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
    return EvidenceDrivenRankingPolicy(
        schema_version="1.1",
        policy_version="ranking-v1",
        score_snapshot_id="benchmark-v1",
        source_date=_TODAY,
        workloads=(workload,),
        score_provenance_mode=ScoreProvenanceMode.BENCHMARK_HYBRID,
        benchmark_snapshot_id="sha256:" + "a" * 64,
        promotion_evidence_id="sha256:" + "b" * 64,
    )


def _payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": str(_REQUEST_ID),
        "workload": _WORKLOAD,
        "risk_level": "low",
        "data_classification": "public",
        "messages": [{"role": "user", "content": "reason about this task"}],
        "context_tokens_estimated": 40_000,
        "max_output_tokens": 500,
    }


def _complexity_coordinator(
    events: list[str],
    *,
    high_unhealthy: bool = False,
) -> ComplexityGenerateCoordinator:
    config = load_complexity_routing_document("config/routing/complexity.json")
    evaluator: ComplexityEvaluator = RecordingEvaluator(
        events,
        DeterministicComplexityEvaluator(config.assessment_policy),
    )
    route_service = ComplexityRouteExplainService(
        policy_enforcement=PolicyEnforcementService(RecordingPolicy(events)),
        complexity_evaluator=evaluator,
        quality_policy=config.quality_policy,
    )
    return ComplexityGenerateCoordinator(
        context_resolver=Resolver(),
        route_service=route_service,
        streaming_service=cast(StreamingExecutionService, object()),
        health=cast(InMemoryHealthTracker, FixedHealth(high_unhealthy=high_unhealthy)),
        registry=_registry(),
        ranking_policy=_ranking_policy(),
        defaults=PolicyProjectionDefaults(
            max_latency_ms=5_000,
            max_cost_usd=Decimal("1"),
        ),
    )


def _post(client: TestClient, *, mode: str | None = None) -> httpx.Response:
    path = "/v1/generate" if mode is None else f"/v1/generate?mode={mode}"
    return cast(
        httpx.Response,
        client.post(
            path,
            headers={"X-Gateway-API-Key": _API_KEY},
            json=_payload(),
        ),
    )


def test_generate_default_mode_preserves_operational_coordinator() -> None:
    operational = FakeHttpCoordinator("deployment-low")
    complexity = FakeHttpCoordinator("deployment-high")
    app = FastAPI()
    attach_generate_route(
        app,
        cast(GenerateCoordinator, operational),
        complexity_coordinator=cast(ComplexityGenerateCoordinator, complexity),
    )

    response = _post(TestClient(app))

    assert response.status_code == 200
    assert '"deployment":"deployment-low"' in response.text
    assert operational.prepare_calls == 1
    assert operational.stream_calls == 1
    assert complexity.prepare_calls == 0
    assert complexity.stream_calls == 0


def test_generate_complexity_mode_dispatches_to_complexity_coordinator() -> None:
    operational = FakeHttpCoordinator("deployment-low")
    complexity = FakeHttpCoordinator("deployment-high")
    app = FastAPI()
    attach_generate_route(
        app,
        cast(GenerateCoordinator, operational),
        complexity_coordinator=cast(ComplexityGenerateCoordinator, complexity),
    )

    response = _post(TestClient(app), mode="complexity")

    assert response.status_code == 200
    assert '"deployment":"deployment-high"' in response.text
    assert operational.prepare_calls == 0
    assert operational.stream_calls == 0
    assert complexity.prepare_calls == 1
    assert complexity.stream_calls == 1


def test_generate_complexity_mode_fails_closed_when_unconfigured() -> None:
    operational = FakeHttpCoordinator("deployment-low")
    app = FastAPI()
    attach_generate_route(app, cast(GenerateCoordinator, operational))

    response = _post(TestClient(app), mode="complexity")

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "complexity_routing_unavailable"}}
    assert operational.prepare_calls == 0
    assert operational.stream_calls == 0


def test_complexity_generation_authorizes_before_assessment_and_selects_high_quality() -> None:
    events: list[str] = []
    coordinator = _complexity_coordinator(events)
    payload = GenerateRequestModel.model_validate(_payload())

    prepared = asyncio.run(coordinator.prepare(api_key=_API_KEY, payload=payload))

    assert events == ["authorize", "assess"]
    assert prepared.decision.selected is not None
    assert prepared.decision.selected.deployment.deployment_id == "deployment-high"
    assert (
        tuple(candidate.deployment.deployment_id for candidate in prepared.decision.alternatives)
        == ()
    )
    assert prepared.decision.routing.score_provenance_mode == "benchmark_hybrid"


def test_complexity_generation_never_resurrects_lower_quality_authorized_candidate() -> None:
    events: list[str] = []
    coordinator = _complexity_coordinator(events, high_unhealthy=True)
    payload = GenerateRequestModel.model_validate(_payload())

    with pytest.raises(NoEligibleStreamingDeploymentError):
        asyncio.run(coordinator.prepare(api_key=_API_KEY, payload=payload))

    assert events == ["authorize", "assess"]
