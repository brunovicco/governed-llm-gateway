"""Verify that local PDP proofs use the reviewed Policy Model Router revision."""

import shutil

# This helper only asks Git for HEAD using the explicit repository path and fixed arguments.
import subprocess  # nosec B404
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
PIN_PATH = _ROOT / "config" / "composition-proof" / "router.commit"


class RouterPinError(RuntimeError):
    """Raised when the sibling Policy Model Router checkout is absent or at another revision."""


def verify_router_revision(repository: Path, *, pin_path: Path = PIN_PATH) -> str:
    """Require the Router checkout to match the full reviewed commit ID in the pin file."""
    try:
        expected = pin_path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RouterPinError("Policy Model Router revision pin cannot be read") from error
    if len(expected) != 40 or any(character not in "0123456789abcdef" for character in expected):
        raise RouterPinError("Policy Model Router revision pin must be a full lowercase commit ID")
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RouterPinError("Git executable is unavailable")
    try:
        result = subprocess.run(
            [git_executable, "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )  # nosec B603
    except (OSError, subprocess.SubprocessError) as error:
        raise RouterPinError(
            "Policy Model Router checkout is unavailable or not a Git repository"
        ) from error
    observed = result.stdout.strip()
    if observed != expected:
        raise RouterPinError(
            "Policy Model Router checkout does not match the reviewed pinned revision"
        )
    return observed
