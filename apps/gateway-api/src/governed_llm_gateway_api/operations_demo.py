"""Credential-isolated local bootstrap for read-only Gateway operations surfaces."""

import argparse
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import uvicorn
from fastapi import FastAPI
from governed_llm_gateway_core.adapters import (
    load_model_registry,
    load_policy_router_runtime_document,
    load_provider_runtime_document,
    load_ranking_policy,
    validate_provider_runtime_registry,
)
from governed_llm_gateway_core.application import (
    InMemoryHealthInspectionAdapter,
    InMemoryHealthTracker,
    OperationsReadModelService,
)

from .client_auth import (
    EnvironmentGatewayClientSecretResolver,
    build_static_gateway_client_context_resolver,
)
from .client_auth_json import load_gateway_client_auth_document
from .operations_access import OperationsReadAccessService
from .operations_access_json import (
    load_operations_read_access_document,
    validate_operations_access_client_auth,
)
from .operations_http import attach_operations_routes
from .operations_snapshot import DeploymentOperationsSnapshotReader
from .process_health import attach_process_health_routes

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8000
_MODEL_REGISTRY_PATH = Path("config/model_registry.yaml")
_RANKING_POLICY_PATH = Path("config/ranking_policy.yaml")
_PROVIDER_RUNTIME_PATH = Path("config/providers/runtime.json")
_POLICY_ROUTER_PATH = Path("config/policy/router.json")
_CLIENT_AUTH_PATH = Path("examples/local-demo/client-auth.json")
_OPERATIONS_ACCESS_PATH = Path("examples/local-demo/operations-access.json")


class OperationsDemoConfigurationError(ValueError):
    """Raised when the local Operations demo would cross an execution boundary."""


class OperationsDemoRunner(Protocol):
    """Run one already-composed operations-only FastAPI application."""

    def run(self, app: FastAPI, *, host: str, port: int) -> None:
        """Serve the operations-only application until the process terminates."""
        ...


class UvicornOperationsDemoRunner:
    """ASGI runner for the bounded local Operations demo."""

    def run(self, app: FastAPI, *, host: str, port: int) -> None:
        """Run exactly one local Uvicorn worker."""
        uvicorn.run(app, host=host, port=port, workers=1)


@dataclass(frozen=True, slots=True)
class OperationsDemoSettings:
    """Explicit local-only settings for the operations demo process."""

    repository_root: Path
    port: int = _DEFAULT_PORT
    host: str = _DEFAULT_HOST

    def __post_init__(self) -> None:
        """Keep the demo bound to the reviewed local host and a valid TCP port."""
        if not isinstance(self.repository_root, Path):
            raise TypeError("repository_root must use pathlib.Path")
        if not self.repository_root.is_absolute():
            raise OperationsDemoConfigurationError("repository_root must be absolute")
        if self.host != _DEFAULT_HOST:
            raise OperationsDemoConfigurationError("operations demo host must remain 127.0.0.1")
        if isinstance(self.port, bool) or not isinstance(self.port, int):
            raise TypeError("port must be an integer")
        if not 1 <= self.port <= 65_535:
            raise OperationsDemoConfigurationError("port must be between 1 and 65535")


def parse_operations_demo_args(argv: Sequence[str]) -> OperationsDemoSettings:
    """Parse the intentionally small local-demo command surface."""
    parser = argparse.ArgumentParser(
        prog="governed-llm-gateway-operations-demo",
        description="Start the read-only local Operations demo without inference authority.",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root containing the reviewed local-demo artifacts.",
    )
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT)
    args = parser.parse_args(tuple(argv))
    return OperationsDemoSettings(
        repository_root=args.repository_root.resolve(),
        port=args.port,
    )


def build_operations_demo_app(
    settings: OperationsDemoSettings,
    *,
    environ: Mapping[str, str] | None = None,
) -> FastAPI:
    """Compose only authenticated Operations reads over a proven non-executable baseline."""
    if not isinstance(settings, OperationsDemoSettings):
        raise TypeError("settings must use OperationsDemoSettings")
    root = settings.repository_root
    if not root.is_dir():
        raise OperationsDemoConfigurationError("repository_root must be an existing directory")

    registry = load_model_registry(root / _MODEL_REGISTRY_PATH)
    ranking_policy = load_ranking_policy(root / _RANKING_POLICY_PATH)
    provider_runtime = load_provider_runtime_document(root / _PROVIDER_RUNTIME_PATH)
    validate_provider_runtime_registry(provider_runtime, registry)
    policy_router = load_policy_router_runtime_document(root / _POLICY_ROUTER_PATH)
    _require_non_executable_baseline(
        registry_deployment_count=len(registry.deployments),
        ranking_workload_count=len(ranking_policy.workloads),
        provider_binding_count=len(provider_runtime.bindings),
        policy_router_enabled=policy_router.runtime.enabled,
        policy_router_endpoint=policy_router.runtime.endpoint,
        policy_router_binding_count=len(policy_router.runtime.bindings),
    )

    client_auth = load_gateway_client_auth_document(root / _CLIENT_AUTH_PATH)
    operations_access = load_operations_read_access_document(root / _OPERATIONS_ACCESS_PATH)
    validate_operations_access_client_auth(operations_access, client_auth)
    client_context = build_static_gateway_client_context_resolver(
        client_auth.bindings,
        EnvironmentGatewayClientSecretResolver(environ),
    )
    access = OperationsReadAccessService(
        authenticator=client_context,
        policy=operations_access.policy,
    )

    health = InMemoryHealthTracker()
    read_model = OperationsReadModelService(
        registry=registry,
        ranking_policy=ranking_policy,
        health=InMemoryHealthInspectionAdapter(health),
    )
    snapshot_reader = DeploymentOperationsSnapshotReader(read_model)

    app = FastAPI(
        title="Governed LLM Gateway Operations Demo",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    attach_operations_routes(app, access=access, read_model=snapshot_reader)
    attach_process_health_routes(app)
    return app


def run_operations_demo(
    settings: OperationsDemoSettings,
    *,
    environ: Mapping[str, str] | None = None,
    runner: OperationsDemoRunner | None = None,
) -> None:
    """Build and run the operations-only local process without serving inference routes."""
    app = build_operations_demo_app(settings, environ=environ)
    selected_runner = UvicornOperationsDemoRunner() if runner is None else runner
    selected_runner.run(app, host=settings.host, port=settings.port)


def main() -> None:
    """Installed console-script entrypoint for the local Operations demo."""
    run_operations_demo(parse_operations_demo_args(sys.argv[1:]))


def _require_non_executable_baseline(
    *,
    registry_deployment_count: int,
    ranking_workload_count: int,
    provider_binding_count: int,
    policy_router_enabled: bool,
    policy_router_endpoint: str | None,
    policy_router_binding_count: int,
) -> None:
    """Reject any artifact state that could be mistaken for an executable serving baseline."""
    if registry_deployment_count != 0:
        raise OperationsDemoConfigurationError(
            "operations demo requires the reviewed empty model registry"
        )
    if ranking_workload_count != 0:
        raise OperationsDemoConfigurationError(
            "operations demo requires the reviewed empty ranking policy"
        )
    if provider_binding_count != 0:
        raise OperationsDemoConfigurationError(
            "operations demo requires zero provider runtime bindings"
        )
    if (
        policy_router_enabled
        or policy_router_endpoint is not None
        or policy_router_binding_count != 0
    ):
        raise OperationsDemoConfigurationError(
            "operations demo requires the disabled credential-free Policy Router baseline"
        )
