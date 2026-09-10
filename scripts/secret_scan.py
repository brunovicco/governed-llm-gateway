"""Credential-free deterministic secret-pattern scan for default CI.

The scan answers exactly one question: could a secret reach a commit from this working
tree? Candidates therefore come from Git — tracked files plus untracked files that are
not ignored — rather than from a filesystem walk. A local ``.env``, ``node_modules/`` or
any other ignored path can never be committed, so scanning it only produces findings that
no one can act on. Enumeration fails closed: an unusable working tree is an error, never a
silently narrower scan.
"""

import re

# Security-reviewed: subprocess runs one repository-owned read-only Git plumbing command.
import subprocess  # nosec B404
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_SCANNED_BYTES = 4_000_000
PATTERNS = {
    "OpenAI-style key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
}
_GIT_LIST_COMMITTABLE = (
    "git",
    "ls-files",
    "-z",
    "--cached",
    "--others",
    "--exclude-standard",
)


class SecretScanError(RuntimeError):
    """Raised when the committable candidate set cannot be enumerated safely."""


def committable_paths(root: Path = ROOT) -> tuple[Path, ...]:
    """Return every existing regular file Git would let a commit carry, sorted."""

    try:
        # Repository-owned literal argument list; shell=False and no interpolated input.
        completed = subprocess.run(  # nosec B603 B607
            _GIT_LIST_COMMITTABLE,
            cwd=root,
            check=True,
            capture_output=True,
        )
    except OSError as exc:
        raise SecretScanError(
            "secret_scan requires Git on PATH to enumerate committable files"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise SecretScanError(
            "secret_scan requires a readable Git working tree to enumerate committable files"
        ) from exc

    names = completed.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    candidates = {root / name for name in names if name}
    return tuple(
        sorted(
            path
            for path in candidates
            # Index entries can outlive the file, and a symlink can point outside the tree.
            if path.is_file() and not path.is_symlink()
        )
    )


def scan_file(path: Path) -> tuple[tuple[str, int], ...]:
    """Return ``(pattern name, line number)`` for each secret shape found in one file."""

    try:
        if path.stat().st_size > MAX_SCANNED_BYTES:
            return ()
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ()

    findings: list[tuple[str, int]] = []
    for name, pattern in PATTERNS.items():
        for line_number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                findings.append((name, line_number))
                break
    return tuple(findings)


def main() -> int:
    """Scan every committable text file for high-confidence secret shapes."""

    try:
        paths = committable_paths()
    except SecretScanError as exc:
        print(f"secret_scan: FAIL — {exc}")
        return 1

    findings: list[str] = []
    for path in paths:
        relative = path.relative_to(ROOT)
        for name, line_number in scan_file(path):
            # The matched value is deliberately never printed.
            findings.append(f"{relative}:{line_number}: {name}")

    if findings:
        print("Potential secrets detected:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print(f"secret_scan: PASS ({len(paths)} committable files scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
