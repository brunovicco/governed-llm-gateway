"""Contract tests for deterministic PC-30 local demo orchestration."""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from scripts import local_demo

_TEST_KEY = "test-only-pc30-runtime-key"


class FakeProcess:
    """Minimal controllable owned-child process."""

    def __init__(self, exit_code: int | None = None) -> None:
        self.exit_code = exit_code

    def poll(self) -> int | None:
        return self.exit_code


class FakeRuntime:
    """Deterministic side-effect recorder for the local demo launcher."""

    def __init__(self, *, second_child_exit_code: int | None = None) -> None:
        self.required: list[str] = []
        self.run_calls: list[tuple[tuple[str, ...], Path, dict[str, str], bool]] = []
        self.start_calls: list[tuple[tuple[str, ...], Path, dict[str, str]]] = []
        self.stopped: list[FakeProcess] = []
        self.clock = 0.0
        self._second_child_exit_code = second_child_exit_code

    def require_executable(self, name: str) -> None:
        self.required.append(name)

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        capture_output: bool = False,
    ) -> str:
        normalized = tuple(command)
        self.run_calls.append((normalized, cwd, dict(env), capture_output))
        if "ps" in normalized:
            return "otel-collector\ntempo\ngrafana\n"
        return ""

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
        return FakeProcess(exit_code)

    def stop(self, process: local_demo.DemoProcess) -> None:
        assert isinstance(process, FakeProcess)
        self.stopped.append(process)

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        if url == "http://127.0.0.1:8000/readyz":
            assert headers is None
            return {"status": "ready"}
        if url == "http://127.0.0.1:8000/v1/ops/overview":
            assert headers == {"X-Gateway-API-Key": _TEST_KEY}
            return {
                "registry": {"deployment_count": 0},
                "health": {"scope": "process_local", "deployment_count": 0},
                "operational_evidence": {"state": "not_supplied"},
            }
        if url == "http://127.0.0.1:3000/api/health":
            assert headers is None
            return {"database": "ok"}
        raise AssertionError(f"unexpected JSON probe: {url}")

    def get_text(self, url: str) -> str:
        assert url == "http://127.0.0.1:5173/"
        return '<!doctype html><div id="root"></div>'

    def monotonic(self) -> float:
        return self.clock

    def sleep(self, seconds: float) -> None:
        self.clock += seconds


def _settings() -> local_demo.LocalDemoSettings:
    return local_demo.LocalDemoSettings(
        repository_root=Path(__file__).resolve().parents[2],
        smoke_test=True,
    )


def _environ() -> dict[str, str]:
    return {
        "PATH": "/test/bin",
        "HOME": "/test/home",
        "GATEWAY_LOCAL_DEMO_API_KEY": _TEST_KEY,
    }


def test_smoke_test_isolates_credential_and_cleans_all_owned_components() -> None:
    runtime = FakeRuntime()
    launcher = local_demo.LocalDemoLauncher(
        _settings(),
        runtime=runtime,
        environ=_environ(),
    )

    launcher.run()

    assert runtime.required == ["docker", "npm", "uv"]
    assert len(runtime.start_calls) == 2

    gateway_command, _, gateway_env = runtime.start_calls[0]
    console_command, _, console_env = runtime.start_calls[1]
    assert gateway_command[-1] == "governed-llm-gateway-operations-demo"
    assert "governed-llm-gateway" not in gateway_command
    assert gateway_env["GATEWAY_LOCAL_DEMO_API_KEY"] == _TEST_KEY
    assert console_command == ("npm", "run", "dev")
    assert "GATEWAY_LOCAL_DEMO_API_KEY" not in console_env

    for command, _, env, _ in runtime.run_calls:
        assert _TEST_KEY not in command
        assert "GATEWAY_LOCAL_DEMO_API_KEY" not in env

    commands = [call[0] for call in runtime.run_calls]
    assert ("npm", "ci", "--ignore-scripts") in commands
    assert any("config" in command and "--quiet" in command for command in commands)
    assert any("up" in command and "grafana" in command for command in commands)
    assert any("ps" in command and "running" in command for command in commands)
    assert any("down" in command and "--volumes" in command for command in commands)
    assert len(runtime.stopped) == 2


def test_missing_runtime_credential_fails_before_any_side_effect() -> None:
    runtime = FakeRuntime()

    with pytest.raises(local_demo.LocalDemoPrerequisiteError) as exc_info:
        local_demo.LocalDemoLauncher(
            _settings(),
            runtime=runtime,
            environ={"PATH": "/test/bin"},
        )

    assert "GATEWAY_LOCAL_DEMO_API_KEY" in str(exc_info.value)
    assert runtime.required == []
    assert runtime.run_calls == []
    assert runtime.start_calls == []


def test_owned_child_exit_fails_closed_and_still_tears_down() -> None:
    runtime = FakeRuntime(second_child_exit_code=7)
    launcher = local_demo.LocalDemoLauncher(
        _settings(),
        runtime=runtime,
        environ=_environ(),
    )

    with pytest.raises(local_demo.LocalDemoChildExitedError) as exc_info:
        launcher.run()

    assert "exit 7" in str(exc_info.value)
    assert len(runtime.stopped) == 2
    commands = [call[0] for call in runtime.run_calls]
    assert any("down" in command and "--remove-orphans" in command for command in commands)


def test_child_environment_builder_does_not_mutate_source_mapping() -> None:
    source = _environ()

    environments = local_demo._build_child_environments(source)

    assert source["GATEWAY_LOCAL_DEMO_API_KEY"] == _TEST_KEY
    assert environments.credential == _TEST_KEY
    assert environments.gateway["GATEWAY_LOCAL_DEMO_API_KEY"] == _TEST_KEY
    assert "GATEWAY_LOCAL_DEMO_API_KEY" not in environments.shared
    assert environments.gateway["PATH"] == source["PATH"]
    assert environments.shared["PATH"] == source["PATH"]


def test_readiness_contract_rejects_non_empty_or_non_local_operations_state() -> None:
    assert local_demo._is_expected_empty_operations_overview(
        {
            "registry": {"deployment_count": 0},
            "health": {"scope": "process_local", "deployment_count": 0},
            "operational_evidence": {"state": "not_supplied"},
        }
    )
    assert not local_demo._is_expected_empty_operations_overview(
        {
            "registry": {"deployment_count": 1},
            "health": {"scope": "process_local", "deployment_count": 1},
            "operational_evidence": {"state": "not_supplied"},
        }
    )
    assert not local_demo._is_expected_empty_operations_overview(
        {
            "registry": {"deployment_count": 0},
            "health": {"scope": "fleet", "deployment_count": 0},
            "operational_evidence": {"state": "not_supplied"},
        }
    )


def test_http_probe_boundary_rejects_external_or_stateful_urls() -> None:
    local_demo._require_reviewed_loopback_url("http://127.0.0.1:8000/readyz")

    with pytest.raises(local_demo.LocalDemoProbeUnavailable):
        local_demo._require_reviewed_loopback_url("https://example.com/readyz")
    with pytest.raises(local_demo.LocalDemoProbeUnavailable):
        local_demo._require_reviewed_loopback_url("http://127.0.0.1:8000/readyz?token=value")
    with pytest.raises(local_demo.LocalDemoProbeUnavailable):
        local_demo._require_reviewed_loopback_url("http://127.0.0.1:9999/readyz")


def test_cli_surface_only_exposes_smoke_test_switch() -> None:
    settings = local_demo.parse_args(["--smoke-test"])

    assert settings.smoke_test is True
    assert settings.repository_root == Path(local_demo.__file__).resolve().parents[1]
