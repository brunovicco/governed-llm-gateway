"""Fail-closed Policy Router runtime composition for the Gateway API process."""

from dataclasses import dataclass
from pathlib import Path

from governed_llm_gateway_core.adapters import (
    PolicyRouterHttpAdapter,
    PolicyRouterRuntimeDocument,
    PolicyRouterSecretResolver,
    build_policy_router_adapter,
    load_policy_router_runtime_document,
)

from .client_auth_json import (
    GatewayClientAuthDocument,
    load_gateway_client_auth_document,
)


class PolicyRouterClientAuthMismatchError(ValueError):
    """Raised when authenticated Gateway clients and PDP credential bindings diverge."""


@dataclass(frozen=True, slots=True)
class PolicyRouterRuntimeBootstrapPaths:
    """Explicit deployment-owned artifacts required by Policy Router startup."""

    policy_router_path: Path
    client_auth_path: Path

    def __post_init__(self) -> None:
        """Reject path coercion so startup inputs remain explicit and reviewable."""
        if not isinstance(self.policy_router_path, Path):
            raise TypeError("policy_router_path must be a pathlib.Path")
        if not isinstance(self.client_auth_path, Path):
            raise TypeError("client_auth_path must be a pathlib.Path")


@dataclass(frozen=True, slots=True)
class PolicyRouterRuntimeBootstrapBundle:
    """Validated Policy Router runtime plus optional secret-backed HTTP adapter."""

    runtime_document: PolicyRouterRuntimeDocument
    client_auth_document: GatewayClientAuthDocument
    adapter: PolicyRouterHttpAdapter | None

    @property
    def policy_router_runtime_digest(self) -> str:
        """Return deterministic Policy Router runtime provenance."""
        return self.runtime_document.digest

    @property
    def policy_router_runtime_config_version(self) -> str:
        """Return the Policy Router runtime configuration version."""
        return self.runtime_document.config_version

    @property
    def client_auth_digest(self) -> str:
        """Return deterministic Gateway client-auth provenance."""
        return self.client_auth_document.digest

    @property
    def client_auth_config_version(self) -> str:
        """Return the Gateway client-auth configuration version."""
        return self.client_auth_document.config_version


def validate_policy_router_client_auth(
    runtime_document: PolicyRouterRuntimeDocument,
    client_auth_document: GatewayClientAuthDocument,
) -> None:
    """Require exact trusted-client coverage before any Policy Router secret access."""
    runtime_client_ids = {
        binding.client_id for binding in runtime_document.runtime.bindings
    }
    authenticated_client_ids = {
        binding.client_id for binding in client_auth_document.bindings
    }
    if runtime_client_ids != authenticated_client_ids:
        raise PolicyRouterClientAuthMismatchError(
            "Policy Router credential bindings must exactly match Gateway client-auth client IDs"
        )


def bootstrap_policy_router_runtime(
    paths: PolicyRouterRuntimeBootstrapPaths,
    secrets: PolicyRouterSecretResolver,
) -> PolicyRouterRuntimeBootstrapBundle:
    """Load and cross-check artifacts before resolving any Policy Router credential."""
    if not isinstance(paths, PolicyRouterRuntimeBootstrapPaths):
        raise TypeError("paths must use PolicyRouterRuntimeBootstrapPaths")

    runtime_document = load_policy_router_runtime_document(paths.policy_router_path)
    client_auth_document = load_gateway_client_auth_document(paths.client_auth_path)

    # Cross-artifact identity coverage is a no-secret startup gate.
    validate_policy_router_client_auth(runtime_document, client_auth_document)

    adapter = build_policy_router_adapter(runtime_document.runtime, secrets)
    return PolicyRouterRuntimeBootstrapBundle(
        runtime_document=runtime_document,
        client_auth_document=client_auth_document,
        adapter=adapter,
    )
