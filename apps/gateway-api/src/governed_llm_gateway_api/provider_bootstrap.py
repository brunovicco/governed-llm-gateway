"""Provider-runtime composition boundary for the gateway API process."""

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


@dataclass(frozen=True, slots=True)
class ProviderRuntimeBootstrapPaths:
    """Explicit local artifacts used to compose provider execution dependencies once."""

    model_registry_path: Path
    provider_runtime_path: Path

    def __post_init__(self) -> None:
        """Reject runtime misuse rather than silently coercing untrusted path-like values."""
        if not isinstance(self.model_registry_path, Path):
            raise TypeError("model_registry_path must be a pathlib.Path")
        if not isinstance(self.provider_runtime_path, Path):
            raise TypeError("provider_runtime_path must be a pathlib.Path")


@dataclass(frozen=True, slots=True)
class ProviderRuntimeBootstrapBundle:
    """Validated provider execution dependencies plus configuration provenance."""

    registry: ModelRegistry
    runtime_document: ProviderRuntimeDocument
    resolver: StaticProviderResolver

    @property
    def model_registry_digest(self) -> str:
        """Return deterministic Model Registry provenance without exposing provider secrets."""
        return self.registry.digest

    @property
    def provider_runtime_digest(self) -> str:
        """Return deterministic provider-runtime provenance without exposing provider secrets."""
        return self.runtime_document.digest

    @property
    def provider_runtime_config_version(self) -> str:
        """Return the provider-runtime configuration version used for this bundle."""
        return self.runtime_document.config_version


def bootstrap_provider_runtime(
    paths: ProviderRuntimeBootstrapPaths,
    secrets: ProviderSecretResolver,
) -> ProviderRuntimeBootstrapBundle:
    """Load, cross-check, then resolve server-side provider credentials exactly once."""
    if not isinstance(paths, ProviderRuntimeBootstrapPaths):
        raise TypeError("paths must use ProviderRuntimeBootstrapPaths")

    registry = load_model_registry(paths.model_registry_path)
    runtime_document = load_provider_runtime_document(paths.provider_runtime_path)

    # This operational consistency gate deliberately runs before any secret backend access.
    validate_provider_runtime_registry(runtime_document, registry)

    resolver = build_static_provider_resolver(runtime_document.bindings, secrets)
    return ProviderRuntimeBootstrapBundle(
        registry=registry,
        runtime_document=runtime_document,
        resolver=resolver,
    )
