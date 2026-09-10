"""Pure service composition over an already-materialized governed process runtime."""

from dataclasses import dataclass

from fastapi import FastAPI
from governed_llm_gateway_core.adapters import ComplexityRoutingDocument
from governed_llm_gateway_core.application import (
    ComplexityRouteExplainService,
    InMemoryHealthInspectionAdapter,
    InMemoryHealthTracker,
    OperationsReadModelService,
    PolicyEnforcementService,
    PolicyProjectionDefaults,
    RouteExplainService,
)
from governed_llm_gateway_core.application.observability import ObservabilityPort
from governed_llm_gateway_core.application.streaming import StreamingExecutionService
from governed_llm_gateway_core.domain.complexity import DeterministicComplexityEvaluator
from governed_llm_gateway_core.domain.evidence_ranking import EvidenceDrivenRankingPolicy
from governed_llm_gateway_core.domain.operational_evidence import OperationalEvidenceSnapshot
from governed_llm_gateway_core.domain.ranking import RankingPolicy
from governed_llm_gateway_core.domain.resilience import RetryPolicy

from .application import create_gateway_app
from .complexity_generate import ComplexityGenerateCoordinator
from .operations_access import OperationsReadAccessService
from .operations_http import attach_operations_routes
from .operations_snapshot import DeploymentOperationsSnapshotReader
from .process_bootstrap import GovernedProcessRuntimeBundle
from .route_explain import ComplexityRouteExplainCoordinator, RouteExplainCoordinator
from .stream_generate import GenerateCoordinator


class GovernedServiceCompositionError(ValueError):
    """Raised when validated runtime inputs cannot form a safe governed service graph."""


@dataclass(frozen=True, slots=True)
class GovernedGatewayServices:
    """Explicit per-process services sharing one validated runtime and health state."""

    app: FastAPI
    health: InMemoryHealthTracker
    operations_read_model: OperationsReadModelService
    operations_snapshot_reader: DeploymentOperationsSnapshotReader
    operations_read_access: OperationsReadAccessService
    policy_enforcement: PolicyEnforcementService
    route_service: RouteExplainService
    streaming_service: StreamingExecutionService
    route_explain_coordinator: RouteExplainCoordinator
    generate_coordinator: GenerateCoordinator
    complexity_route_service: ComplexityRouteExplainService | None
    complexity_route_explain_coordinator: ComplexityRouteExplainCoordinator | None
    complexity_generate_coordinator: ComplexityGenerateCoordinator | None

    @property
    def complexity_enabled(self) -> bool:
        """Report whether the complete post-authorization complexity path was composed."""
        return self.complexity_route_service is not None


def validate_governed_routing_inputs(
    *,
    ranking_policy: RankingPolicy,
    complexity_routing: ComplexityRoutingDocument | None,
) -> None:
    """Validate routing artifacts without config, secret, environment, or network access."""
    if not isinstance(ranking_policy, RankingPolicy):
        raise TypeError("ranking_policy must use RankingPolicy")
    if complexity_routing is not None and not isinstance(
        complexity_routing, ComplexityRoutingDocument
    ):
        raise TypeError("complexity_routing must use ComplexityRoutingDocument")
    if complexity_routing is not None and not isinstance(
        ranking_policy, EvidenceDrivenRankingPolicy
    ):
        raise GovernedServiceCompositionError(
            "complexity routing requires an explicit evidence-driven ranking policy"
        )


def compose_governed_gateway_services(
    runtime: GovernedProcessRuntimeBundle,
    *,
    ranking_policy: RankingPolicy,
    defaults: PolicyProjectionDefaults,
    complexity_routing: ComplexityRoutingDocument | None = None,
    operational_evidence: OperationalEvidenceSnapshot | None = None,
    observability: ObservabilityPort | None = None,
    retry_policy: RetryPolicy | None = None,
    health: InMemoryHealthTracker | None = None,
) -> GovernedGatewayServices:
    """Build the governed HTTP service graph without reading config, secrets, or the network."""
    if not isinstance(runtime, GovernedProcessRuntimeBundle):
        raise TypeError("runtime must use GovernedProcessRuntimeBundle")
    if not isinstance(defaults, PolicyProjectionDefaults):
        raise TypeError("defaults must use PolicyProjectionDefaults")
    validate_governed_routing_inputs(
        ranking_policy=ranking_policy,
        complexity_routing=complexity_routing,
    )
    if operational_evidence is not None and not isinstance(
        operational_evidence,
        OperationalEvidenceSnapshot,
    ):
        raise TypeError("operational_evidence must use OperationalEvidenceSnapshot or None")
    if retry_policy is not None and not isinstance(retry_policy, RetryPolicy):
        raise TypeError("retry_policy must use RetryPolicy")
    if health is not None and not isinstance(health, InMemoryHealthTracker):
        raise TypeError("health must use InMemoryHealthTracker")

    policy_adapter = runtime.policy_router_adapter
    if policy_adapter is None:
        raise GovernedServiceCompositionError(
            "governed service composition requires a materialized Policy Router adapter"
        )

    active_health = health or InMemoryHealthTracker()
    policy_enforcement = PolicyEnforcementService(
        policy_adapter,
        observability=observability,
    )
    route_service = RouteExplainService(policy_enforcement)
    streaming_service = StreamingExecutionService(
        health=active_health,
        resolver=runtime.provider_resolver,
        retry_policy=retry_policy,
        observability=observability,
    )

    registry = runtime.artifacts.registry
    operations_read_model = OperationsReadModelService(
        registry=registry,
        ranking_policy=ranking_policy,
        health=InMemoryHealthInspectionAdapter(active_health),
    )
    operations_snapshot_reader = DeploymentOperationsSnapshotReader(
        read_model=operations_read_model,
        operational_evidence=operational_evidence,
    )
    context_resolver = runtime.client_context_resolver
    route_explain_coordinator = RouteExplainCoordinator(
        context_resolver=context_resolver,
        service=route_service,
        registry=registry,
        ranking_policy=ranking_policy,
        defaults=defaults,
    )
    generate_coordinator = GenerateCoordinator(
        context_resolver=context_resolver,
        route_service=route_service,
        streaming_service=streaming_service,
        health=active_health,
        registry=registry,
        ranking_policy=ranking_policy,
        defaults=defaults,
    )

    complexity_route_service: ComplexityRouteExplainService | None = None
    complexity_route_explain_coordinator: ComplexityRouteExplainCoordinator | None = None
    complexity_generate_coordinator: ComplexityGenerateCoordinator | None = None
    if complexity_routing is not None:
        evidence_policy = ranking_policy
        if not isinstance(evidence_policy, EvidenceDrivenRankingPolicy):
            raise GovernedServiceCompositionError(
                "complexity routing requires benchmark-grounded ranking evidence"
            )
        complexity_route_service = ComplexityRouteExplainService(
            policy_enforcement=policy_enforcement,
            complexity_evaluator=DeterministicComplexityEvaluator(
                complexity_routing.assessment_policy
            ),
            quality_policy=complexity_routing.quality_policy,
        )
        complexity_route_explain_coordinator = ComplexityRouteExplainCoordinator(
            context_resolver=context_resolver,
            service=complexity_route_service,
            registry=registry,
            ranking_policy=evidence_policy,
            defaults=defaults,
        )
        complexity_generate_coordinator = ComplexityGenerateCoordinator(
            context_resolver=context_resolver,
            route_service=complexity_route_service,
            streaming_service=streaming_service,
            health=active_health,
            registry=registry,
            ranking_policy=evidence_policy,
            defaults=defaults,
        )

    app = create_gateway_app(
        route_explain_coordinator,
        generate_coordinator,
        complexity_route_explain_coordinator=complexity_route_explain_coordinator,
        complexity_generate_coordinator=complexity_generate_coordinator,
        observability=observability,
    )
    attach_operations_routes(
        app,
        access=runtime.operations_read_access,
        read_model=operations_snapshot_reader,
    )
    return GovernedGatewayServices(
        app=app,
        health=active_health,
        operations_read_model=operations_read_model,
        operations_snapshot_reader=operations_snapshot_reader,
        operations_read_access=runtime.operations_read_access,
        policy_enforcement=policy_enforcement,
        route_service=route_service,
        streaming_service=streaming_service,
        route_explain_coordinator=route_explain_coordinator,
        generate_coordinator=generate_coordinator,
        complexity_route_service=complexity_route_service,
        complexity_route_explain_coordinator=complexity_route_explain_coordinator,
        complexity_generate_coordinator=complexity_generate_coordinator,
    )
