"""Repository quality gate matching the project roadmap."""

import os

# Security-reviewed: subprocess runs only repository-owned gate commands.
import subprocess  # nosec B404
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL_PYTHON = os.environ.get("GATEWAY_TOOL_PYTHON", "3.13")


def uvx(*args: str) -> list[str]:
    """Build an isolated uvx command pinned to the project toolchain Python."""
    return ["uvx", "--python", TOOL_PYTHON, *args]


def uv_run(*args: str) -> list[str]:
    """Build a project-aware uv run command for tools that import workspace code."""
    return ["uv", "run", "--frozen", "--python", TOOL_PYTHON, "--all-packages", *args]


COMMANDS = [
    ["uv", "lock", "--check"],
    uvx("--from", "ruff==0.12.11", "ruff", "check", "."),
    uvx("--from", "ruff==0.12.11", "ruff", "format", "--check", "."),
    uv_run(
        "--with",
        "mypy==1.17.1",
        "--with",
        "pytest==8.4.1",
        "mypy",
        "packages",
        "apps",
        "scripts",
        "tests",
    ),
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
        "--cov-report=term-missing",
    ),
    uvx(
        "--from",
        "bandit==1.8.6",
        "bandit",
        "-c",
        "pyproject.toml",
        "-r",
        "packages",
        "apps",
        "scripts",
    ),
    uvx(
        "--from",
        "pip-audit==2.9.0",
        "pip-audit",
        "--no-deps",
        "--disable-pip",
        "-r",
        "requirements-runtime.txt",
    ),
    [sys.executable, "scripts/architecture_check.py"],
    [sys.executable, "scripts/secret_scan.py"],
    [sys.executable, "scripts/phase0_gate.py"],
]


def main() -> int:
    """Run the complete deterministic, credential-free quality gate."""

    for command in COMMANDS:
        print("+", " ".join(command))
        # Command lists are repository-owned; shell=False and no user input is interpolated.
        subprocess.run(command, cwd=ROOT, check=True)  # nosec B603
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
