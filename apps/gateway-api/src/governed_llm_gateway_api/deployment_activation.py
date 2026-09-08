"""Explicit deployment settings and activation above the governed application bootstrap."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from a2a_otel_kit import Observability
from governed_llm_gateway_core.adapters import (
    EnvironmentPolicyRouterSecretResolver,
    EnvironmentProviderSecretResolver,
)
from governed_llm_gateway_core.application import InMemoryHealthTracker, PolicyProjectionDefaults
from governed_llm_gateway_core.domain.resilience import RetryPolicy

from .application_bootstrap import (
    GovernedApplicationBootstrapPaths,
    load_governed_application_artifacts,
    materialize_governed_application_services,
)
from .client_auth import EnvironmentGatewayClientSecretResolver
from .process_bootstrap import GovernedProcessBootstrapPaths
from .service_composition import GovernedGatewayServices


@dataclass(frozen=True, slots=True)
class GovernedDeploymentSettings:
    """Deployment-owned, secret-free inputs required before executable process activation."""

    deployment_root: Path
    model_registry_path: Path
    provider_runtime_path: Path
    client_auth_path: Path
    policy_router_path: Path
    default_max_latency_ms: int
    default_max_cost_usd: Decimal
    ranking_policy_path: Path | None = None
    approved_ranking_artifact_path: Path | None = None
    expected_ranking_artifact_id: str | None = None
    complexity_routing_path: Path | None = None
    operations_access_path: Path | None = None
    operational_evidence_path: Path | None = None

    def __post_init__(self) -> None:
        """Validate settings without reading artifacts, secrets, or process environment."""
        if not isinstance(self.deployment_root, Path):
            raise TypeError("deployment_root must be a pathlib.Path")
        if not self.deployment_root.is_absolute():
            raise ValueError("deployment_root must be an absolute path")
        for name, value in (
            ("model_registry_path", self.model_registry_path),
            ("provider_runtime_path", self.provider_runtime_path),
            ("client_auth_path", self.client_auth_path),
            ("policy_router_path", self.policy_router_path),
        ):
            if not isinstance(value, Path):
                raise TypeError(f"{name} must be a pathlib.Path")
        for name, optional_value in (
            ("ranking_policy_path", self.ranking_policy_path),
            ("approved_ranking_artifact_path", self.approved_ranking_artifact_path),
            ("complexity_routing_path", self.complexity_routing_path),
            ("operations_access_path", self.operations_access_path),
            ("operational_evidence_path", self.operational_evidence_path),
        ):
            if optional_value is not None and not isinstance(optional_value, Path):
                raise TypeError(f"{name} must be a pathlib.Path or None")

        static_selected = self.ranking_policy_path is not None
        approved_path_selected = self.approved_ranking_artifact_path is not None
        approved_id_selected = self.expected_ranking_artifact_id is not None
        if static_selected and (approved_path_selected or approved_id_selected):
            raise ValueError("deployment ranking source must be static or approved, not both")
        if not static_selected and not approved_path_selected:
            raise ValueError("deployment settings require one explicit ranking source")
        if approved_path_selected != approved_id_selected:
            raise ValueError(
                "approved ranking artifact path and expected artifact id must be supplied together"
            )
        if approved_id_selected:
            expected_id = self.expected_ranking_artifact_id
            if expected_id is None or not expected_id or expected_id.strip() != expected_id:
                raise ValueError("expected_ranking_artifact_id must be non-empty and normalized")

        PolicyProjectionDefaults(
            max_latency_ms=self.default_max_latency_ms,
            max_cost_usd=self.default_max_cost_usd,
        )

    @property
    def projection_defaults(self) -> PolicyProjectionDefaults:
        """Materialize the existing immutable projection-default contract."""
        return PolicyProjectionDefaults(
            max_latency_ms=self.default_max_latency_ms,
            max_cost_usd=self.default_max_cost_usd,
        )

    @property
    def bootstrap_paths(self) -> GovernedApplicationBootstrapPaths:
        """Resolve explicit deployment paths without scanning or discovering artifacts."""
        root = self.deployment_root.resolve(strict=False)
        return GovernedApplicationBootstrapPaths(
            process=GovernedProcessBootstrapPaths(
                model_registry_path=_resolve_deployment_path(
                    root, self.model_registry_path, "model_registry_path"
                ),
                provider_runtime_path=_resolve_deployment_path(
                    root, self.provider_runtime_path, "provider_runtime_path"
                ),
                client_auth_path=_resolve_deployment_path(
                    root, self.client_auth_path, "client_auth_path"
                ),
                policy_router_path=_resolve_deployment_path(
                    root, self.policy_router_path, "policy_router_path"
                ),
                operations_access_path=_resolve_optional_deployment_path(
                    root,
                    self.operations_access_path,
                    "operations_access_path",
                ),
            ),
            ranking_policy_path=_resolve_optional_deployment_path(
                root, self.ranking_policy_path, "ranking_policy_path"
            ),
            approved_ranking_artifact_path=_resolve_optional_deployment_path(
                root,
                self.approved_ranking_artifact_path,
                "approved_ranking_artifact_path",
            ),
            expected_ranking_artifact_id=self.expected_ranking_artifact_id,
            complexity_routing_path=_resolve_optional_deployment_path(
                root, self.complexity_routing_path, "complexity_routing_path"
            ),
            operational_evidence_path=_resolve_optional_deployment_path(
                root,
                self.operational_evidence_path,
                "operational_evidence_path",
            ),
        )


def activate_governed_deployment(
    settings: GovernedDeploymentSettings,
    *,
    environ: Mapping[str, str] | None = None,
    observability: Observability | None = None,
    retry_policy: RetryPolicy | None = None,
    health: InMemoryHealthTracker | None = None,
) -> GovernedGatewayServices:
    """Validate all deployment artifacts before binding environment-backed credentials."""
    if not isinstance(settings, GovernedDeploymentSettings):
        raise TypeError("settings must use GovernedDeploymentSettings")

    paths = settings.bootstrap_paths
    defaults = settings.projection_defaults
    artifacts = load_governed_application_artifacts(paths)

    return materialize_governed_application_services(
        artifacts,
        client_secrets=EnvironmentGatewayClientSecretResolver(environ),
        policy_router_secrets=EnvironmentPolicyRouterSecretResolver(environ),
        provider_secrets=EnvironmentProviderSecretResolver(environ),
        defaults=defaults,
        observability=observability,
        retry_policy=retry_policy,
        health=health,
    )


def _resolve_optional_deployment_path(
    root: Path,
    value: Path | None,
    field: str,
) -> Path | None:
    if value is None:
        return None
    return _resolve_deployment_path(root, value, field)


def _resolve_deployment_path(root: Path, value: Path, field: str) -> Path:
    if value.is_absolute():
        return value.resolve(strict=False)
    resolved = (root / value).resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise ValueError(f"{field} must not escape deployment_root")
    return resolved
