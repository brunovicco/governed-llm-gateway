"""Staged process bootstrap that validates all runtime artifacts before secret access."""

from dataclasses import dataclass
from pathlib import Path

from governed_llm_gateway_core.adapters import (
    PolicyRouterHttpAdapter,
    PolicyRouterRuntimeDocument,
    PolicyRouterSecretResolver,
    ProviderRuntimeDocument,
    ProviderSecretResolver,
    build_policy_router_adapter,
    build_static_provider_resolver,
    load_model_registry,
    load_policy_router_runtime_document,
    load_provider_runtime_document,
    validate_provider_runtime_registry,
)
from governed_llm_gateway_core.application.resilience import StaticProviderResolver
from governed_llm_gateway_core.domain import ModelRegistry

from .client_auth import (
    GatewayClientSecretResolver,
    StaticGatewayClientContextResolver,
    build_static_gateway_client_context_resolver,
)
from .client_auth_json import GatewayClientAuthDocument, load_gateway_client_auth_document
from .policy_router_bootstrap import validate_policy_router_client_auth


@dataclass(frozen=True, slots=True)
class GovernedProcessBootstrapPaths:
    """Deployment-owned artifacts required before governed process activation."""

    model_registry_path: Path
    provider_runtime_path: Path
    client_auth_path: Path
    policy_router_path: Path

    def __post_init__(self) -> None:
        """Reject implicit path coercion so startup inputs remain explicit and reviewable."""
        for name, value in (
            ("model_registry_path", self.model_registry_path),
            ("provider_runtime_path", self.provider_runtime_path),
            ("client_auth_path", self.client_auth_path),
            ("policy_router_path", self.policy_router_path),
        ):
            if not isinstance(value, Path):
                raise TypeError(f"{name} must be a pathlib.Path")


@dataclass(frozen=True, slots=True)
class GovernedProcessArtifacts:
    """Secret-free runtime documents after every structural and cross-artifact gate."""

    registry: ModelRegistry
    provider_runtime_document: ProviderRuntimeDocument
    client_auth_document: GatewayClientAuthDocument
    policy_router_runtime_document: PolicyRouterRuntimeDocument

    def __post_init__(self) -> None:
        """Revalidate cross-artifact invariants even for direct construction."""
        if not isinstance(self.registry, ModelRegistry):
            raise TypeError("registry must use ModelRegistry")
        if not isinstance(self.provider_runtime_document, ProviderRuntimeDocument):
            raise TypeError("provider_runtime_document must use ProviderRuntimeDocument")
        if not isinstance(self.client_auth_document, GatewayClientAuthDocument):
            raise TypeError("client_auth_document must use GatewayClientAuthDocument")
        if not isinstance(self.policy_router_runtime_document, PolicyRouterRuntimeDocument):
            raise TypeError("policy_router_runtime_document must use PolicyRouterRuntimeDocument")

        validate_provider_runtime_registry(self.provider_runtime_document, self.registry)
        validate_policy_router_client_auth(
            self.policy_router_runtime_document,
            self.client_auth_document,
        )

    @property
    def model_registry_digest(self) -> str:
        """Return deterministic model-registry provenance."""
        return self.registry.digest

    @property
    def provider_runtime_digest(self) -> str:
        """Return deterministic provider-runtime provenance."""
        return self.provider_runtime_document.digest

    @property
    def provider_runtime_config_version(self) -> str:
        """Return the provider-runtime configuration version."""
        return self.provider_runtime_document.config_version

    @property
    def client_auth_digest(self) -> str:
        """Return deterministic Gateway client-auth provenance."""
        return self.client_auth_document.digest

    @property
    def client_auth_config_version(self) -> str:
        """Return the Gateway client-auth configuration version."""
        return self.client_auth_document.config_version

    @property
    def policy_router_runtime_digest(self) -> str:
        """Return deterministic Policy Router runtime provenance."""
        return self.policy_router_runtime_document.digest

    @property
    def policy_router_runtime_config_version(self) -> str:
        """Return the Policy Router runtime configuration version."""
        return self.policy_router_runtime_document.config_version


@dataclass(frozen=True, slots=True)
class GovernedProcessRuntimeBundle:
    """Secret-backed runtime adapters materialized only after full artifact validation."""

    artifacts: GovernedProcessArtifacts
    client_context_resolver: StaticGatewayClientContextResolver
    policy_router_adapter: PolicyRouterHttpAdapter | None
    provider_resolver: StaticProviderResolver

    @property
    def model_registry_digest(self) -> str:
        """Expose model-registry provenance without duplicating artifact state."""
        return self.artifacts.model_registry_digest

    @property
    def provider_runtime_digest(self) -> str:
        """Expose provider-runtime provenance without duplicating artifact state."""
        return self.artifacts.provider_runtime_digest

    @property
    def client_auth_digest(self) -> str:
        """Expose client-auth provenance without duplicating artifact state."""
        return self.artifacts.client_auth_digest

    @property
    def policy_router_runtime_digest(self) -> str:
        """Expose Policy Router provenance without duplicating artifact state."""
        return self.artifacts.policy_router_runtime_digest


def load_governed_process_artifacts(
    paths: GovernedProcessBootstrapPaths,
) -> GovernedProcessArtifacts:
    """Load every runtime document and finish all no-secret validation gates."""
    if not isinstance(paths, GovernedProcessBootstrapPaths):
        raise TypeError("paths must use GovernedProcessBootstrapPaths")

    registry = load_model_registry(paths.model_registry_path)
    provider_runtime_document = load_provider_runtime_document(paths.provider_runtime_path)
    client_auth_document = load_gateway_client_auth_document(paths.client_auth_path)
    policy_router_runtime_document = load_policy_router_runtime_document(paths.policy_router_path)

    return GovernedProcessArtifacts(
        registry=registry,
        provider_runtime_document=provider_runtime_document,
        client_auth_document=client_auth_document,
        policy_router_runtime_document=policy_router_runtime_document,
    )


def materialize_governed_process_runtime(
    artifacts: GovernedProcessArtifacts,
    *,
    client_secrets: GatewayClientSecretResolver,
    policy_router_secrets: PolicyRouterSecretResolver,
    provider_secrets: ProviderSecretResolver,
) -> GovernedProcessRuntimeBundle:
    """Resolve server-side credentials only after the complete no-secret stage succeeds."""
    if not isinstance(artifacts, GovernedProcessArtifacts):
        raise TypeError("artifacts must use GovernedProcessArtifacts")

    # Resolve identity and authority credentials before provider credentials. This ordering is
    # operational least privilege only; it does not grant or widen authorization.
    client_context_resolver = build_static_gateway_client_context_resolver(
        artifacts.client_auth_document.bindings,
        client_secrets,
    )
    policy_router_adapter = build_policy_router_adapter(
        artifacts.policy_router_runtime_document.runtime,
        policy_router_secrets,
    )
    provider_resolver = build_static_provider_resolver(
        artifacts.provider_runtime_document.bindings,
        provider_secrets,
    )

    return GovernedProcessRuntimeBundle(
        artifacts=artifacts,
        client_context_resolver=client_context_resolver,
        policy_router_adapter=policy_router_adapter,
        provider_resolver=provider_resolver,
    )


def bootstrap_governed_process_runtime(
    paths: GovernedProcessBootstrapPaths,
    *,
    client_secrets: GatewayClientSecretResolver,
    policy_router_secrets: PolicyRouterSecretResolver,
    provider_secrets: ProviderSecretResolver,
) -> GovernedProcessRuntimeBundle:
    """Validate all artifacts first, then materialize secret-backed runtime adapters."""
    artifacts = load_governed_process_artifacts(paths)
    return materialize_governed_process_runtime(
        artifacts,
        client_secrets=client_secrets,
        policy_router_secrets=policy_router_secrets,
        provider_secrets=provider_secrets,
    )
