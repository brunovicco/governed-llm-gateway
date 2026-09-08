"""Contract tests for the explicit Gateway process entrypoint and server runner boundary."""

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import uvicorn
from a2a_otel_kit.application.settings import ObservabilitySettings
from a2a_otel_kit.entrypoints.observability import Observability
from fastapi import FastAPI
from fastapi.routing import APIRoute
from governed_llm_gateway_api import server as server_module
from governed_llm_gateway_api.deployment_activation import GovernedDeploymentSettings
from governed_llm_gateway_api.server import (
    GovernedServerSettings,
    UvicornServerRunner,
    parse_server_args,
    run_governed_server,
)

_ROOT = Path(__file__).resolve().parents[2]


class RecordingRunner:
    """Capture one server invocation without binding a socket."""

    def __init__(self) -> None:
        self.app: FastAPI | None = None
        self.host: str | None = None
        self.port: int | None = None

    def run(self, app: FastAPI, *, host: str, port: int) -> None:
        self.app = app
        self.host = host
        self.port = port


class RaisingRunner:
    """Raise one stable runner error after the application is composed."""

    def run(self, app: FastAPI, *, host: str, port: int) -> None:
        del app, host, port
        raise RunnerError("runner failed")


class RunnerError(RuntimeError):
    """Stable runner sentinel for lifecycle tests."""


class ActivationError(RuntimeError):
    """Stable activation sentinel for lifecycle tests."""


class RecordingObservability:
    """Minimal lifecycle double cast to the concrete observability facade in tests."""

    def __init__(self, *, fail_shutdown: bool = False) -> None:
        self.shutdown_calls: list[float] = []
        self.fail_shutdown = fail_shutdown

    def shutdown(self, timeout_seconds: float = 5.0) -> None:
        self.shutdown_calls.append(timeout_seconds)
        if self.fail_shutdown:
            raise RuntimeError("raw shutdown detail")


def _deployment(root: Path) -> GovernedDeploymentSettings:
    return GovernedDeploymentSettings(
        deployment_root=root,
        model_registry_path=Path("config/model-registry.yaml"),
        provider_runtime_path=Path("config/provider-runtime.json"),
        client_auth_path=Path("config/client-auth.json"),
        policy_router_path=Path("config/policy-router.json"),
        ranking_policy_path=Path("config/ranking.yaml"),
        default_max_latency_ms=5_000,
        default_max_cost_usd=Decimal("1.25"),
    )


def _static_argv(root: Path) -> list[str]:
    return [
        "--deployment-root",
        str(root),
        "--model-registry-path",
        "config/model-registry.yaml",
        "--provider-runtime-path",
        "config/provider-runtime.json",
        "--client-auth-path",
        "config/client-auth.json",
        "--policy-router-path",
        "config/policy-router.json",
        "--ranking-policy-path",
        "config/ranking.yaml",
        "--default-max-latency-ms",
        "5000",
        "--default-max-cost-usd",
        "1.25",
    ]


def _otel_argv(root: Path) -> list[str]:
    return [
        *_static_argv(root),
        "--otel-endpoint",
        "http://127.0.0.1:4318/v1/traces",
        "--otel-environment",
        "test",
        "--otel-timeout-seconds",
        "3.5",
    ]


def test_console_script_points_to_gateway_main() -> None:
    package_toml = (_ROOT / "apps/gateway-api/pyproject.toml").read_text(encoding="utf-8")

    assert "[project.scripts]" in package_toml
    assert 'governed-llm-gateway = "governed_llm_gateway_api.server:main"' in package_toml


def test_static_cli_parsing_is_deterministic_and_defaults_to_loopback(tmp_path: Path) -> None:
    root = tmp_path.resolve()

    first = parse_server_args(_static_argv(root))
    second = parse_server_args(_static_argv(root))

    assert first == second
    assert first.host == "127.0.0.1"
    assert first.port == 8000
    assert first.observability is None
    assert first.deployment.deployment_root == root
    assert first.deployment.ranking_policy_path == Path("config/ranking.yaml")
    assert first.deployment.approved_ranking_artifact_path is None
    assert first.deployment.default_max_latency_ms == 5_000
    assert first.deployment.default_max_cost_usd == Decimal("1.25")


def test_approved_cli_requires_exact_expected_artifact_identity(tmp_path: Path) -> None:
    argv = _static_argv(tmp_path.resolve())
    ranking_index = argv.index("--ranking-policy-path")
    argv[ranking_index : ranking_index + 2] = [
        "--approved-ranking-artifact-path",
        "config/approved-ranking.json",
    ]

    with pytest.raises(ValueError, match="must be supplied together"):
        parse_server_args(argv)

    expected_id = "sha256:" + "a" * 64
    argv.extend(["--expected-ranking-artifact-id", expected_id])
    settings = parse_server_args(argv)

    assert settings.deployment.ranking_policy_path is None
    assert settings.deployment.approved_ranking_artifact_path == Path(
        "config/approved-ranking.json"
    )
    assert settings.deployment.expected_ranking_artifact_id == expected_id


@pytest.mark.parametrize(
    "extra",
    [
        ["--provider-api-key", "secret"],
        ["--otel-headers", "Authorization=secret"],
        ["--otel-api-key", "secret"],
    ],
)
def test_secret_values_are_not_accepted_as_cli_arguments(
    tmp_path: Path,
    extra: list[str],
) -> None:
    argv = [*_static_argv(tmp_path.resolve()), *extra]

    with pytest.raises(SystemExit):
        parse_server_args(argv)


def test_server_settings_reject_invalid_host_and_port_before_activation(tmp_path: Path) -> None:
    deployment = _deployment(tmp_path.resolve())

    with pytest.raises(ValueError, match="host must be"):
        GovernedServerSettings(deployment=deployment, host=" bad-host ")
    with pytest.raises(ValueError, match="port must be between"):
        GovernedServerSettings(deployment=deployment, port=0)


@pytest.mark.parametrize(
    "extra",
    [
        ["--otel-endpoint", "http://127.0.0.1:4318/v1/traces"],
        ["--otel-environment", "test"],
        ["--otel-timeout-seconds", "2.0"],
    ],
)
def test_partial_observability_cli_fails_before_activation(
    tmp_path: Path,
    extra: list[str],
) -> None:
    with pytest.raises(ValueError, match="must be supplied together"):
        parse_server_args([*_static_argv(tmp_path.resolve()), *extra])


def test_invalid_observability_values_fail_during_cli_parsing(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    invalid_endpoint = [
        *_static_argv(root),
        "--otel-endpoint",
        "grpc://collector:4317",
        "--otel-environment",
        "test",
    ]
    invalid_environment = [
        *_static_argv(root),
        "--otel-endpoint",
        "http://127.0.0.1:4318/v1/traces",
        "--otel-environment",
        " bad env ",
    ]
    invalid_timeout = [*_otel_argv(root[:-0] if False else root)]
    invalid_timeout[-1] = "0"

    with pytest.raises(ValueError):
        parse_server_args(invalid_endpoint)
    with pytest.raises(ValueError, match="normalized value"):
        parse_server_args(invalid_environment)
    with pytest.raises(ValueError):
        parse_server_args(invalid_timeout)


def test_explicit_observability_settings_ignore_ambient_a2a_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("A2A_OTEL_SERVICE_NAME", "ambient-service")
    monkeypatch.setenv("A2A_OTEL_SERVICE_VERSION", "999")
    monkeypatch.setenv("A2A_OTEL_ENVIRONMENT", "ambient")
    monkeypatch.setenv("A2A_OTEL_ENABLED", "false")
    monkeypatch.setenv("A2A_OTEL_OTLP_ENDPOINT", "https://ambient.example/v1/traces")
    monkeypatch.setenv("A2A_OTEL_OTLP_TIMEOUT_SECONDS", "99")
    monkeypatch.setenv("A2A_OTEL_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("A2A_OTEL_LOG_FORMAT", "console")

    settings = parse_server_args(_otel_argv(tmp_path.resolve()))
    observability = settings.observability

    assert observability is not None
    assert observability.service_name == "governed-llm-gateway"
    assert observability.service_version == "0.1.0"
    assert observability.environment == "test"
    assert observability.enabled is True
    assert observability.otlp_endpoint == "http://127.0.0.1:4318/v1/traces"
    assert observability.otlp_timeout_seconds == 3.5
    assert observability.log_level == "INFO"
    assert observability.log_format == "json"


def test_injected_runner_receives_composed_app_without_socket_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    runner = RecordingRunner()
    deployment = _deployment(tmp_path.resolve())
    settings = GovernedServerSettings(deployment=deployment, host="localhost", port=8123)
    seen: list[tuple[GovernedDeploymentSettings, Observability | None]] = []

    def fake_configure(settings: ObservabilitySettings) -> Observability:
        pytest.fail(f"observability must stay disabled by default: {settings}")

    def fake_activate(
        value: GovernedDeploymentSettings,
        *,
        environ: Mapping[str, str] | None = None,
        observability: Observability | None = None,
    ) -> SimpleNamespace:
        del environ
        seen.append((value, observability))
        return SimpleNamespace(app=app)

    monkeypatch.setattr(server_module.Observability, "configure", staticmethod(fake_configure))
    monkeypatch.setattr(server_module, "activate_governed_deployment", fake_activate)

    run_governed_server(settings, environ={}, runner=runner)

    assert seen == [(deployment, None)]
    assert runner.app is app
    assert runner.host == "localhost"
    assert runner.port == 8123
    route_paths = [route.path for route in app.routes if isinstance(route, APIRoute)]
    assert route_paths.count("/livez") == 1
    assert route_paths.count("/readyz") == 1


def test_enabled_observability_is_injected_and_shutdown_after_runner_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    runner = RecordingRunner()
    settings = parse_server_args(_otel_argv(tmp_path.resolve()))
    fake_observability = RecordingObservability()
    configured: list[ObservabilitySettings] = []
    injected: list[Observability | None] = []

    def fake_configure(value: ObservabilitySettings) -> Observability:
        configured.append(value)
        return cast(Observability, fake_observability)

    def fake_activate(
        value: GovernedDeploymentSettings,
        *,
        environ: Mapping[str, str] | None = None,
        observability: Observability | None = None,
    ) -> SimpleNamespace:
        del value, environ
        injected.append(observability)
        return SimpleNamespace(app=app)

    monkeypatch.setattr(server_module.Observability, "configure", staticmethod(fake_configure))
    monkeypatch.setattr(server_module, "activate_governed_deployment", fake_activate)

    run_governed_server(settings, environ={}, runner=runner)

    assert configured == [settings.observability]
    assert injected == [cast(Observability, fake_observability)]
    assert fake_observability.shutdown_calls == [5.0]
    assert runner.app is app


def test_observability_configuration_failure_degrades_to_null_telemetry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = FastAPI()
    runner = RecordingRunner()
    settings = parse_server_args(_otel_argv(tmp_path.resolve()))
    injected: list[Observability | None] = []

    def fake_configure(value: ObservabilitySettings) -> Observability:
        del value
        raise RuntimeError("raw configure detail")

    def fake_activate(
        value: GovernedDeploymentSettings,
        *,
        environ: Mapping[str, str] | None = None,
        observability: Observability | None = None,
    ) -> SimpleNamespace:
        del value, environ
        injected.append(observability)
        return SimpleNamespace(app=app)

    monkeypatch.setattr(server_module.Observability, "configure", staticmethod(fake_configure))
    monkeypatch.setattr(server_module, "activate_governed_deployment", fake_activate)

    run_governed_server(settings, environ={}, runner=runner)

    assert injected == [None]
    assert runner.app is app
    assert "Gateway observability configuration failed" in caplog.text
    assert "raw configure detail" not in caplog.text


def test_activation_failure_still_shuts_down_owned_observability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = parse_server_args(_otel_argv(tmp_path.resolve()))
    fake_observability = RecordingObservability()

    def fake_configure(value: ObservabilitySettings) -> Observability:
        del value
        return cast(Observability, fake_observability)

    def fake_activate(
        value: GovernedDeploymentSettings,
        *,
        environ: Mapping[str, str] | None = None,
        observability: Observability | None = None,
    ) -> SimpleNamespace:
        del value, environ
        assert observability is cast(Observability, fake_observability)
        raise ActivationError("activation failed")

    monkeypatch.setattr(server_module.Observability, "configure", staticmethod(fake_configure))
    monkeypatch.setattr(server_module, "activate_governed_deployment", fake_activate)

    with pytest.raises(ActivationError, match="activation failed"):
        run_governed_server(settings, environ={}, runner=RecordingRunner())

    assert fake_observability.shutdown_calls == [5.0]


def test_shutdown_failure_never_masks_runner_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = parse_server_args(_otel_argv(tmp_path.resolve()))
    fake_observability = RecordingObservability(fail_shutdown=True)
    app = FastAPI()

    def fake_configure(value: ObservabilitySettings) -> Observability:
        del value
        return cast(Observability, fake_observability)

    def fake_activate(
        value: GovernedDeploymentSettings,
        *,
        environ: Mapping[str, str] | None = None,
        observability: Observability | None = None,
    ) -> SimpleNamespace:
        del value, environ
        assert observability is cast(Observability, fake_observability)
        return SimpleNamespace(app=app)

    monkeypatch.setattr(server_module.Observability, "configure", staticmethod(fake_configure))
    monkeypatch.setattr(server_module, "activate_governed_deployment", fake_activate)

    with pytest.raises(RunnerError, match="runner failed"):
        run_governed_server(settings, environ={}, runner=RaisingRunner())

    assert fake_observability.shutdown_calls == [5.0]
    assert "Gateway observability shutdown failed" in caplog.text
    assert "raw shutdown detail" not in caplog.text


def test_shutdown_failure_after_normal_runner_return_is_best_effort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = parse_server_args(_otel_argv(tmp_path.resolve()))
    fake_observability = RecordingObservability(fail_shutdown=True)
    app = FastAPI()
    runner = RecordingRunner()

    def fake_configure(value: ObservabilitySettings) -> Observability:
        del value
        return cast(Observability, fake_observability)

    def fake_activate(
        value: GovernedDeploymentSettings,
        *,
        environ: Mapping[str, str] | None = None,
        observability: Observability | None = None,
    ) -> SimpleNamespace:
        del value, environ, observability
        return SimpleNamespace(app=app)

    monkeypatch.setattr(server_module.Observability, "configure", staticmethod(fake_configure))
    monkeypatch.setattr(server_module, "activate_governed_deployment", fake_activate)

    run_governed_server(settings, environ={}, runner=runner)

    assert fake_observability.shutdown_calls == [5.0]
    assert runner.app is app


def test_uvicorn_runner_delegates_single_worker_without_global_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    calls: list[tuple[FastAPI, str, int, int]] = []

    def fake_uvicorn_run(
        candidate: FastAPI,
        *,
        host: str,
        port: int,
        workers: int,
    ) -> None:
        calls.append((candidate, host, port, workers))

    monkeypatch.setattr(uvicorn, "run", fake_uvicorn_run)

    UvicornServerRunner().run(app, host="127.0.0.1", port=8000)

    assert calls == [(app, "127.0.0.1", 8000, 1)]
