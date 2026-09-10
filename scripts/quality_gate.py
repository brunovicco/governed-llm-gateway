"""Repository quality gate matching the project roadmap.

Each step runs exactly once. ``scripts/phase0_gate.py`` owns the architecture-boundary
check and the secret scan and re-runs them itself, so this gate invokes that script
rather than repeating either command — a duplicated step costs time without adding a
signal, and lets the two lists drift apart.
"""

import os

# Security-reviewed: subprocess runs only repository-owned gate commands.
import subprocess  # nosec B404
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL_PYTHON = os.environ.get("GATEWAY_TOOL_PYTHON", "3.13")


def uvx(*args: str) -> list[str]:
    """Build an isolated uvx command pinned to the project toolchain Python."""
    return ["uvx", "--python", TOOL_PYTHON, *args]


def uv_run(*args: str) -> list[str]:
    """Build a project-aware uv run command for tools that import workspace code."""
    return ["uv", "run", "--frozen", "--python", TOOL_PYTHON, "--all-packages", *args]


STEPS: list[tuple[str, list[str]]] = [
    ("lockfile", ["uv", "lock", "--check"]),
    ("lint", uvx("--from", "ruff==0.12.11", "ruff", "check", ".")),
    ("format", uvx("--from", "ruff==0.12.11", "ruff", "format", "--check", ".")),
    (
        "types",
        uv_run(
            "--with",
            "mypy==1.17.1",
            "--with",
            "pytest==8.4.1",
            "--with",
            "types-jsonschema==4.26.0.20260518",
            "mypy",
            "packages",
            "apps",
            "benchmarks",
            "scripts",
            "tests",
        ),
    ),
    (
        "tests",
        uv_run(
            "--with",
            "pytest==8.4.1",
            "--with",
            "pytest-cov==6.2.1",
            "pytest",
            "--cov=governed_llm_gateway_contracts",
            "--cov=governed_llm_gateway_core",
            "--cov=governed_llm_gateway_client",
            "--cov=governed_llm_gateway_api",
            "--cov=benchmarks",
            "--cov-report=term-missing",
            "--cov-fail-under=80",
        ),
    ),
    # Re-reads the persisted .coverage file, proving the artifact the tests wrote is
    # itself well-formed and still above the threshold.
    (
        "coverage-artifact",
        uv_run("--with", "coverage==7.10.6", "coverage", "report", "--fail-under=80"),
    ),
    (
        "security",
        uvx(
            "--from",
            "bandit==1.8.6",
            "bandit",
            "-c",
            "pyproject.toml",
            "-r",
            "packages",
            "apps",
            "benchmarks",
            "scripts",
        ),
    ),
    (
        "dependency-audit",
        uvx(
            "--from",
            "pip-audit==2.9.0",
            "pip-audit",
            "--no-deps",
            "--disable-pip",
            "-r",
            "requirements-runtime.txt",
        ),
    ),
    # Owns architecture_check.py and secret_scan.py; both run inside it.
    ("phase0", [sys.executable, "scripts/phase0_gate.py"]),
]


def main() -> int:
    """Run the complete deterministic, credential-free quality gate."""

    durations: list[tuple[str, float]] = []
    for name, command in STEPS:
        print(f"+ [{name}] {' '.join(command)}")
        started = time.monotonic()
        # Command lists are repository-owned; shell=False and no user input is interpolated.
        completed = subprocess.run(command, cwd=ROOT, check=False)  # nosec B603
        elapsed = time.monotonic() - started
        durations.append((name, elapsed))
        if completed.returncode != 0:
            print(f"\nquality_gate: FAIL at {name} after {elapsed:.1f}s")
            return completed.returncode

    total = sum(elapsed for _, elapsed in durations)
    print("\nquality_gate: PASS")
    for name, elapsed in durations:
        print(f"- {name}: {elapsed:.1f}s")
    print(f"- total: {total:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
