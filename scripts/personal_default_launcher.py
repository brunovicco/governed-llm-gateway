"""Deterministic local orchestration for the personal-default governed inference profile.

Starts the sibling Policy Model Router process and the Gateway together, pointed at
config/profiles/personal-default/, so a consumer project can call governed inference through
one already-running local boundary instead of two manually-managed terminals.
"""

import argparse
import json
import os
import signal

# Security-reviewed: commands are fixed repository-owned argv sequences with shell disabled.
import subprocess  # nosec B404
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_PROFILE_REL = Path("config") / "profiles" / "personal-default"
_POLICY_ROUTER_PATH_ENV = "POLICY_MODEL_ROUTER_ROOT"
_GATEWAY_CREDENTIAL_NAME = "GATEWAY_DEMO_API_KEY"
_POLICY_ROUTER_CREDENTIAL_NAME = "POLICY_ROUTER_DEMO_API_KEY"
_POLICY_ROUTER_CLIENT_ID = "gateway-demo"
_POLICY_ROUTER_READY_URL = "http://127.0.0.1:8001/readyz"
_GATEWAY_READY_URL = "http://127.0.0.1:8000/readyz"
_ALLOWED_HTTP_PORTS = frozenset({8000, 8001})
_STARTUP_TIMEOUT_SECONDS = 60.0
_READINESS_INTERVAL_SECONDS = 1.0
_PROCESS_STOP_TIMEOUT_SECONDS = 5.0
_PROCESS_GROUP_POLL_SECONDS = 0.05


class PersonalDefaultError(RuntimeError):
    """Base failure for the personal-default local launcher."""


class PersonalDefaultPrerequisiteError(PersonalDefaultError):
    """Raised when a required runtime prerequisite is unavailable."""


class PersonalDefaultProbeUnavailable(PersonalDefaultError):
    """Raised when a bounded local HTTP probe is not yet available."""


class PersonalDefaultChildExitedError(PersonalDefaultError):
    """Raised when an owned foreground child exits before launcher shutdown."""


class PersonalDefaultReadinessError(PersonalDefaultError):
    """Raised when the bounded readiness deadline expires."""


class LauncherProcess(Protocol):
    """Minimal owned-child process contract used by the launcher."""

    def poll(self) -> int | None:
        """Return the child exit code when terminated, otherwise None."""
        ...


class LauncherRuntime(Protocol):
    """Side-effect boundary for deterministic launcher tests."""

    def start(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
    ) -> LauncherProcess:
        """Start one fixed foreground child process."""
        ...

    def stop(self, process: LauncherProcess) -> None:
        """Stop one owned child process with bounded escalation."""
        ...

    def get_json(self, url: str) -> object:
        """Retrieve JSON from one reviewed loopback endpoint."""
        ...

    def monotonic(self) -> float:
        """Return a monotonic clock value."""
        ...

    def sleep(self, seconds: float) -> None:
        """Sleep between bounded readiness attempts."""
        ...


class SystemLauncherRuntime:
    """Concrete subprocess and loopback HTTP runtime for the personal-default launcher."""

    def start(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
    ) -> subprocess.Popen[str]:
        """Start one repository-owned foreground child in its own process session."""
        try:
            return subprocess.Popen(  # nosec B603
                tuple(command),
                cwd=cwd,
                env=dict(env),
                text=True,
                start_new_session=True,
            )
        except OSError:
            raise PersonalDefaultPrerequisiteError(
                f"personal-default child could not start: {command[0]}"
            ) from None

    def stop(self, process: LauncherProcess) -> None:
        """Terminate an owned process session with bounded escalation."""
        if not isinstance(process, subprocess.Popen):
            raise TypeError("system runtime can only stop subprocess.Popen instances")
        if os.name == "posix":
            self._stop_posix_process_group(process)
            return
        self._stop_single_process(process)

    def _stop_posix_process_group(self, process: subprocess.Popen[str]) -> None:
        process.poll()
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return

        deadline = time.monotonic() + _PROCESS_STOP_TIMEOUT_SECONDS
        while self._process_group_exists(process.pid):
            process.poll()
            if time.monotonic() >= deadline:
                break
            time.sleep(_PROCESS_GROUP_POLL_SECONDS)

        if self._process_group_exists(process.pid):
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        if process.poll() is None:
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)

    @staticmethod
    def _process_group_exists(process_group_id: int) -> bool:
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def _stop_single_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=_PROCESS_STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1.0)

    def get_json(self, url: str) -> object:
        """Read and decode one reviewed local JSON endpoint."""
        _require_reviewed_loopback_url(url)
        request = urllib.request.Request(url, method="GET")  # noqa: S310
        try:
            with urllib.request.urlopen(request, timeout=1.0) as response:  # noqa: S310  # nosec B310
                raw_body = response.read()
        except (OSError, urllib.error.URLError) as exc:
            raise PersonalDefaultProbeUnavailable("local HTTP probe is unavailable") from exc
        try:
            return json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PersonalDefaultProbeUnavailable("local JSON probe returned invalid JSON") from exc

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


@dataclass(frozen=True, slots=True)
class PersonalDefaultSettings:
    """Fixed local orchestration settings with one non-interactive smoke-test switch."""

    repository_root: Path = _REPOSITORY_ROOT
    policy_router_root: Path | None = None
    smoke_test: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.repository_root, Path):
            raise TypeError("repository_root must use pathlib.Path")
        if not self.repository_root.is_absolute():
            raise PersonalDefaultPrerequisiteError("repository_root must be absolute")
        if self.policy_router_root is not None and not isinstance(self.policy_router_root, Path):
            raise TypeError("policy_router_root must use pathlib.Path")


class PersonalDefaultLauncher:
    """Start the Policy Model Router and the Gateway together for personal-default."""

    def __init__(
        self,
        settings: PersonalDefaultSettings,
        *,
        runtime: LauncherRuntime | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        if not isinstance(settings, PersonalDefaultSettings):
            raise TypeError("settings must use PersonalDefaultSettings")
        self._settings = settings
        self._runtime = SystemLauncherRuntime() if runtime is None else runtime
        source_environ = os.environ if environ is None else environ
        self._policy_router_root = _resolve_policy_router_root(settings, source_environ)
        self._gateway_credential = _require_credential(source_environ, _GATEWAY_CREDENTIAL_NAME)
        self._policy_router_credential = _require_credential(
            source_environ, _POLICY_ROUTER_CREDENTIAL_NAME
        )
        self._gateway_env = dict(source_environ)
        self._policy_router_env = _build_policy_router_env(
            source_environ, self._policy_router_root, self._policy_router_credential
        )
        self._children: list[LauncherProcess] = []

    def run(self) -> None:
        """Start, prove ready and eventually clean up both owned processes."""
        self._require_prerequisites()
        try:
            self._start_children()
            self._wait_until_ready()
            self._print_ready_summary()
            if not self._settings.smoke_test:
                self._wait_for_owned_children()
        except KeyboardInterrupt:
            return
        finally:
            self._cleanup()

    def _require_prerequisites(self) -> None:
        if not self._settings.repository_root.is_dir():
            raise PersonalDefaultPrerequisiteError("repository root does not exist")
        if not self._policy_router_root.is_dir():
            raise PersonalDefaultPrerequisiteError(
                f"policy-model-router root does not exist: {self._policy_router_root}"
            )
        profile_root = self._settings.repository_root / _PROFILE_REL
        if not profile_root.is_dir():
            raise PersonalDefaultPrerequisiteError(
                "personal-default profile directory does not exist"
            )

    def _start_children(self) -> None:
        self._children.append(
            self._runtime.start(
                (
                    "uv",
                    "run",
                    "uvicorn",
                    "policy_model_router.entrypoints.http:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8001",
                ),
                cwd=self._policy_router_root,
                env=self._policy_router_env,
            )
        )
        self._children.append(
            self._runtime.start(
                (
                    "uv",
                    "run",
                    "--frozen",
                    "--package",
                    "governed-llm-gateway-api",
                    "governed-llm-gateway",
                    "--deployment-root",
                    str(self._settings.repository_root),
                    "--model-registry-path",
                    str(_PROFILE_REL / "model_registry.yaml"),
                    "--provider-runtime-path",
                    str(_PROFILE_REL / "provider_runtime.json"),
                    "--client-auth-path",
                    str(_PROFILE_REL / "client_auth.json"),
                    "--operations-access-path",
                    str(_PROFILE_REL / "operations_access.json"),
                    "--policy-router-path",
                    str(_PROFILE_REL / "policy_router.json"),
                    "--ranking-policy-path",
                    str(_PROFILE_REL / "ranking_policy.yaml"),
                    "--default-max-latency-ms",
                    "60000",
                    "--default-max-cost-usd",
                    "0.05",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                ),
                cwd=self._settings.repository_root,
                env=self._gateway_env,
            )
        )

    def _wait_until_ready(self) -> None:
        deadline = self._runtime.monotonic() + _STARTUP_TIMEOUT_SECONDS
        while self._runtime.monotonic() < deadline:
            self._require_owned_children_running()
            try:
                if self._is_ready():
                    return
            except PersonalDefaultProbeUnavailable:
                pass
            self._runtime.sleep(_READINESS_INTERVAL_SECONDS)
        self._require_owned_children_running()
        raise PersonalDefaultReadinessError("personal-default readiness deadline expired")

    def _is_ready(self) -> bool:
        if self._runtime.get_json(_POLICY_ROUTER_READY_URL) != {"status": "ready"}:
            return False
        return self._runtime.get_json(_GATEWAY_READY_URL) == {"status": "ready"}

    def _require_owned_children_running(self) -> None:
        for process in self._children:
            exit_code = process.poll()
            if exit_code is not None:
                raise PersonalDefaultChildExitedError(
                    f"owned personal-default child exited before shutdown (exit {exit_code})"
                )

    def _wait_for_owned_children(self) -> None:
        while True:
            self._require_owned_children_running()
            self._runtime.sleep(0.5)

    def _cleanup(self) -> None:
        for process in reversed(self._children):
            try:
                self._runtime.stop(process)
            except Exception as exc:
                print(
                    f"personal-default cleanup warning: owned child stop failed "
                    f"({type(exc).__name__})",
                    file=sys.stderr,
                )

    @staticmethod
    def _print_ready_summary() -> None:
        print("Governed LLM Gateway personal-default profile is ready.")
        print("Policy Model Router: http://127.0.0.1:8001")
        print("Gateway: http://127.0.0.1:8000")
        print("Point GOVERNED_LLM_GATEWAY_URL at http://127.0.0.1:8000 from your own project.")
        print("Provider and Policy Router credentials remain runtime-only and are not printed.")


def _resolve_policy_router_root(
    settings: PersonalDefaultSettings,
    environ: Mapping[str, str],
) -> Path:
    if settings.policy_router_root is not None:
        return settings.policy_router_root
    override = environ.get(_POLICY_ROUTER_PATH_ENV)
    if override:
        return Path(override).expanduser()
    return settings.repository_root.parent / "policy-model-router"


def _require_credential(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name)
    if value is None or value == "":
        raise PersonalDefaultPrerequisiteError(f"{name} must be set at runtime")
    return value


def _build_policy_router_env(
    environ: Mapping[str, str],
    policy_router_root: Path,
    policy_router_credential: str,
) -> dict[str, str]:
    env = dict(environ)
    env["APP_ENV"] = "development"
    env["ROUTING_POLICY_PATH"] = str(
        policy_router_root / "examples" / "policies" / "gateway-generic.yaml"
    )
    env["API_KEYS"] = json.dumps({_POLICY_ROUTER_CLIENT_ID: policy_router_credential})
    return env


def _require_reviewed_loopback_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise PersonalDefaultProbeUnavailable("local HTTP probe URL has an invalid port") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or port not in _ALLOWED_HTTP_PORTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise PersonalDefaultProbeUnavailable(
            "local HTTP probe URL escaped the reviewed loopback boundary"
        )


def parse_args(argv: Sequence[str]) -> PersonalDefaultSettings:
    """Parse the intentionally tiny personal-default orchestration command surface."""
    parser = argparse.ArgumentParser(
        prog="personal_default_launcher.py",
        description=(
            "Start the Policy Model Router and the Gateway together for the "
            "personal-default profile."
        ),
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Prove startup/readiness and tear the stack down immediately.",
    )
    args = parser.parse_args(tuple(argv))
    return PersonalDefaultSettings(smoke_test=args.smoke_test)


def main() -> int:
    """Run the personal-default launcher with sanitized failures."""
    try:
        PersonalDefaultLauncher(parse_args(sys.argv[1:])).run()
    except PersonalDefaultError as exc:
        print(f"personal-default launcher failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
