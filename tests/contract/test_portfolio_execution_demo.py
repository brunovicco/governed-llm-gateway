import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml  # type: ignore[import-untyped]
from fastapi.routing import APIRoute

from scripts import portfolio_execution_demo as demo
from scripts.portfolio_execution_demo import (
    _PRIMARY,
    _SECONDARY,
    _UNAUTHORIZED,
    ScenarioResult,
    _build_services,
    _payload,
    _SimulatedProvider,
    _teardown_compose,
)


def test_execution_fixture_composes_real_gateway_services_without_provider_secrets(
    tmp_path: Path,
) -> None:
    services = _build_services(
        tmp_path / "runtime",
        "https://127.0.0.1:44443/route",
        _SimulatedProvider(),
    )

    routes = {route.path for route in services.app.routes if isinstance(route, APIRoute)}
    assert "/v1/generate" in routes
    assert services.generate_coordinator is not None
    assert services.streaming_service is not None
    assert len(services.operations_read_model._registry.deployments) == 3
    assert {
        deployment.deployment_id
        for deployment in services.operations_read_model._registry.deployments
    } == {_PRIMARY, _SECONDARY, _UNAUTHORIZED}


def test_demo_request_has_no_caller_controlled_deployment_selector() -> None:
    payload = _payload()

    assert "model" not in payload
    assert "deployment_id" not in payload
    assert "provider" not in payload


def test_demo_compose_uses_ephemeral_pdp_credential(tmp_path: Path) -> None:
    key_file = tmp_path / "runtime-keys.json"
    compose_file = demo._compose_document(51234, key_file, "per-run-router-key")
    try:
        router = yaml.safe_load(compose_file.read_text(encoding="utf-8"))["services"][
            "policy-model-router"
        ]
    finally:
        compose_file.unlink()

    assert router["ports"] == ["127.0.0.1:51234:8000"]
    assert json.loads(router["environment"]["API_KEYS"]) == {
        "composition-proof-client": "per-run-router-key"
    }
    assert demo._GATEWAY_KEY != "local-demo-gateway-key"
    assert demo._PDP_API_KEY != "composition-proof-api-key"


def test_teardown_removes_compose_containers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(shutil, "which", lambda executable: executable)

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        del kwargs
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(subprocess, "run", run)

    assert _teardown_compose(["docker", "compose", "-p", "demo"])
    assert calls[0][-3:] == ["down", "--volumes", "--remove-orphans"]
    assert calls[1][-3:] == ["ps", "--all", "--quiet"]
    assert calls[2][:3] == ["docker", "network", "ls"]
    assert calls[3][:3] == ["docker", "volume", "ls"]


def test_teardown_fails_if_compose_still_reports_containers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda executable: executable)
    results = iter(
        [
            SimpleNamespace(returncode=0, stdout=""),
            SimpleNamespace(returncode=0, stdout="demo-container-id\n"),
            SimpleNamespace(returncode=0, stdout=""),
            SimpleNamespace(returncode=0, stdout=""),
        ]
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(results))

    assert not _teardown_compose(["docker", "compose", "-p", "demo"])


@pytest.mark.parametrize("outcome", ["success", "unexpected", "failure", "interrupt"])
def test_demo_always_tears_down_after_success_failure_or_interrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(shutil, "which", lambda executable: executable)
    monkeypatch.setattr(demo, "_ROUTER_PATH", tmp_path)
    monkeypatch.setattr(demo, "verify_router_revision", lambda path: "a" * 40)
    monkeypatch.setattr(demo, "_free_loopback_port", lambda: 54321)
    monkeypatch.setattr(demo, "_wait_router", lambda port: None)

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        del kwargs
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(subprocess, "run", run)

    class Proxy:
        endpoint = "https://127.0.0.1:54322/route"

        def __enter__(self) -> "Proxy":
            return self

        def __exit__(self, *args: object) -> None:
            del args

    monkeypatch.setattr(demo, "LocalVerifiedHttpsProxy", lambda **kwargs: Proxy())

    def scenario(name: str, behavior: str, directory: Path, endpoint: str) -> ScenarioResult:
        del behavior, directory, endpoint
        if outcome == "failure":
            raise RuntimeError("injected scenario exception")
        if outcome == "interrupt":
            raise KeyboardInterrupt
        return ScenarioResult(name, outcome != "unexpected", "fixture result", {}, {}, {})

    monkeypatch.setattr(demo, "_scenario", scenario)
    if outcome == "failure":
        with pytest.raises(RuntimeError, match="injected scenario exception"):
            demo.run_demo()
    elif outcome == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            demo.run_demo()
    else:
        assert demo.run_demo() == (1 if outcome == "unexpected" else 0)

    assert commands[-4][-3:] == ["down", "--volumes", "--remove-orphans"]
    assert commands[-3][-3:] == ["ps", "--all", "--quiet"]
    assert commands[-2][:3] == ["docker", "network", "ls"]
    assert commands[-1][:3] == ["docker", "volume", "ls"]
