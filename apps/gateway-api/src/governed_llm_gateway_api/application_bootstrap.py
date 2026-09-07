"""Staged application bootstrap over PC-8 runtime and PC-9 service composition."""

from dataclasses import dataclass
from pathlib import Path

from a2a_otel_kit import Observability
from governed_llm_gateway_core.adapters import (
    ComplexityRoutingDocument,
    PolicyRouterSecretResolver,
    ProviderSecretResolver,
    load_complexity_routing_document,
    load_ranking_policy,
)
from governed_llm_gateway_core.application import InMemoryHealthTracker, PolicyProjectionDefaults
from governed_llm_gateway_core.domain.ranking import RankingPolicy
from governed_llm_gateway_core.domain.resilience import RetryPolicy

from .client_auth import GatewayClientSecretResolver
from .process_bootstrap import (
    GovernedProcessArtifacts,
    GovernedProcessBootstrapPaths,
    load_governed_process_artifacts,
    materialize_governed_process_runtime,
)
from .service_composition import (
    GovernedGatewayServices,
    compose_governed_gateway_services,
    validate_governed_routing_inputs,
)


@dataclass(frozen=True, slots=True)
class GovernedApplicationBootstrapPaths:
    """Deployment-owned artifact paths that must validate before any secret access."""

    process: GovernedProcessBootstrapPaths
    ranking_policy_path: Path
    complexity_routing_path: Path | None = None

    def __post_init__(self) -> None:
        """Reject implicit path coercion and preserve explicit complexity activation."""
        if not isinstance(self.process, GovernedProcessBootstrapPaths):
            raise TypeError("process must use GovernedProcessBootstrapPaths")
        if not isinstance(self.ranking_policy_path, Path):
            raise TypeError("ranking_policy_path must be a pathlib.Path")
        if self.complexity_routing_path is not None and not isinstance(
            self.complexity_routing_path, Path
        ):
            raise TypeError("complexity_routing_path must be a pathlib.Path or None")


@dataclass(frozen=True, slots=True)
class GovernedApplicationArtifacts:
    """Complete secret-free application artifacts after routing compatibility validation."""

    process: GovernedProcessArtifacts
    ranking_policy: RankingPolicy
    complexity_routing: ComplexityRoutingDocument | None = None

    def __post_init__(self) -> None:
        """Revalidate the complete no-secret composition boundary on direct construction."""
        if not isinstance(self.process, GovernedProcessArtifacts):
            raise TypeError("process must use GovernedProcessArtifacts")
        validate_governed_routing_inputs(
            ranking_policy=self.ranking_policy,
            complexity_routing=self.complexity_routing,
        )

    @property
    def complexity_enabled(self) -> bool:
        """Report whether complexity routing was explicitly supplied for activation."""
        return self.complexity_routing is not None


def load_governed_application_artifacts(
    paths: GovernedApplicationBootstrapPaths,
) -> GovernedApplicationArtifacts:
    """Load every process/routing artifact and finish all gates before secret access."""
    if not isinstance(paths, GovernedApplicationBootstrapPaths):
        raise TypeError("paths must use GovernedApplicationBootstrapPaths")

    process = load_governed_process_artifacts(paths.process)
    ranking_policy = load_ranking_policy(paths.ranking_policy_path)
    complexity_routing = (
        load_complexity_routing_document(paths.complexity_routing_path)
        if paths.complexity_routing_path is not None
        else None
    )
    return GovernedApplicationArtifacts(
        process=process,
        ranking_policy=ranking_policy,
        complexity_routing=complexity_routing,
    )


def materialize_governed_application_services(
    artifacts: GovernedApplicationArtifacts,
    *,
    client_secrets: GatewayClientSecretResolver,
    policy_router_secrets: PolicyRouterSecretResolver,
    provider_secrets: ProviderSecretResolver,
    defaults: PolicyProjectionDefaults,
    observability: Observability | None = None,
    retry_policy: RetryPolicy | None = None,
    health: InMemoryHealthTracker | None = None,
) -> GovernedGatewayServices:
    """Resolve secrets only after routing artifacts validated, then delegate to PC-9."""
    if not isinstance(artifacts, GovernedApplicationArtifacts):
        raise TypeError("artifacts must use GovernedApplicationArtifacts")

    runtime = materialize_governed_process_runtime(
        artifacts.process,
        client_secrets=client_secrets,
        policy_router_secrets=policy_router_secrets,
        provider_secrets=provider_secrets,
    )
    return compose_governed_gateway_services(
        runtime,
        ranking_policy=artifacts.ranking_policy,
        defaults=defaults,
        complexity_routing=artifacts.complexity_routing,
        observability=observability,
        retry_policy=retry_policy,
        health=health,
    )


def bootstrap_governed_application_services(
    paths: GovernedApplicationBootstrapPaths,
    *,
    client_secrets: GatewayClientSecretResolver,
    policy_router_secrets: PolicyRouterSecretResolver,
    provider_secrets: ProviderSecretResolver,
    defaults: PolicyProjectionDefaults,
    observability: Observability | None = None,
    retry_policy: RetryPolicy | None = None,
    health: InMemoryHealthTracker | None = None,
) -> GovernedGatewayServices:
    """Validate every deployment artifact before materializing any secret-backed service."""
    artifacts = load_governed_application_artifacts(paths)
    return materialize_governed_application_services(
        artifacts,
        client_secrets=client_secrets,
        policy_router_secrets=policy_router_secrets,
        provider_secrets=provider_secrets,
        defaults=defaults,
        observability=observability,
        retry_policy=retry_policy,
        health=health,
    )
