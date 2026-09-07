"""Fail-closed composition of Gateway client and provider runtime dependencies."""

from dataclasses import dataclass
from pathlib import Path

from governed_llm_gateway_core.adapters import (
    ProviderRuntimeDocument,
    ProviderSecretResolver,
    build_static_provider_resolver,
    load_model_registry,
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
from .client_auth_json import (
    GatewayClientAuthDocument,
    load_gateway_client_auth_document,
)


@dataclass(frozen=True, slots=True)
class GatewayRuntimeBootstrapPaths:
    """Explicit deployment-owned artifacts required by Gateway runtime startup."""

    model_registry_path: Path
    provider_runtime_path: Path
    client_auth_path: Path

    def __post_init__(self) -> None:
        """Reject path coercion so bootstrap inputs stay explicit and reviewable."""
        for name, value in (
            ("model_registry_path", self.model_registry_path),
            ("provider_runtime_path", self.provider_runtime_path),
            ("client_auth_path", self.client_auth_path),
        ):
            if not isinstance(value, Path):
                raise TypeError(f"{name} must be a pathlib.Path")


@dataclass(frozen=True, slots=True)
class GatewayRuntimeBootstrapBundle:
    """Validated runtime artifacts and immutable secret-backed resolvers."""

    registry: ModelRegistry
    provider_runtime_document: ProviderRuntimeDocument
    client_auth_document: GatewayClientAuthDocument
    provider_resolver: StaticProviderResolver
    client_context_resolver: StaticGatewayClientContextResolver

    @property
    def model_registry_digest(self) -> str:
        """Return deterministic Model Registry provenance."""
        return self.registry.digest

    @property
    def provider_runtime_digest(self) -> str:
        """Return deterministic provider-runtime artifact provenance."""
        return self.provider_runtime_document.digest

    @property
    def provider_runtime_config_version(self) -> str:
        """Return the provider-runtime configuration version."""
        return self.provider_runtime_document.config_version

    @property
    def client_auth_digest(self) -> str:
        """Return deterministic Gateway client-auth artifact provenance."""
        return self.client_auth_document.digest

    @property
    def client_auth_config_version(self) -> str:
        """Return the Gateway client-auth configuration version."""
        return self.client_auth_document.config_version


def bootstrap_gateway_runtime(
    paths: GatewayRuntimeBootstrapPaths,
    *,
    provider_secrets: ProviderSecretResolver,
    client_secrets: GatewayClientSecretResolver,
) -> GatewayRuntimeBootstrapBundle:
    """Validate every artifact before resolving any server-side credentials."""
    if not isinstance(paths, GatewayRuntimeBootstrapPaths):
        raise TypeError("paths must use GatewayRuntimeBootstrapPaths")

    registry = load_model_registry(paths.model_registry_path)
    provider_runtime_document = load_provider_runtime_document(paths.provider_runtime_path)
    client_auth_document = load_gateway_client_auth_document(paths.client_auth_path)

    # Cross-artifact consistency remains part of the no-secret validation phase.
    validate_provider_runtime_registry(provider_runtime_document, registry)

    provider_resolver = build_static_provider_resolver(
        provider_runtime_document.bindings,
        provider_secrets,
    )
    client_context_resolver = build_static_gateway_client_context_resolver(
        client_auth_document.bindings,
        client_secrets,
    )

    return GatewayRuntimeBootstrapBundle(
        registry=registry,
        provider_runtime_document=provider_runtime_document,
        client_auth_document=client_auth_document,
        provider_resolver=provider_resolver,
        client_context_resolver=client_context_resolver,
    )
