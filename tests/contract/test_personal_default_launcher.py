"""Contract tests for deterministic personal-default local orchestration."""

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from scripts import personal_default_launcher as launcher_module

_GATEWAY_KEY = "test-only-gateway-demo-key"
_POLICY_ROUTER_KEY = "test-only-policy-router-demo-key"
_REPO_ROOT = Path(launcher_module.__file__).resolve().parents[1]
_POLICY_ROUTER_ROOT = _REPO_ROOT.parent / "policy-model-router"


class FakeProcess:
    """Minimal controllable owned-child process."""

    def __init__(self, exit_code: int | None = None) -> None:
        self.exit_code = exit_code

    def poll(self) -> int | None:
        return self.exit_code


class FakeRuntime:
    """Deterministic side-effect recorder for the personal-default launcher."""

    def __init__(self, *, second_child_exit_code: int | None = None) -> None:
        self.start_calls: list[tuple[tuple[str, ...], Path, dict[str, str]]] = []
        self.started_processes: list[FakeProcess] = []
        self.stopped: list[FakeProcess] = []
        self.clock = 0.0
        self._second_child_exit_code = second_child_exit_code

    def start(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
    ) -> FakeProcess:
        normalized = tuple(command)
        self.start_calls.append((normalized, cwd, dict(env)))
        exit_code = self._second_child_exit_code if len(self.start_calls) == 2 else None
        process = FakeProcess(exit_code)
        self.started_processes.append(process)
        return process

    def stop(self, process: launcher_module.LauncherProcess) -> None:
        assert isinstance(process, FakeProcess)
        self.stopped.append(process)

    def get_json(self, url: str) -> object:
        if url == "http://127.0.0.1:8001/readyz":
            return {"status": "ready"}
        if url == "http://127.0.0.1:8000/readyz":
            return {"status": "ready"}
        raise AssertionError(f"unexpected JSON probe: {url}")

    def monotonic(self) -> float:
        return self.clock

    def sleep(self, seconds: float) -> None:
        self.clock += seconds


def _settings(
    policy_router_root: Path = _POLICY_ROUTER_ROOT,
) -> launcher_module.PersonalDefaultSettings:
    return launcher_module.PersonalDefaultSettings(
        repository_root=_REPO_ROOT,
        policy_router_root=policy_router_root,
        smoke_test=True,
    )


def _environ() -> dict[str, str]:
    return {
        "PATH": "/test/bin",
        "HOME": "/test/home",
        "GATEWAY_DEMO_API_KEY": _GATEWAY_KEY,
        "POLICY_ROUTER_DEMO_API_KEY": _POLICY_ROUTER_KEY,
        "NVIDIA_API_KEY": "test-only-nvidia-key",
    }


def test_smoke_test_starts_policy_router_then_gateway_and_cleans_up_in_reverse(
    tmp_path: Path,
) -> None:
    policy_router_root = tmp_path / "policy-model-router"
    policy_router_root.mkdir()
    runtime = FakeRuntime()
    launcher = launcher_module.PersonalDefaultLauncher(
        _settings(policy_router_root),
        runtime=runtime,
        environ=_environ(),
    )

    launcher.run()

    assert len(runtime.start_calls) == 2

    policy_router_command, policy_router_cwd, policy_router_env = runtime.start_calls[0]
    gateway_command, gateway_cwd, gateway_env = runtime.start_calls[1]

    assert policy_router_command[:3] == ("uv", "run", "uvicorn")
    assert policy_router_cwd == policy_router_root
    assert policy_router_env["APP_ENV"] == "development"
    assert policy_router_env["ROUTING_POLICY_PATH"] == str(
        policy_router_root / "examples" / "policies" / "gateway-generic.yaml"
    )
    assert json.loads(policy_router_env["API_KEYS"]) == {"gateway-demo": _POLICY_ROUTER_KEY}

    assert gateway_command[-1] == "8000"
    assert "personal-default" in " ".join(gateway_command)
    assert gateway_cwd == _REPO_ROOT
    assert gateway_env["GATEWAY_DEMO_API_KEY"] == _GATEWAY_KEY
    assert gateway_env["NVIDIA_API_KEY"] == "test-only-nvidia-key"

    # Cleanup stops the Gateway (started second) before the Policy Router (started first).
    assert runtime.stopped == list(reversed(runtime.started_processes))


def test_missing_gateway_credential_fails_before_any_side_effect() -> None:
    runtime = FakeRuntime()
    environ = _environ()
    del environ["GATEWAY_DEMO_API_KEY"]

    with pytest.raises(launcher_module.PersonalDefaultPrerequisiteError) as exc_info:
        launcher_module.PersonalDefaultLauncher(_settings(), runtime=runtime, environ=environ)

    assert "GATEWAY_DEMO_API_KEY" in str(exc_info.value)
    assert runtime.start_calls == []


def test_missing_policy_router_credential_fails_before_any_side_effect() -> None:
    runtime = FakeRuntime()
    environ = _environ()
    del environ["POLICY_ROUTER_DEMO_API_KEY"]

    with pytest.raises(launcher_module.PersonalDefaultPrerequisiteError) as exc_info:
        launcher_module.PersonalDefaultLauncher(_settings(), runtime=runtime, environ=environ)

    assert "POLICY_ROUTER_DEMO_API_KEY" in str(exc_info.value)
    assert runtime.start_calls == []


def test_missing_policy_router_root_fails_closed() -> None:
    runtime = FakeRuntime()
    settings = launcher_module.PersonalDefaultSettings(
        repository_root=_REPO_ROOT,
        policy_router_root=_REPO_ROOT / "does-not-exist",
        smoke_test=True,
    )
    launcher = launcher_module.PersonalDefaultLauncher(
        settings, runtime=runtime, environ=_environ()
    )

    with pytest.raises(launcher_module.PersonalDefaultPrerequisiteError) as exc_info:
        launcher.run()

    assert "policy-model-router root does not exist" in str(exc_info.value)
    assert runtime.start_calls == []


def test_owned_child_exit_fails_closed_and_still_tears_down(tmp_path: Path) -> None:
    policy_router_root = tmp_path / "policy-model-router"
    policy_router_root.mkdir()
    runtime = FakeRuntime(second_child_exit_code=7)
    launcher = launcher_module.PersonalDefaultLauncher(
        _settings(policy_router_root),
        runtime=runtime,
        environ=_environ(),
    )

    with pytest.raises(launcher_module.PersonalDefaultChildExitedError) as exc_info:
        launcher.run()

    assert "exit 7" in str(exc_info.value)
    assert len(runtime.stopped) == 2


def test_policy_router_root_resolution_prefers_explicit_then_env_then_sibling_default() -> None:
    explicit = launcher_module.PersonalDefaultSettings(
        repository_root=_REPO_ROOT,
        policy_router_root=Path("/explicit/policy-router"),
    )
    assert launcher_module._resolve_policy_router_root(explicit, {}) == Path(
        "/explicit/policy-router"
    )

    via_env = launcher_module.PersonalDefaultSettings(repository_root=_REPO_ROOT)
    assert launcher_module._resolve_policy_router_root(
        via_env, {"POLICY_MODEL_ROUTER_ROOT": "/env/policy-router"}
    ) == Path("/env/policy-router")

    default = launcher_module.PersonalDefaultSettings(repository_root=_REPO_ROOT)
    assert (
        launcher_module._resolve_policy_router_root(default, {})
        == _REPO_ROOT.parent / "policy-model-router"
    )


def test_http_probe_boundary_rejects_external_or_non_reviewed_ports() -> None:
    launcher_module._require_reviewed_loopback_url("http://127.0.0.1:8000/readyz")
    launcher_module._require_reviewed_loopback_url("http://127.0.0.1:8001/readyz")

    with pytest.raises(launcher_module.PersonalDefaultProbeUnavailable):
        launcher_module._require_reviewed_loopback_url("https://example.com/readyz")
    with pytest.raises(launcher_module.PersonalDefaultProbeUnavailable):
        launcher_module._require_reviewed_loopback_url("http://127.0.0.1:9999/readyz")
    with pytest.raises(launcher_module.PersonalDefaultProbeUnavailable):
        launcher_module._require_reviewed_loopback_url("http://127.0.0.1:8000/readyz?x=1")


def test_cli_surface_only_exposes_smoke_test_switch() -> None:
    settings = launcher_module.parse_args(["--smoke-test"])

    assert settings.smoke_test is True
    assert settings.repository_root == _REPO_ROOT
    assert settings.policy_router_root is None
