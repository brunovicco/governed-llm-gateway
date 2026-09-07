"""Contract tests for the explicit Gateway process entrypoint and server runner boundary."""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from governed_llm_gateway_api.deployment_activation import GovernedDeploymentSettings
from governed_llm_gateway_api import server as server_module
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


def test_console_script_points_to_gateway_main() -> None:
    package_toml = (_ROOT / "apps/gateway-api/pyproject.toml").read_text(encoding="utf-8")

    assert '[project.scripts]' in package_toml
    assert 'governed-llm-gateway = "governed_llm_gateway_api.server:main"' in package_toml


def test_static_cli_parsing_is_deterministic_and_defaults_to_loopback(tmp_path: Path) -> None:
    root = tmp_path.resolve()

    first = parse_server_args(_static_argv(root))
    second = parse_server_args(_static_argv(root))

    assert first == second
    assert first.host == "127.0.0.1"
    assert first.port == 8000
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


def test_secret_values_are_not_accepted_as_cli_arguments(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        parse_server_args(_static_argv(tmp_path.resolve()) + ["--provider-api-key", "secret"])


def test_server_settings_reject_invalid_host_and_port_before_activation(tmp_path: Path) -> None:
    deployment = _deployment(tmp_path.resolve())

    with pytest.raises(ValueError, match="host must be"):
        GovernedServerSettings(deployment=deployment, host=" bad-host ")
    with pytest.raises(ValueError, match="port must be between"):
        GovernedServerSettings(deployment=deployment, port=0)


def test_injected_runner_receives_composed_app_without_socket_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    runner = RecordingRunner()
    deployment = _deployment(tmp_path.resolve())
    settings = GovernedServerSettings(deployment=deployment, host="localhost", port=8123)
    seen: list[GovernedDeploymentSettings] = []

    def fake_activate(
        value: GovernedDeploymentSettings,
        *,
        environ: object = None,
    ) -> SimpleNamespace:
        seen.append(value)
        return SimpleNamespace(app=app)

    monkeypatch.setattr(server_module, "activate_governed_deployment", fake_activate)

    run_governed_server(settings, environ={}, runner=runner)

    assert seen == [deployment]
    assert runner.app is app
    assert runner.host == "localhost"
    assert runner.port == 8123


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

    monkeypatch.setattr(server_module.uvicorn, "run", fake_uvicorn_run)

    UvicornServerRunner().run(app, host="127.0.0.1", port=8000)

    assert calls == [(app, "127.0.0.1", 8000, 1)]
