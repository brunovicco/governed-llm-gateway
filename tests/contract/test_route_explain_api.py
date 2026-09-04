from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient
from governed_llm_gateway_api.route_explain import (
    ClientAuthenticationError,
    RouteExplainCoordinator,
    create_app,
)
from governed_llm_gateway_contracts import (
    Capability,
    DataClassification,
    GatewayRequest,
    Modality,
    PolicyProvenance,
    RiskLevel,
)
from governed_llm_gateway_core.application import (
    PolicyAuthorizationDecision,
    PolicyEnforcementService,
    PolicyProjectionDefaults,
    PolicyRequestMetadata,
)
from governed_llm_gateway_core.application.ranking import RouteExplainService
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
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext

REQUEST_ID = UUID("22222222-2222-4222-8222-222222222222")
TODAY = date(2026, 8, 31)
TEST_CREDENTIAL = "unit-test-token"


class FakePolicy:
    def __init__(self) -> None:
        self.calls = 0

    async def authorize(self, request: PolicyRequestMetadata) -> PolicyAuthorizationDecision:
        self.calls += 1
        return PolicyAuthorizationDecision(
            authorization=PolicyAuthorization(
                decision_id="decision-api",
                authorized_model_groups=frozenset({"agentic-strong"}),
            ),
            provenance=PolicyProvenance(
                decision_id="decision-api",
                policy_id="gateway-policy",
                policy_version="1.0.0",
                policy_digest="sha256:" + "b" * 64,
            ),
            decided_at=datetime(2026, 8, 31, 12, tzinfo=UTC),
            reason="authorized",
            service_version="0.4.0",
            environment="development",
        )


class FakeResolver:
    async def resolve(self, *, api_key: str, request: GatewayRequest) -> EffectivePolicyContext:
        assert api_key == TEST_CREDENTIAL
        return EffectivePolicyContext(
            client_id="service-a",
            environment="development",
            workload=request.workload,
            risk_level=RiskLevel.HIGH,
            data_classification=DataClassification.INTERNAL,
        )


class RejectingResolver:
    async def resolve(self, *, api_key: str, request: GatewayRequest) -> EffectivePolicyContext:
        raise ClientAuthenticationError("credential rejected")


def _registry() -> ModelRegistry:
    deployment = ModelDeployment(
        deployment_id="candidate-a",
        provider="provider-a",
        model_id="model/a",
        model_group="agentic-strong",
        api_family="openai-compatible",
        capabilities=frozenset({Capability.TEXT, Capability.TOOL_CALLING}),
        context_tokens=128_000,
        modalities=frozenset({Modality.TEXT}),
        pricing=PricingMetadata(
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("2"),
            source_date=TODAY,
            snapshot_version="pricing-v1",
        ),
        max_data_classification=DataClassification.INTERNAL,
        allowed_environments=frozenset({"development"}),
        enabled=True,
        source_date=TODAY,
        catalog_version="catalog-v1",
    )
    return ModelRegistry(
        schema_version="1.0",
        catalog_version="catalog-v1",
        source_date=TODAY,
        deployments=(deployment,),
    )


def _ranking_policy() -> RankingPolicy:
    return RankingPolicy(
        schema_version="1.0",
        policy_version="ranking-v1",
        score_snapshot_id="static-v1",
        source_date=TODAY,
        workloads=(
            WorkloadRankingPolicy(
                workload="agent.orchestration",
                weights=RankingWeights(
                    quality=Decimal("0.4"),
                    reliability=Decimal("0.2"),
                    latency=Decimal("0.15"),
                    cost=Decimal("0.15"),
                    availability=Decimal("0.1"),
                ),
                deployments=(
                    StaticDeploymentScore(
                        deployment_id="candidate-a",
                        quality=Decimal("0.9"),
                        reliability=Decimal("0.9"),
                        latency=Decimal("0.9"),
                        cost=Decimal("0.9"),
                        availability=Decimal("0.9"),
                        expected_latency_ms=1000,
                    ),
                ),
            ),
        ),
    )


def _client(
    resolver: FakeResolver | RejectingResolver,
    ranking_policy: RankingPolicy | None = None,
) -> TestClient:
    policy = FakePolicy()
    coordinator = RouteExplainCoordinator(
        context_resolver=resolver,
        service=RouteExplainService(PolicyEnforcementService(policy)),
        registry=_registry(),
        ranking_policy=ranking_policy or _ranking_policy(),
        defaults=PolicyProjectionDefaults(
            max_latency_ms=10_000,
            max_cost_usd=Decimal("1"),
        ),
    )
    return TestClient(create_app(coordinator))


def _evidence_ranking_policy() -> EvidenceDrivenRankingPolicy:
    base = _ranking_policy()
    return EvidenceDrivenRankingPolicy(
        schema_version="1.1",
        policy_version="ranking-benchmark-v1",
        score_snapshot_id="benchmark-hybrid-v1",
        source_date=TODAY,
        workloads=base.workloads,
        score_provenance_mode=ScoreProvenanceMode.MANUAL_OVERRIDE,
        benchmark_snapshot_id="sha256:" + "c" * 64,
        promotion_evidence_id="sha256:" + "d" * 64,
        manual_override_id="sha256:" + "e" * 64,
    )


def _payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": str(REQUEST_ID),
        "workload": "agent.orchestration",
        "risk_level": "low",
        "data_classification": "public",
        "requirements": {
            "tool_calling": True,
            "structured_output": False,
            "vision": False,
            "min_context_tokens": 0,
        },
        "limits": {
            "max_latency_ms": 5000,
            "max_cost_usd": "0.50",
        },
        "agent_identity": "caller-spoofed",
        "context_tokens_estimated": 1000,
        "max_output_tokens_estimated": 500,
    }


def test_route_explain_returns_deterministic_metadata_without_messages() -> None:
    client = _client(FakeResolver())

    first = client.post(
        "/v1/route/explain",
        json=_payload(),
        headers={"X-Gateway-API-Key": TEST_CREDENTIAL},
    )
    second = client.post(
        "/v1/route/explain",
        json=_payload(),
        headers={"X-Gateway-API-Key": TEST_CREDENTIAL},
    )

    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json()["selected_deployment"] == "candidate-a"
    assert first.json()["authorized_model_group"] == "agentic-strong"
    assert first.json()["ranking"]["decision_id"].startswith("sha256:")
    assert first.json()["ranking"]["benchmark_snapshot_id"] is None
    assert first.json()["ranking"]["score_provenance_mode"] is None
    assert first.json()["ranking"]["manual_override_id"] is None
    assert "messages" not in first.json()


def test_route_explain_rejects_prompt_field_at_http_boundary() -> None:
    client = _client(FakeResolver())
    payload = _payload()
    payload["messages"] = [{"role": "user", "content": "test prompt"}]

    response = client.post(
        "/v1/route/explain",
        json=payload,
        headers={"X-Gateway-API-Key": TEST_CREDENTIAL},
    )

    assert response.status_code == 422


def test_route_explain_authentication_error_never_echoes_credential() -> None:
    client = _client(RejectingResolver())

    response = client.post(
        "/v1/route/explain",
        json=_payload(),
        headers={"X-Gateway-API-Key": TEST_CREDENTIAL},
    )

    assert response.status_code == 401
    assert TEST_CREDENTIAL not in response.text
    assert response.json()["detail"]["code"] == "invalid_gateway_credential"


def test_route_explain_rejects_unknown_schema_version_at_http_boundary() -> None:
    client = _client(FakeResolver())
    payload = _payload()
    payload["schema_version"] = "2.0"

    response = client.post(
        "/v1/route/explain",
        json=payload,
        headers={"X-Gateway-API-Key": TEST_CREDENTIAL},
    )

    assert response.status_code == 422


def test_route_explain_rejects_non_dotted_workload_at_http_boundary() -> None:
    client = _client(FakeResolver())
    payload = _payload()
    payload["workload"] = "orchestration"

    response = client.post(
        "/v1/route/explain",
        json=payload,
        headers={"X-Gateway-API-Key": TEST_CREDENTIAL},
    )

    assert response.status_code == 422


def test_route_explain_exposes_phase11_reconstruction_provenance() -> None:
    policy = _evidence_ranking_policy()
    client = _client(FakeResolver(), policy)

    response = client.post(
        "/v1/route/explain",
        json=_payload(),
        headers={"X-Gateway-API-Key": TEST_CREDENTIAL},
    )

    assert response.status_code == 200
    ranking = response.json()["ranking"]
    assert ranking["benchmark_snapshot_id"] == policy.benchmark_snapshot_id
    assert ranking["score_provenance_mode"] == "manual_override"
    assert ranking["manual_override_id"] == policy.manual_override_id
