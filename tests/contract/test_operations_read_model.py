"""Contract tests for the typed read-only operations projection."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from governed_llm_gateway_contracts import Capability, DataClassification, Modality
from governed_llm_gateway_core.application.operations_read_model import (
    InMemoryHealthInspectionAdapter,
    OperationalEvidenceAvailable,
    OperationalEvidenceNotSupplied,
    OperationalEvidenceState,
    OperationsHealthScope,
    OperationsReadModelService,
)
from governed_llm_gateway_core.application.provider import ProviderError, ProviderErrorCode
from governed_llm_gateway_core.application.resilience import InMemoryHealthTracker
from governed_llm_gateway_core.domain.evidence_ranking import (
    EvidenceDrivenRankingPolicy,
    ScoreProvenanceMode,
)
from governed_llm_gateway_core.domain.model_registry import ModelDeployment, ModelRegistry
from governed_llm_gateway_core.domain.operational_evidence import (
    OperationalEvidenceRecord,
    create_operational_evidence_snapshot,
)
from governed_llm_gateway_core.domain.ranking import (
    RankingPolicy,
    RankingWeights,
    StaticDeploymentScore,
    WorkloadRankingPolicy,
)
from governed_llm_gateway_core.domain.resilience import (
    CircuitBreakerPolicy,
    CircuitState,
    HealthStatus,
)

_SOURCE_DATE = date(2026, 9, 8)


class FakeClock:
    """Controllable monotonic clock for circuit-view tests."""

    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _deployment(deployment_id: str, provider: str) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider=provider,
        model_id=f"model/{deployment_id}",
        model_group="agentic-strong",
        api_family="openai-compatible",
        capabilities=frozenset({Capability.TEXT}),
        context_tokens=128_000,
        modalities=frozenset({Modality.TEXT}),
        pricing=None,
        max_data_classification=DataClassification.INTERNAL,
        allowed_environments=frozenset({"development"}),
        enabled=True,
        source_date=_SOURCE_DATE,
        catalog_version="catalog-v1",
    )


def _registry() -> ModelRegistry:
    return ModelRegistry(
        schema_version="1.0",
        catalog_version="catalog-v1",
        source_date=_SOURCE_DATE,
        deployments=(
            _deployment("deployment-b", "provider-b"),
            _deployment("deployment-a", "provider-a"),
        ),
    )


def _weights() -> RankingWeights:
    return RankingWeights(
        quality=Decimal("0.4"),
        reliability=Decimal("0.2"),
        latency=Decimal("0.2"),
        cost=Decimal("0.1"),
        availability=Decimal("0.1"),
    )


def _scores() -> tuple[StaticDeploymentScore, ...]:
    return (
        StaticDeploymentScore(
            deployment_id="deployment-b",
            quality=Decimal("0.8"),
            reliability=Decimal("0.8"),
            latency=Decimal("0.7"),
            cost=Decimal("0.6"),
            availability=Decimal("0.9"),
            expected_latency_ms=900,
        ),
        StaticDeploymentScore(
            deployment_id="deployment-a",
            quality=Decimal("0.9"),
            reliability=Decimal("0.9"),
            latency=Decimal("0.8"),
            cost=Decimal("0.7"),
            availability=Decimal("0.95"),
            expected_latency_ms=700,
        ),
    )


def _static_ranking() -> RankingPolicy:
    return RankingPolicy(
        schema_version="1.0",
        policy_version="ranking-v1",
        score_snapshot_id="static-v1",
        source_date=_SOURCE_DATE,
        workloads=(
            WorkloadRankingPolicy(
                workload="agent.orchestration",
                weights=_weights(),
                deployments=_scores(),
            ),
        ),
    )


def _evidence_ranking() -> EvidenceDrivenRankingPolicy:
    return EvidenceDrivenRankingPolicy(
        schema_version="1.1",
        policy_version="ranking-v2",
        score_snapshot_id="promoted-v1",
        source_date=_SOURCE_DATE,
        workloads=(
            WorkloadRankingPolicy(
                workload="agent.orchestration",
                weights=_weights(),
                deployments=_scores(),
            ),
        ),
        score_provenance_mode=ScoreProvenanceMode.BENCHMARK_HYBRID,
        benchmark_snapshot_id="sha256:" + "a" * 64,
        promotion_evidence_id="sha256:" + "b" * 64,
    )


def _server_error() -> ProviderError:
    return ProviderError(
        provider="provider-a",
        code=ProviderErrorCode.UNAVAILABLE,
        message="provider-a request failed with HTTP 503",
        retryable=True,
        status_code=503,
    )


def test_health_inspection_does_not_materialize_unseen_live_state() -> None:
    health = InMemoryHealthTracker()
    inspector = InMemoryHealthInspectionAdapter(health)

    snapshots = inspector.inspect(("deployment-a",))

    assert len(snapshots) == 1
    assert snapshots[0].deployment_id == "deployment-a"
    assert snapshots[0].status is HealthStatus.HEALTHY
    assert snapshots[0].circuit_state is CircuitState.CLOSED
    assert snapshots[0].request_count == 0
    assert getattr(health, "_states") == {}


def test_health_inspection_reports_effective_half_open_without_mutating_live_state() -> None:
    clock = FakeClock()
    health = InMemoryHealthTracker(
        CircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=30),
        clock=clock,
    )
    health.record_failure("deployment-a", _server_error(), latency_ms=25)
    assert getattr(health, "_states")["deployment-a"].circuit_state is CircuitState.OPEN

    clock.advance(30)
    inspected = InMemoryHealthInspectionAdapter(health).inspect(("deployment-a",))

    assert inspected[0].circuit_state is CircuitState.HALF_OPEN
    assert inspected[0].status is HealthStatus.DEGRADED
    assert getattr(health, "_states")["deployment-a"].circuit_state is CircuitState.OPEN


def test_static_operations_snapshot_is_deterministic_and_explicit_about_absence() -> None:
    registry = _registry()
    ranking = _static_ranking()
    health = InMemoryHealthTracker()
    service = OperationsReadModelService(
        registry=registry,
        ranking_policy=ranking,
        health=InMemoryHealthInspectionAdapter(health),
    )

    first = service.snapshot()
    second = service.snapshot()

    assert first == second
    assert first.health_scope is OperationsHealthScope.PROCESS_LOCAL
    assert first.registry.digest == registry.digest
    assert first.registry.catalog_version == "catalog-v1"
    assert first.registry.source_date == _SOURCE_DATE
    assert first.registry.deployment_count == 2
    assert first.ranking.digest == ranking.digest
    assert first.ranking.policy_version == "ranking-v1"
    assert first.ranking.score_snapshot_id == "static-v1"
    assert first.ranking.score_provenance_mode is None
    assert first.ranking.benchmark_snapshot_id is None
    assert first.ranking.promotion_evidence_id is None
    assert first.ranking.manual_override_id is None
    assert [item.deployment_id for item in first.deployments] == [
        "deployment-a",
        "deployment-b",
    ]
    assert isinstance(first.operational_evidence, OperationalEvidenceNotSupplied)
    assert first.operational_evidence.state is OperationalEvidenceState.NOT_SUPPLIED
    assert getattr(health, "_states") == {}


def test_evidence_driven_ranking_provenance_is_projected_without_inference() -> None:
    ranking = _evidence_ranking()
    service = OperationsReadModelService(
        registry=_registry(),
        ranking_policy=ranking,
        health=InMemoryHealthInspectionAdapter(InMemoryHealthTracker()),
    )

    snapshot = service.snapshot()

    assert snapshot.ranking.score_provenance_mode == "benchmark_hybrid"
    assert snapshot.ranking.benchmark_snapshot_id == "sha256:" + "a" * 64
    assert snapshot.ranking.promotion_evidence_id == "sha256:" + "b" * 64
    assert snapshot.ranking.manual_override_id is None


def test_reviewed_operational_evidence_preserves_exact_provenance_and_window() -> None:
    window_start = datetime(2026, 9, 8, 0, 0, tzinfo=UTC)
    window_end = window_start + timedelta(minutes=15)
    captured_at = window_end + timedelta(seconds=5)
    evidence = create_operational_evidence_snapshot(
        snapshot_version="operational-v1",
        collector_id="gateway-process",
        collector_version="1.0.0",
        window_start=window_start,
        window_end=window_end,
        captured_at=captured_at,
        records=(
            OperationalEvidenceRecord(
                runtime_workload="agent.orchestration",
                deployment_id="deployment-a",
                gateway_request_count=10,
                provider_attempt_count=12,
                successful_provider_attempt_count=10,
                provider_error_count=2,
                rate_limit_error_count=1,
                timeout_count=1,
                fallback_request_count=2,
                provider_latency_p50_ms=500,
                provider_latency_p95_ms=900,
            ),
        ),
    )
    service = OperationsReadModelService(
        registry=_registry(),
        ranking_policy=_static_ranking(),
        health=InMemoryHealthInspectionAdapter(InMemoryHealthTracker()),
    )

    snapshot = service.snapshot(operational_evidence=evidence)

    assert isinstance(snapshot.operational_evidence, OperationalEvidenceAvailable)
    assert snapshot.operational_evidence.state is OperationalEvidenceState.AVAILABLE
    assert snapshot.operational_evidence.evidence_id == evidence.evidence_id
    assert snapshot.operational_evidence.snapshot_version == "operational-v1"
    assert snapshot.operational_evidence.collector_id == "gateway-process"
    assert snapshot.operational_evidence.collector_version == "1.0.0"
    assert snapshot.operational_evidence.window_start == window_start
    assert snapshot.operational_evidence.window_end == window_end
    assert snapshot.operational_evidence.captured_at == captured_at
    assert snapshot.operational_evidence.record_count == 1
