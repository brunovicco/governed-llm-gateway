"""Immutable public-URL publication contracts for multimodal benchmark fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from benchmarks.fixtures import BenchmarkFixtureManifest

_PUBLICATION_SOURCE = "github_raw_commit"
_ALLOWED_MANIFEST_KEYS = frozenset({"schema_version", "data_classification", "publications"})
_ALLOWED_PUBLICATION_KEYS = frozenset(
    {"fixture_id", "digest", "source", "source_revision", "url"}
)
_DIGEST_PREFIX = "sha256:"
_MAX_URL_LENGTH = 2048
_GITHUB_RAW_HOST = "raw.githubusercontent.com"


@dataclass(frozen=True, slots=True)
class BenchmarkFixturePublication:
    """One immutable public retrieval URL bound to a reviewed fixture digest."""

    fixture_id: str
    digest: str
    source: str
    source_revision: str
    url: str

    def __post_init__(self) -> None:
        """Require a commit-pinned credential-free publication URL in v1."""
        if not self.fixture_id or self.fixture_id.strip() != self.fixture_id:
            raise ValueError("publication fixture_id must be non-empty and normalized")
        if not _is_sha256_digest(self.digest):
            raise ValueError("publication digest must be sha256:<64 lowercase hex characters>")
        if self.source != _PUBLICATION_SOURCE:
            raise ValueError("publication source must be github_raw_commit in v1")
        if not _is_commit_sha(self.source_revision):
            raise ValueError(
                "publication source_revision must be a 40-character lowercase commit SHA"
            )
        _validate_publication_url(self.url, self.source_revision)


@dataclass(frozen=True, slots=True)
class BenchmarkFixturePublicationManifest:
    """Versioned publication catalog kept separate from local fixture storage."""

    schema_version: str
    data_classification: str
    publications: tuple[BenchmarkFixturePublication, ...]

    def __post_init__(self) -> None:
        """Require an explicitly public, unique publication catalog."""
        if self.schema_version != "1.0":
            raise ValueError("unsupported benchmark fixture publication schema_version")
        if self.data_classification != "public":
            raise ValueError("benchmark fixture publications must be explicitly public")
        if not self.publications:
            raise ValueError("benchmark fixture publication manifest must not be empty")
        fixture_ids = [publication.fixture_id for publication in self.publications]
        if len(fixture_ids) != len(set(fixture_ids)):
            raise ValueError("benchmark fixture publication IDs must be unique")

    def require(self, fixture_id: str) -> BenchmarkFixturePublication:
        """Resolve one publication by fixture ID and fail closed when absent."""
        for publication in self.publications:
            if publication.fixture_id == fixture_id:
                return publication
        raise ValueError(f"unknown benchmark fixture publication: {fixture_id}")


def load_fixture_publication_manifest(path: Path) -> BenchmarkFixturePublicationManifest:
    """Load a strict JSON publication manifest without performing network I/O."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("benchmark fixture publication manifest root must be an object")
    _reject_unknown(payload, _ALLOWED_MANIFEST_KEYS, "benchmark fixture publication manifest")

    raw_publications = payload.get("publications")
    if not isinstance(raw_publications, list):
        raise ValueError("benchmark fixture publication manifest publications must be a list")

    publications: list[BenchmarkFixturePublication] = []
    for index, raw_publication in enumerate(raw_publications):
        if not isinstance(raw_publication, dict):
            raise ValueError(f"benchmark fixture publication {index} must be an object")
        _reject_unknown(
            raw_publication,
            _ALLOWED_PUBLICATION_KEYS,
            f"benchmark fixture publication {index}",
        )
        publications.append(
            BenchmarkFixturePublication(
                fixture_id=_required_string(raw_publication, "fixture_id", index),
                digest=_required_string(raw_publication, "digest", index),
                source=_required_string(raw_publication, "source", index),
                source_revision=_required_string(raw_publication, "source_revision", index),
                url=_required_string(raw_publication, "url", index),
            )
        )

    return BenchmarkFixturePublicationManifest(
        schema_version=_root_string(payload, "schema_version"),
        data_classification=_root_string(payload, "data_classification"),
        publications=tuple(publications),
    )


def validate_fixture_publications(
    fixtures: BenchmarkFixtureManifest,
    publications: BenchmarkFixturePublicationManifest,
) -> None:
    """Require a one-to-one fixture/publication mapping with identical content digests."""
    fixture_ids = {fixture.fixture_id for fixture in fixtures.fixtures}
    publication_ids = {publication.fixture_id for publication in publications.publications}
    if publication_ids != fixture_ids:
        missing = sorted(fixture_ids - publication_ids)
        unknown = sorted(publication_ids - fixture_ids)
        details: list[str] = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unknown:
            details.append(f"unknown: {', '.join(unknown)}")
        detail_text = "; ".join(details)
        raise ValueError(
            f"fixture publication catalog does not match fixture catalog: {detail_text}"
        )

    for fixture in fixtures.fixtures:
        publication = publications.require(fixture.fixture_id)
        if publication.digest != fixture.digest:
            raise ValueError(f"fixture publication digest mismatch: {fixture.fixture_id}")


def _validate_publication_url(url: str, source_revision: str) -> None:
    if not url or url.strip() != url or len(url) > _MAX_URL_LENGTH:
        raise ValueError("publication url must be a bounded normalized HTTPS URL")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != _GITHUB_RAW_HOST:
        raise ValueError("publication url must use HTTPS raw.githubusercontent.com in v1")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("publication url must not contain userinfo")
    if parsed.query or parsed.fragment:
        raise ValueError("publication url must not contain query or fragment")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("publication url contains an invalid port") from exc
    if port is not None:
        raise ValueError("publication url must not override the HTTPS port")

    path_segments = tuple(segment for segment in parsed.path.split("/") if segment)
    if len(path_segments) < 4 or path_segments[2] != source_revision:
        raise ValueError("publication url must be pinned to source_revision")


def _reject_unknown(payload: dict[str, object], allowed: frozenset[str], label: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"{label} contains unknown fields: {', '.join(unknown)}")


def _required_string(payload: dict[str, object], key: str, index: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"benchmark fixture publication {index} {key} must be a string")
    return value


def _root_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"benchmark fixture publication manifest {key} must be a string")
    return value


def _is_sha256_digest(value: str) -> bool:
    if not value.startswith(_DIGEST_PREFIX):
        return False
    digest = value.removeprefix(_DIGEST_PREFIX)
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)


def _is_commit_sha(value: str) -> bool:
    return len(value) == 40 and all(character in "0123456789abcdef" for character in value)
