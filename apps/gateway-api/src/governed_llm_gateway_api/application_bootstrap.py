"""Staged application bootstrap over PC-8 runtime and PC-9 service composition."""

from dataclasses import dataclass
from pathlib import Path

from a2a_otel_kit import Observability
from governed_llm_gateway_core.adapters import (
    ComplexityRoutingDocument,
    PolicyRouterSecretResolver,
    ProviderSecretResolver,
    load_approved_ranking_artifact,
    load_complexity_routing_document,
    load_ranking_policy,
)
from governed_llm_gateway_core.application import InMemoryHealthTracker, PolicyProjectionDefaults
from governed_llm_gateway_core.domain.ranking import RankingPolicy
from governed_llm_gateway_core.domain.ranking_override import ApprovedRankingArtifact
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
    ranking_policy_path: Path | None = None
    approved_ranking_artifact_path: Path | None = None
    expected_ranking_artifact_id: str | None = None
    complexity_routing_path: Path | None = None

    def __post_init__(self) -> None:
        """Require one explicit ranking source and preserve explicit complexity activation."""
        if not isinstance(self.process, GovernedProcessBootstrapPaths):
            raise TypeError("process must use GovernedProcessBootstrapPaths")
        if self.ranking_policy_path is not None and not isinstance(self.ranking_policy_path, Path):
            raise TypeError("ranking_policy_path must be a pathlib.Path or None")
        if self.approved_ranking_artifact_path is not None and not isinstance(
            self.approved_ranking_artifact_path, Path
        ):
            raise TypeError("approved_ranking_artifact_path must be a pathlib.Path or None")
        if self.expected_ranking_artifact_id is not None and not isinstance(
            self.expected_ranking_artifact_id, str
        ):
            raise TypeError("expected_ranking_artifact_id must be a string or None")
        if self.complexity_routing_path is not None and not isinstance(
            self.complexity_routing_path, Path
        ):
            raise TypeError("complexity_routing_path must be a pathlib.Path or None")

        static_selected = self.ranking_policy_path is not None
        approved_path_selected = self.approved_ranking_artifact_path is not None
        approved_id_selected = self.expected_ranking_artifact_id is not None
        if static_selected and (approved_path_selected or approved_id_selected):
            raise ValueError(
                "ranking bootstrap must select static policy or approved artifact, not both"
            )
        if not static_selected and not approved_path_selected:
            raise ValueError("ranking bootstrap requires one explicit ranking source")
        if approved_path_selected != approved_id_selected:
            raise ValueError(
                "approved ranking artifact path and expected artifact id must be supplied together"
            )


@dataclass(frozen=True, slots=True)
class GovernedApplicationArtifacts:
    """Complete secret-free application artifacts after routing compatibility validation."""

    process: GovernedProcessArtifacts
    ranking_policy: RankingPolicy
    complexity_routing: ComplexityRoutingDocument | None = None
    approved_ranking_artifact: ApprovedRankingArtifact | None = None

    def __post_init__(self) -> None:
        """Revalidate the complete no-secret composition boundary on direct construction."""
        if not isinstance(self.process, GovernedProcessArtifacts):
            raise TypeError("process must use GovernedProcessArtifacts")
        if self.approved_ranking_artifact is not None:
            if not isinstance(self.approved_ranking_artifact, ApprovedRankingArtifact):
                raise TypeError(
                    "approved_ranking_artifact must use ApprovedRankingArtifact or None"
                )
            if self.approved_ranking_artifact.policy.digest != self.ranking_policy.digest:
                raise ValueError(
                    "approved ranking artifact policy must match the effective ranking policy"
                )
        validate_governed_routing_inputs(
            ranking_policy=self.ranking_policy,
            complexity_routing=self.complexity_routing,
        )

    @property
    def complexity_enabled(self) -> bool:
        """Report whether complexity routing was explicitly supplied for activation."""
        return self.complexity_routing is not None

    @property
    def approved_ranking_artifact_id(self) -> str | None:
        """Expose the exact selected approval identity without changing ranking authority."""
        if self.approved_ranking_artifact is None:
            return None
        return self.approved_ranking_artifact.artifact_id


def load_governed_application_artifacts(
    paths: GovernedApplicationBootstrapPaths,
) -> GovernedApplicationArtifacts:
    """Load every process/routing artifact and finish all gates before secret access."""
    if not isinstance(paths, GovernedApplicationBootstrapPaths):
        raise TypeError("paths must use GovernedApplicationBootstrapPaths")

    process = load_governed_process_artifacts(paths.process)
    approved_ranking_artifact: ApprovedRankingArtifact | None = None
    if paths.ranking_policy_path is not None:
        ranking_policy = load_ranking_policy(paths.ranking_policy_path)
    else:
        approved_path = paths.approved_ranking_artifact_path
        expected_artifact_id = paths.expected_ranking_artifact_id
        if approved_path is None or expected_artifact_id is None:
            raise RuntimeError("validated approved ranking artifact selection is incomplete")
        approved_ranking_artifact = load_approved_ranking_artifact(
            approved_path,
            expected_artifact_id=expected_artifact_id,
        )
        ranking_policy = approved_ranking_artifact.policy

    complexity_routing = (
        load_complexity_routing_document(paths.complexity_routing_path)
        if paths.complexity_routing_path is not None
        else None
    )
    return GovernedApplicationArtifacts(
        process=process,
        ranking_policy=ranking_policy,
        complexity_routing=complexity_routing,
        approved_ranking_artifact=approved_ranking_artifact,
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
