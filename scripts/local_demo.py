"""Deterministic local orchestration for the bounded Gateway operations demo stack."""

from __future__ import annotations

import argparse
import json
import os
import shutil

# Security-reviewed: commands are fixed repository-owned argv sequences with shell disabled.
import subprocess  # nosec B404
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_CONSOLE_ROOT = _REPOSITORY_ROOT / "apps/gateway-console"
_COMPOSE_FILE = _REPOSITORY_ROOT / "compose.observability.yml"
_COMPOSE_PROJECT = "governed-llm-gateway-demo"
_DEMO_KEY_NAME = "GATEWAY_LOCAL_DEMO_API_KEY"
_GATEWAY_READY_URL = "http://127.0.0.1:8000/readyz"
_OPERATIONS_OVERVIEW_URL = "http://127.0.0.1:8000/v1/ops/overview"
_GRAFANA_HEALTH_URL = "http://127.0.0.1:3000/api/health"
_CONSOLE_URL = "http://127.0.0.1:5173/"
_EXPECTED_COMPOSE_SERVICES = frozenset({"otel-collector", "tempo", "grafana"})
_ALLOWED_HTTP_PORTS = frozenset({3000, 5173, 8000})
_STARTUP_TIMEOUT_SECONDS = 90.0
_READINESS_INTERVAL_SECONDS = 1.0


class LocalDemoError(RuntimeError):
    """Base failure for the repository-owned local demo launcher."""


class LocalDemoPrerequisiteError(LocalDemoError):
    """Raised when a required runtime prerequisite is unavailable."""


class LocalDemoCommandError(LocalDemoError):
    """Raised when one fixed local command fails."""


class LocalDemoProbeUnavailable(LocalDemoError):
    """Raised when a bounded local HTTP probe is not yet available."""


class LocalDemoChildExitedError(LocalDemoError):
    """Raised when an owned foreground child exits before launcher shutdown."""


class LocalDemoReadinessError(LocalDemoError):
    """Raised when the bounded demo readiness deadline expires."""


class DemoProcess(Protocol):
    """Minimal owned-child process contract used by the launcher."""

    def poll(self) -> int | None:
        """Return the child exit code when terminated, otherwise None."""
        ...


class DemoRuntime(Protocol):
    """Side-effect boundary for deterministic launcher tests."""

    def require_executable(self, name: str) -> None:
        """Require one executable to exist on PATH."""
        ...

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        capture_output: bool = False,
    ) -> str:
        """Run one fixed command and return stdout when requested."""
        ...

    def start(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
    ) -> DemoProcess:
        """Start one fixed foreground child process."""
        ...

    def stop(self, process: DemoProcess) -> None:
        """Stop one owned child process with bounded escalation."""
        ...

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        """Retrieve JSON from one reviewed loopback endpoint."""
        ...

    def get_text(self, url: str) -> str:
        """Retrieve text from one reviewed loopback endpoint."""
        ...

    def monotonic(self) -> float:
        """Return a monotonic clock value."""
        ...

    def sleep(self, seconds: float) -> None:
        """Sleep between bounded readiness attempts."""
        ...


class SystemDemoRuntime:
    """Concrete subprocess and loopback HTTP runtime for the local demo."""

    def require_executable(self, name: str) -> None:
        """Fail closed when a required executable is missing."""
        if shutil.which(name) is None:
            raise LocalDemoPrerequisiteError(f"required executable is unavailable: {name}")

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        capture_output: bool = False,
    ) -> str:
        """Run a repository-owned argv command without a shell."""
        completed = subprocess.run(  # nosec B603
            tuple(command),
            cwd=cwd,
            env=dict(env),
            check=False,
            text=True,
            capture_output=capture_output,
        )
        if completed.returncode != 0:
            raise LocalDemoCommandError(
                f"local demo command failed: {command[0]} (exit {completed.returncode})"
            )
        return completed.stdout if capture_output else ""

    def start(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
    ) -> subprocess.Popen[str]:
        """Start one repository-owned foreground child without a shell."""
        return subprocess.Popen(  # nosec B603
            tuple(command),
            cwd=cwd,
            env=dict(env),
            text=True,
        )

    def stop(self, process: DemoProcess) -> None:
        """Terminate an owned subprocess, escalating only after a bounded wait."""
        if process.poll() is not None:
            return
        if not isinstance(process, subprocess.Popen):
            raise TypeError("system runtime can only stop subprocess.Popen instances")
        process.terminate()
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5.0)

    def get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        """Read and decode one reviewed local JSON endpoint."""
        body = self._get(url, headers=headers)
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise LocalDemoProbeUnavailable("local JSON probe returned invalid JSON") from exc

    def get_text(self, url: str) -> str:
        """Read one reviewed local text endpoint."""
        return self._get(url, headers=None)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def _get(self, url: str, *, headers: Mapping[str, str] | None) -> str:
        _require_reviewed_loopback_url(url)
        request = urllib.request.Request(url, headers=dict(headers or {}), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=1.0) as response:  # nosec B310
                return response.read().decode("utf-8")
        except (OSError, urllib.error.URLError, UnicodeDecodeError) as exc:
            raise LocalDemoProbeUnavailable("local HTTP probe is unavailable") from exc


@dataclass(frozen=True, slots=True)
class LocalDemoSettings:
    """Fixed local orchestration settings with one non-interactive smoke-test switch."""

    repository_root: Path = _REPOSITORY_ROOT
    smoke_test: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.repository_root, Path):
            raise TypeError("repository_root must use pathlib.Path")
        if not self.repository_root.is_absolute():
            raise LocalDemoPrerequisiteError("repository_root must be absolute")


@dataclass(frozen=True, slots=True)
class ChildEnvironments:
    """Credential-isolated child environments for the local demo stack."""

    credential: str
    gateway: Mapping[str, str]
    shared: Mapping[str, str]


class LocalDemoLauncher:
    """Coordinate already-reviewed local components without creating execution authority."""

    def __init__(
        self,
        settings: LocalDemoSettings,
        *,
        runtime: DemoRuntime | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if not isinstance(settings, LocalDemoSettings):
            raise TypeError("settings must use LocalDemoSettings")
        self._settings = settings
        self._runtime = SystemDemoRuntime() if runtime is None else runtime
        self._environments = _build_child_environments(os.environ if environ is None else environ)
        self._children: list[DemoProcess] = []
        self._compose_attempted = False

    def run(self) -> None:
        """Start, prove and eventually clean up the bounded local demo stack."""
        root = self._settings.repository_root
        console_root = root / "apps/gateway-console"
        compose_file = root / "compose.observability.yml"
        self._require_prerequisites(root, console_root, compose_file)

        try:
            self._runtime.run(
                _compose_command(compose_file, "config", "--quiet"),
                cwd=root,
                env=self._environments.shared,
            )
            self._runtime.run(
                ("npm", "ci", "--ignore-scripts"),
                cwd=console_root,
                env=self._environments.shared,
            )
            self._compose_attempted = True
            self._runtime.run(
                _compose_command(
                    compose_file,
                    "up",
                    "-d",
                    "otel-collector",
                    "tempo",
                    "grafana",
                ),
                cwd=root,
                env=self._environments.shared,
            )
            self._children.append(
                self._runtime.start(
                    (
                        "uv",
                        "run",
                        "--frozen",
                        "--package",
                        "governed-llm-gateway-api",
                        "governed-llm-gateway-operations-demo",
                    ),
                    cwd=root,
                    env=self._environments.gateway,
                )
            )
            self._children.append(
                self._runtime.start(
                    ("npm", "run", "dev"),
                    cwd=console_root,
                    env=self._environments.shared,
                )
            )
            self._wait_until_ready(root, compose_file)
            self._print_ready_summary()
            if not self._settings.smoke_test:
                self._wait_for_owned_child()
        except KeyboardInterrupt:
            return
        finally:
            self._cleanup(root, compose_file)

    def _require_prerequisites(
        self,
        root: Path,
        console_root: Path,
        compose_file: Path,
    ) -> None:
        if not root.is_dir():
            raise LocalDemoPrerequisiteError("repository root does not exist")
        if not console_root.is_dir():
            raise LocalDemoPrerequisiteError("Gateway Console directory does not exist")
        if not compose_file.is_file():
            raise LocalDemoPrerequisiteError("observability Compose file does not exist")
        for executable in ("docker", "npm", "uv"):
            self._runtime.require_executable(executable)

    def _wait_until_ready(self, root: Path, compose_file: Path) -> None:
        deadline = self._runtime.monotonic() + _STARTUP_TIMEOUT_SECONDS
        while self._runtime.monotonic() < deadline:
            self._require_owned_children_running()
            try:
                if self._is_ready(root, compose_file):
                    return
            except LocalDemoProbeUnavailable:
                pass
            self._runtime.sleep(_READINESS_INTERVAL_SECONDS)
        self._require_owned_children_running()
        raise LocalDemoReadinessError("local demo readiness deadline expired")

    def _is_ready(self, root: Path, compose_file: Path) -> bool:
        gateway_ready = self._runtime.get_json(_GATEWAY_READY_URL)
        if gateway_ready != {"status": "ready"}:
            return False

        overview = self._runtime.get_json(
            _OPERATIONS_OVERVIEW_URL,
            headers={"X-Gateway-API-Key": self._environments.credential},
        )
        if not _is_expected_empty_operations_overview(overview):
            return False

        grafana_health = self._runtime.get_json(_GRAFANA_HEALTH_URL)
        if not isinstance(grafana_health, dict) or grafana_health.get("database") != "ok":
            return False

        console_html = self._runtime.get_text(_CONSOLE_URL)
        if '<div id="root"></div>' not in console_html:
            return False

        running = self._runtime.run(
            _compose_command(compose_file, "ps", "--status", "running", "--services"),
            cwd=root,
            env=self._environments.shared,
            capture_output=True,
        )
        return _EXPECTED_COMPOSE_SERVICES <= frozenset(running.splitlines())

    def _require_owned_children_running(self) -> None:
        for process in self._children:
            exit_code = process.poll()
            if exit_code is not None:
                raise LocalDemoChildExitedError(
                    f"owned local demo child exited before shutdown (exit {exit_code})"
                )

    def _wait_for_owned_child(self) -> None:
        while True:
            self._require_owned_children_running()
            self._runtime.sleep(0.5)

    def _cleanup(self, root: Path, compose_file: Path) -> None:
        for process in reversed(self._children):
            try:
                self._runtime.stop(process)
            except Exception as exc:
                print(
                    f"local demo cleanup warning: owned child stop failed ({type(exc).__name__})",
                    file=sys.stderr,
                )
        if self._compose_attempted:
            try:
                self._runtime.run(
                    _compose_command(compose_file, "down", "--volumes", "--remove-orphans"),
                    cwd=root,
                    env=self._environments.shared,
                )
            except LocalDemoError as exc:
                print(f"local demo cleanup warning: {exc}", file=sys.stderr)

    @staticmethod
    def _print_ready_summary() -> None:
        print("Governed LLM Gateway local demo is ready.")
        print(f"Console: {_CONSOLE_URL}")
        print("Operations API: http://127.0.0.1:8000/v1/ops/overview")
        print("Grafana: http://127.0.0.1:3000")
        print("The Gateway demo credential remains runtime-only and is not printed.")


def _compose_command(compose_file: Path, *args: str) -> tuple[str, ...]:
    return (
        "docker",
        "compose",
        "--project-name",
        _COMPOSE_PROJECT,
        "-f",
        str(compose_file),
        *args,
    )


def _build_child_environments(environ: Mapping[str, str]) -> ChildEnvironments:
    credential = environ.get(_DEMO_KEY_NAME)
    if credential is None or credential == "":
        raise LocalDemoPrerequisiteError(f"{_DEMO_KEY_NAME} must be set at runtime")
    shared = dict(environ)
    shared.pop(_DEMO_KEY_NAME, None)
    gateway = dict(shared)
    gateway[_DEMO_KEY_NAME] = credential
    return ChildEnvironments(
        credential=credential,
        gateway=gateway,
        shared=shared,
    )


def _is_expected_empty_operations_overview(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    registry = payload.get("registry")
    health = payload.get("health")
    evidence = payload.get("operational_evidence")
    return (
        isinstance(registry, dict)
        and registry.get("deployment_count") == 0
        and isinstance(health, dict)
        and health.get("scope") == "process_local"
        and health.get("deployment_count") == 0
        and isinstance(evidence, dict)
        and evidence.get("state") == "not_supplied"
    )


def _require_reviewed_loopback_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port not in _ALLOWED_HTTP_PORTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise LocalDemoProbeUnavailable("local HTTP probe URL escaped the reviewed loopback boundary")


def parse_args(argv: Sequence[str]) -> LocalDemoSettings:
    """Parse the intentionally tiny local demo orchestration command surface."""
    parser = argparse.ArgumentParser(
        prog="local_demo.py",
        description="Start the bounded read-only Governed LLM Gateway local demo stack.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Prove startup/readiness and tear the stack down immediately.",
    )
    args = parser.parse_args(tuple(argv))
    return LocalDemoSettings(smoke_test=args.smoke_test)


def main() -> int:
    """Run the local demo launcher with sanitized failures."""
    try:
        LocalDemoLauncher(parse_args(sys.argv[1:])).run()
    except LocalDemoError as exc:
        print(f"local demo failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
