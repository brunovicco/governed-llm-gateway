"""Executable Gateway process settings and ASGI server boundary."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol

import uvicorn
from a2a_otel_kit.application.settings import ObservabilitySettings
from a2a_otel_kit.entrypoints.observability import Observability
from fastapi import FastAPI

from .deployment_activation import GovernedDeploymentSettings, activate_governed_deployment
from .process_health import attach_process_health_routes

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8000
_MAX_HOST_LENGTH = 253
_GATEWAY_SERVICE_NAME = "governed-llm-gateway"
_GATEWAY_SERVICE_VERSION = "0.1.0"
_DEFAULT_OTLP_TIMEOUT_SECONDS = 10.0
_OBSERVABILITY_SHUTDOWN_TIMEOUT_SECONDS = 5.0
_OBSERVABILITY_LOG_LEVEL = "INFO"
_OBSERVABILITY_LOG_FORMAT = "json"
_LOGGER = logging.getLogger(__name__)


class ServerRunner(Protocol):
    """Start one already-composed FastAPI application."""

    def run(self, app: FastAPI, *, host: str, port: int) -> None:
        """Run the application until the process terminates."""
        ...


class UvicornServerRunner:
    """Production ASGI runner for the governed Gateway process."""

    def run(self, app: FastAPI, *, host: str, port: int) -> None:
        """Run exactly one Uvicorn worker around an already-composed application."""
        uvicorn.run(app, host=host, port=port, workers=1)


@dataclass(frozen=True, slots=True)
class GovernedServerSettings:
    """Executable process settings layered over secret-free deployment settings."""

    deployment: GovernedDeploymentSettings
    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    observability: ObservabilitySettings | None = None

    def __post_init__(self) -> None:
        """Validate bounded server settings without reading artifacts or secrets."""
        if not isinstance(self.deployment, GovernedDeploymentSettings):
            raise TypeError("deployment must use GovernedDeploymentSettings")
        if (
            not isinstance(self.host, str)
            or not self.host
            or self.host.strip() != self.host
            or len(self.host) > _MAX_HOST_LENGTH
            or any(character.isspace() for character in self.host)
        ):
            raise ValueError("host must be a non-empty normalized host value")
        if isinstance(self.port, bool) or not isinstance(self.port, int):
            raise TypeError("port must be an integer")
        if not 1 <= self.port <= 65_535:
            raise ValueError("port must be between 1 and 65535")
        if self.observability is not None:
            if not isinstance(self.observability, ObservabilitySettings):
                raise TypeError("observability must use ObservabilitySettings")
            if not self.observability.enabled:
                raise ValueError("process-owned observability must be enabled or omitted")
            if self.observability.service_name != _GATEWAY_SERVICE_NAME:
                raise ValueError("observability service_name must use the Gateway process identity")
            if self.observability.service_version != _GATEWAY_SERVICE_VERSION:
                raise ValueError(
                    "observability service_version must use the Gateway process version"
                )
            if self.observability.log_level != _OBSERVABILITY_LOG_LEVEL:
                raise ValueError("observability log_level is owned by the Gateway process")
            if self.observability.log_format != _OBSERVABILITY_LOG_FORMAT:
                raise ValueError("observability log_format is owned by the Gateway process")


def parse_server_args(argv: Sequence[str]) -> GovernedServerSettings:
    """Parse explicit non-secret process arguments into immutable settings."""
    parser = _build_parser()
    args = parser.parse_args(tuple(argv))
    deployment = GovernedDeploymentSettings(
        deployment_root=args.deployment_root,
        model_registry_path=args.model_registry_path,
        provider_runtime_path=args.provider_runtime_path,
        client_auth_path=args.client_auth_path,
        policy_router_path=args.policy_router_path,
        ranking_policy_path=args.ranking_policy_path,
        approved_ranking_artifact_path=args.approved_ranking_artifact_path,
        expected_ranking_artifact_id=args.expected_ranking_artifact_id,
        complexity_routing_path=args.complexity_routing_path,
        default_max_latency_ms=args.default_max_latency_ms,
        default_max_cost_usd=args.default_max_cost_usd,
    )
    return GovernedServerSettings(
        deployment=deployment,
        host=args.host,
        port=args.port,
        observability=_parse_observability_settings(args),
    )


def run_governed_server(
    settings: GovernedServerSettings,
    *,
    environ: Mapping[str, str] | None = None,
    runner: ServerRunner | None = None,
) -> None:
    """Compose the governed application, serve it, and own optional telemetry lifecycle."""
    if not isinstance(settings, GovernedServerSettings):
        raise TypeError("settings must use GovernedServerSettings")
    observability = _configure_observability_best_effort(settings.observability)
    try:
        services = activate_governed_deployment(
            settings.deployment,
            environ=environ,
            observability=observability,
        )
        attach_process_health_routes(services.app)
        selected_runner = UvicornServerRunner() if runner is None else runner
        selected_runner.run(services.app, host=settings.host, port=settings.port)
    finally:
        _shutdown_observability_best_effort(observability)


def main() -> None:
    """Installed console-script entrypoint for the governed Gateway process."""
    run_governed_server(parse_server_args(sys.argv[1:]))


def _parse_observability_settings(args: argparse.Namespace) -> ObservabilitySettings | None:
    endpoint = args.otel_endpoint
    environment = args.otel_environment
    timeout_seconds = args.otel_timeout_seconds
    if endpoint is None and environment is None and timeout_seconds is None:
        return None
    if endpoint is None or environment is None:
        raise ValueError("--otel-endpoint and --otel-environment must be supplied together")
    _require_normalized_observability_value(endpoint, name="--otel-endpoint")
    _require_normalized_observability_value(environment, name="--otel-environment")
    return ObservabilitySettings(
        service_name=_GATEWAY_SERVICE_NAME,
        service_version=_GATEWAY_SERVICE_VERSION,
        environment=environment,
        enabled=True,
        otlp_endpoint=endpoint,
        otlp_timeout_seconds=(
            _DEFAULT_OTLP_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
        ),
        log_level=_OBSERVABILITY_LOG_LEVEL,
        log_format=_OBSERVABILITY_LOG_FORMAT,
    )


def _require_normalized_observability_value(value: str, *, name: str) -> None:
    if not value or value.strip() != value or any(character.isspace() for character in value):
        raise ValueError(f"{name} must be a non-empty normalized value without whitespace")


def _configure_observability_best_effort(
    settings: ObservabilitySettings | None,
) -> Observability | None:
    if settings is None:
        return None
    try:
        return Observability.configure(settings)
    except Exception:
        _LOGGER.warning("Gateway observability configuration failed; continuing without telemetry")
        return None


def _shutdown_observability_best_effort(observability: Observability | None) -> None:
    if observability is None:
        return
    try:
        observability.shutdown(_OBSERVABILITY_SHUTDOWN_TIMEOUT_SECONDS)
    except Exception:
        _LOGGER.warning("Gateway observability shutdown failed; process termination continues")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="governed-llm-gateway",
        description="Start the Governed LLM Gateway from explicit deployment artifacts.",
    )
    parser.add_argument("--deployment-root", required=True, type=Path)
    parser.add_argument("--model-registry-path", required=True, type=Path)
    parser.add_argument("--provider-runtime-path", required=True, type=Path)
    parser.add_argument("--client-auth-path", required=True, type=Path)
    parser.add_argument("--policy-router-path", required=True, type=Path)

    ranking = parser.add_mutually_exclusive_group(required=True)
    ranking.add_argument("--ranking-policy-path", type=Path)
    ranking.add_argument("--approved-ranking-artifact-path", type=Path)
    parser.add_argument("--expected-ranking-artifact-id")
    parser.add_argument("--complexity-routing-path", type=Path)

    parser.add_argument("--default-max-latency-ms", required=True, type=int)
    parser.add_argument("--default-max-cost-usd", required=True, type=Decimal)
    parser.add_argument("--host", default=_DEFAULT_HOST)
    parser.add_argument("--port", default=_DEFAULT_PORT, type=int)
    parser.add_argument("--otel-endpoint")
    parser.add_argument("--otel-environment")
    parser.add_argument("--otel-timeout-seconds", type=float)
    return parser
