"""Credential-free acceptance gate for Phase 0 — Architecture Gate."""

import os

# Security-reviewed: subprocess runs only repository-owned gate commands.
import subprocess  # nosec B404
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    "pyproject.toml",
    "docs/project/PROJECT_INSTRUCTIONS.md",
    "docs/project/CURRENT_STATE.md",
    "docs/project/ARCHITECTURE.md",
    "docs/project/ROADMAP.md",
    "docs/project/PROVIDER_CONTRACT.md",
    "docs/project/MODEL_REGISTRY.md",
    "docs/project/ROUTING.md",
    "docs/project/FALLBACK_AND_RETRY.md",
    "docs/project/OBSERVABILITY.md",
    "docs/project/EVALUATION.md",
    "docs/project/SECURITY_MODEL.md",
    "docs/project/THREAT_MODEL.md",
    "docs/project/SOURCES.md",
    "docs/project/SOURCE_ROADMAP.txt",
    "docs/adr/ADR-0001-gateway-vs-policy-router-boundary.md",
    "docs/adr/ADR-0002-workspace-package-topology.md",
    "docs/adr/ADR-0003-provider-neutral-contract.md",
    "docs/adr/ADR-0004-native-vs-openai-compatible-adapters.md",
    "docs/adr/ADR-0005-model-registry-and-provenance.md",
]
FORBIDDEN_RUNTIME_TERMS = (
    "from openai ",
    "import openai",
    "from anthropic ",
    "import anthropic",
    "from fastapi ",
    "import fastapi",
    "from opentelemetry ",
    "import opentelemetry",
)


def run(command: list[str], env: dict[str, str] | None = None) -> None:
    """Run one gate command and fail immediately on non-zero status."""

    print("+", " ".join(command))
    # Command lists are repository-owned; shell=False and no user input is interpolated.
    subprocess.run(command, cwd=ROOT, check=True, env=env)  # nosec B603


def main() -> int:
    """Validate all Phase 0 acceptance artifacts without network/credentials."""

    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        print("Missing Phase 0 files:")
        for path in missing:
            print(f"- {path}")
        return 1

    workspace = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for member in (
        "apps/gateway-api",
        "packages/gateway-contracts",
        "packages/gateway-core",
        "packages/gateway-client",
    ):
        if member not in workspace:
            print(f"Workspace member missing: {member}")
            return 1

    code = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [*(ROOT / "packages").rglob("*.py"), *(ROOT / "apps").rglob("*.py")]
    ).lower()
    blocked = [term for term in FORBIDDEN_RUNTIME_TERMS if term in code]
    if blocked:
        print(f"Forbidden Phase 0 runtime imports found: {blocked}")
        return 1

    run([sys.executable, "scripts/architecture_check.py"])
    run([sys.executable, "scripts/secret_scan.py"])

    env = os.environ.copy()
    python_paths = [
        ROOT / "packages/gateway-contracts/src",
        ROOT / "packages/gateway-core/src",
        ROOT / "packages/gateway-client/src",
        ROOT / "apps/gateway-api/src",
    ]
    env["PYTHONPATH"] = os.pathsep.join(str(path) for path in python_paths)
    run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests/contract",
            "-p",
            "test_*.py",
        ],
        env=env,
    )

    print("phase0_gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
