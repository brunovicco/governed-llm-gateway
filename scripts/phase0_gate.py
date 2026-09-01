"""Credential-free regression gate for the Phase 0 architecture baseline."""

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

# Frozen from the ``phase-0-architecture-gate`` baseline tag. Future-phase contract tests are
# intentionally exercised by the repository-wide pytest gate, not silently absorbed here.
PHASE0_CONTRACT_TESTS = (
    "test_authorization_invariant.py",
    "test_contracts.py",
    "test_phase0_boundaries.py",
    "test_phase0_documents.py",
    "test_workspace_smoke.py",
)


def run(command: list[str], env: dict[str, str] | None = None) -> None:
    """Run one gate command and fail immediately on non-zero status."""

    print("+", " ".join(command))
    # Command lists are repository-owned; shell=False and no user input is interpolated.
    subprocess.run(command, cwd=ROOT, check=True, env=env)  # nosec B603


def main() -> int:
    """Validate durable Phase 0 artifacts and architecture boundaries as a regression gate."""

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

    # The Phase 0 repository-wide provider-runtime ban expires when Phase 3 activates provider
    # adapters. The durable Phase 0 boundary is provider-neutral contracts/domain code, which is
    # enforced with exact AST import checks by architecture_check.py. Keeping the former substring
    # scan here would both block legitimate Phase 3 adapters and produce false positives on symbols
    # such as ``OpenAIResponsesAdapter`` and ``AnthropicMessagesAdapter``.
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

    for test_file in PHASE0_CONTRACT_TESTS:
        run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests/contract",
                "-p",
                test_file,
            ],
            env=env,
        )

    print("phase0_gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
