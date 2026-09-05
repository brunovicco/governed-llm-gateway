"""Credential-free local fixture contracts for future multimodal benchmarks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_ALLOWED_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_ALLOWED_MANIFEST_KEYS = frozenset({"schema_version", "data_classification", "fixtures"})
_ALLOWED_FIXTURE_KEYS = frozenset({"fixture_id", "media_type", "relative_path", "digest"})
_MAX_FIXTURE_BYTES = 20 * 1024 * 1024
_DIGEST_PREFIX = "sha256:"


@dataclass(frozen=True, slots=True)
class BenchmarkFixture:
    """Immutable public fixture descriptor referenced by benchmark cases."""

    fixture_id: str
    media_type: str
    relative_path: str
    digest: str

    def __post_init__(self) -> None:
        """Reject ambiguous paths, unsupported media types, and malformed digests."""
        if not self.fixture_id or self.fixture_id.strip() != self.fixture_id:
            raise ValueError("fixture_id must be non-empty and normalized")
        if self.media_type not in _ALLOWED_MEDIA_TYPES:
            raise ValueError("fixture media_type must be image/jpeg, image/png, or image/webp")

        path = PurePosixPath(self.relative_path)
        if (
            not self.relative_path
            or self.relative_path.strip() != self.relative_path
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
            or "\\" in self.relative_path
        ):
            raise ValueError("fixture relative_path must be a normalized relative POSIX path")

        if not _is_sha256_digest(self.digest):
            raise ValueError("fixture digest must be sha256:<64 lowercase hex characters>")


@dataclass(frozen=True, slots=True)
class BenchmarkFixtureManifest:
    """Versioned public fixture catalog kept separate from model outputs and routing evidence."""

    schema_version: str
    data_classification: str
    fixtures: tuple[BenchmarkFixture, ...]

    def __post_init__(self) -> None:
        """Require a non-empty public catalog with unique fixture identities."""
        if self.schema_version != "1.0":
            raise ValueError("unsupported benchmark fixture schema_version")
        if self.data_classification != "public":
            raise ValueError("benchmark fixtures must be explicitly public")
        if not self.fixtures:
            raise ValueError("benchmark fixture manifest must contain at least one fixture")
        fixture_ids = [fixture.fixture_id for fixture in self.fixtures]
        if len(fixture_ids) != len(set(fixture_ids)):
            raise ValueError("benchmark fixture IDs must be unique")

    def require(self, fixture_id: str) -> BenchmarkFixture:
        """Resolve one descriptor by stable ID and fail closed when it is not declared."""
        for fixture in self.fixtures:
            if fixture.fixture_id == fixture_id:
                return fixture
        raise ValueError(f"unknown benchmark fixture: {fixture_id}")


@dataclass(frozen=True, slots=True)
class ResolvedBenchmarkFixture:
    """Verified local fixture bytes ready for a benchmark executor boundary."""

    fixture: BenchmarkFixture
    content: bytes

    @property
    def size_bytes(self) -> int:
        """Return the verified content size without re-reading the filesystem."""
        return len(self.content)


def load_fixture_manifest(path: Path) -> BenchmarkFixtureManifest:
    """Load a strict JSON fixture manifest without resolving any referenced file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("benchmark fixture manifest root must be an object")
    _reject_unknown(payload, _ALLOWED_MANIFEST_KEYS, "benchmark fixture manifest")

    raw_fixtures = payload.get("fixtures")
    if not isinstance(raw_fixtures, list):
        raise ValueError("benchmark fixture manifest fixtures must be a list")

    fixtures: list[BenchmarkFixture] = []
    for index, raw_fixture in enumerate(raw_fixtures):
        if not isinstance(raw_fixture, dict):
            raise ValueError(f"benchmark fixture {index} must be an object")
        _reject_unknown(raw_fixture, _ALLOWED_FIXTURE_KEYS, f"benchmark fixture {index}")
        fixtures.append(
            BenchmarkFixture(
                fixture_id=_required_string(raw_fixture, "fixture_id", index),
                media_type=_required_string(raw_fixture, "media_type", index),
                relative_path=_required_string(raw_fixture, "relative_path", index),
                digest=_required_string(raw_fixture, "digest", index),
            )
        )

    return BenchmarkFixtureManifest(
        schema_version=_root_string(payload, "schema_version"),
        data_classification=_root_string(payload, "data_classification"),
        fixtures=tuple(fixtures),
    )


def resolve_fixture(
    root: Path,
    fixture: BenchmarkFixture,
    *,
    max_bytes: int = _MAX_FIXTURE_BYTES,
) -> ResolvedBenchmarkFixture:
    """Read a local fixture only after containment, size, and digest validation."""
    if max_bytes <= 0:
        raise ValueError("fixture max_bytes must be positive")

    root_path = root.resolve(strict=True)
    if not root_path.is_dir():
        raise ValueError("benchmark fixture root must be a directory")

    candidate = (root_path / Path(fixture.relative_path)).resolve(strict=True)
    if not candidate.is_relative_to(root_path):
        raise ValueError("benchmark fixture path escapes the configured root")
    if not candidate.is_file():
        raise ValueError("benchmark fixture path must resolve to a regular file")

    size = candidate.stat().st_size
    if size <= 0:
        raise ValueError("benchmark fixture must not be empty")
    if size > max_bytes:
        raise ValueError("benchmark fixture exceeds the configured byte limit")

    content = candidate.read_bytes()
    if len(content) != size or len(content) > max_bytes:
        raise ValueError("benchmark fixture changed while being read")
    actual_digest = _sha256(content)
    if actual_digest != fixture.digest:
        raise ValueError("benchmark fixture digest mismatch")

    return ResolvedBenchmarkFixture(fixture=fixture, content=content)


def _reject_unknown(payload: dict[str, object], allowed: frozenset[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {', '.join(unknown)}")


def _required_string(payload: dict[str, object], key: str, index: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"benchmark fixture {index} {key} must be a string")
    return value


def _root_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"benchmark fixture manifest {key} must be a string")
    return value


def _is_sha256_digest(value: str) -> bool:
    if not value.startswith(_DIGEST_PREFIX):
        return False
    digest = value.removeprefix(_DIGEST_PREFIX)
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)


def _sha256(content: bytes) -> str:
    return _DIGEST_PREFIX + hashlib.sha256(content).hexdigest()
