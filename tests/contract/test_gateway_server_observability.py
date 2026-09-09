"""Contract tests for executable-process observability ownership and degradation."""

from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from a2a_otel_kit.application.settings import ObservabilitySettings
from a2a_otel_kit.domain.errors import InvalidObservabilityConfigurationError
from a2a_otel_kit.entrypoints.observability import Observability
from fastapi import FastAPI
from governed_llm_gateway_api import server as server_module
from governed_llm_gateway_api.deployment_activation import GovernedDeploymentSettings
from governed_llm_gateway_api.server import parse_server_args, run_governed_server


class RecordingRunner:
    """Capture whether the already-composed application reached the runner."""

    def __init__(self) -> None:
        self.app: FastAPI | None = None

    def run(self, app: FastAPI, *, host: str, port: int) -> None:
        del host, port
        self.app = app


class RaisingRunner:
    """Raise one stable error after process composition."""

    def run(self, app: FastAPI, *, host: str, port: int) -> None:
        del app, host, port
        raise RunnerError("runner failed")


class RunnerError(RuntimeError):
    """Stable runner sentinel."""


class ActivationError(RuntimeError):
    """Stable activation sentinel."""


class RecordingObservability:
    """Minimal lifecycle double used behind an explicit test cast."""

    def __init__(self, *, fail_shutdown: bool = False) -> None:
        self.shutdown_calls: list[float] = []
        self.fail_shutdown = fail_shutdown

    def shutdown(self, timeout_seconds: float = 5.0) -> None:
        self.shutdown_calls.append(timeout_seconds)
        if self.fail_shutdown:
            raise RuntimeError("raw shutdown detail")


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


@pytest.mark.parametrize(
    "extra",
    [
        ["--otel-endpoint", "http://127.0.0.1:4318/v1/traces"],
        ["--otel-environment", "test"],
        ["--otel-timeout-seconds", "2.0"],
    ],
)
def test_partial_observability_cli_fails_before_process_activation(
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
    invalid_timeout = _otel_argv(root)
    invalid_timeout[-1] = "0"

    with pytest.raises(InvalidObservabilityConfigurationError):
        parse_server_args(invalid_endpoint)
    with pytest.raises(ValueError, match="normalized value"):
        parse_server_args(invalid_environment)
    with pytest.raises(InvalidObservabilityConfigurationError):
        parse_server_args(invalid_timeout)


def test_explicit_observability_settings_override_ambient_a2a_values(
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
    assert observability.service_version == "1.0.0"
    assert observability.environment == "test"
    assert observability.enabled is True
    assert observability.otlp_endpoint == "http://127.0.0.1:4318/v1/traces"
    assert observability.otlp_timeout_seconds == 3.5
    assert observability.log_level == "INFO"
    assert observability.log_format == "json"


def test_enabled_observability_is_injected_and_shutdown_after_runner_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    runner = RecordingRunner()
    settings = parse_server_args(_otel_argv(tmp_path.resolve()))
    fake_observability = RecordingObservability()
    expected_observability = cast(Observability, fake_observability)
    configured: list[ObservabilitySettings] = []
    injected: list[Observability | None] = []

    def fake_configure(value: ObservabilitySettings) -> Observability:
        configured.append(value)
        return expected_observability

    def fake_activate(
        value: GovernedDeploymentSettings,
        *,
        environ: Mapping[str, str] | None = None,
        observability: Observability | None = None,
    ) -> SimpleNamespace:
        del value, environ
        injected.append(observability)
        return SimpleNamespace(app=app)

    monkeypatch.setattr(Observability, "configure", staticmethod(fake_configure))
    monkeypatch.setattr(server_module, "activate_governed_deployment", fake_activate)

    run_governed_server(settings, environ={}, runner=runner)

    assert configured == [settings.observability]
    assert injected == [expected_observability]
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

    monkeypatch.setattr(Observability, "configure", staticmethod(fake_configure))
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
    expected_observability = cast(Observability, fake_observability)

    def fake_configure(value: ObservabilitySettings) -> Observability:
        del value
        return expected_observability

    def fake_activate(
        value: GovernedDeploymentSettings,
        *,
        environ: Mapping[str, str] | None = None,
        observability: Observability | None = None,
    ) -> SimpleNamespace:
        del value, environ
        assert observability is expected_observability
        raise ActivationError("activation failed")

    monkeypatch.setattr(Observability, "configure", staticmethod(fake_configure))
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
    expected_observability = cast(Observability, fake_observability)
    app = FastAPI()

    def fake_configure(value: ObservabilitySettings) -> Observability:
        del value
        return expected_observability

    def fake_activate(
        value: GovernedDeploymentSettings,
        *,
        environ: Mapping[str, str] | None = None,
        observability: Observability | None = None,
    ) -> SimpleNamespace:
        del value, environ
        assert observability is expected_observability
        return SimpleNamespace(app=app)

    monkeypatch.setattr(Observability, "configure", staticmethod(fake_configure))
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
    expected_observability = cast(Observability, fake_observability)
    app = FastAPI()
    runner = RecordingRunner()

    def fake_configure(value: ObservabilitySettings) -> Observability:
        del value
        return expected_observability

    def fake_activate(
        value: GovernedDeploymentSettings,
        *,
        environ: Mapping[str, str] | None = None,
        observability: Observability | None = None,
    ) -> SimpleNamespace:
        del value, environ
        assert observability is expected_observability
        return SimpleNamespace(app=app)

    monkeypatch.setattr(Observability, "configure", staticmethod(fake_configure))
    monkeypatch.setattr(server_module, "activate_governed_deployment", fake_activate)

    run_governed_server(settings, environ={}, runner=runner)

    assert fake_observability.shutdown_calls == [5.0]
    assert runner.app is app
