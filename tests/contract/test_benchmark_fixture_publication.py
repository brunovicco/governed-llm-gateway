from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.fixture_publication import (
    BenchmarkFixturePublication,
    BenchmarkFixturePublicationManifest,
    load_fixture_publication_manifest,
    validate_fixture_publications,
)
from benchmarks.fixtures import load_fixture_manifest

_FIXTURE_ID = "multimodal.quadrants_rgb_001"
_DIGEST = "sha256:c016362530bd9a02aff8d3bf0b7114b38d7499b03e2acacb566f657f94bb5f76"
_REVISION = "627dff6edb500a7d85bc58792992a2dd8b196892"
_URL = (
    "https://raw.githubusercontent.com/brunovicco/governed-llm-gateway/"
    + _REVISION
    + "/benchmarks/fixtures/multimodal-v1/quadrants-rgb.png"
)


def _publication(
    *,
    fixture_id: str = _FIXTURE_ID,
    digest: str = _DIGEST,
    revision: str = _REVISION,
    url: str = _URL,
) -> BenchmarkFixturePublication:
    return BenchmarkFixturePublication(
        fixture_id=fixture_id,
        digest=digest,
        source="github_raw_commit",
        source_revision=revision,
        url=url,
    )


def _fixture_root() -> Path:
    return Path(__file__).resolve().parents[2] / "benchmarks" / "fixtures" / "multimodal-v1"


def test_checked_in_publication_is_commit_pinned_and_matches_fixture_catalog() -> None:
    fixture_root = _fixture_root()
    fixtures = load_fixture_manifest(fixture_root / "manifest.json")
    publications = load_fixture_publication_manifest(fixture_root / "publication.json")

    validate_fixture_publications(fixtures, publications)
    publication = publications.require(_FIXTURE_ID)

    assert publication.source_revision == _REVISION
    assert f"/{_REVISION}/" in publication.url
    assert "/main/" not in publication.url
    assert publication.digest == fixtures.require(_FIXTURE_ID).digest


def test_publication_rejects_mutable_or_credential_bearing_urls() -> None:
    invalid_urls = (
        "https://raw.githubusercontent.com/brunovicco/governed-llm-gateway/main/image.png",
        _URL + "?token=secret",
        _URL + "#fragment",
        _URL.replace("https://", "http://"),
        _URL.replace("raw.githubusercontent.com", "user:pass@raw.githubusercontent.com"),
        _URL.replace("raw.githubusercontent.com", "example.test"),
        _URL.replace(_REVISION, "1" * 40),
    )

    for url in invalid_urls:
        with pytest.raises(ValueError):
            _publication(url=url)


def test_publication_requires_canonical_revision_source_and_digest() -> None:
    with pytest.raises(ValueError, match="source must be"):
        BenchmarkFixturePublication(
            fixture_id=_FIXTURE_ID,
            digest=_DIGEST,
            source="mutable_url",
            source_revision=_REVISION,
            url=_URL,
        )

    with pytest.raises(ValueError, match="source_revision"):
        _publication(revision="main")

    with pytest.raises(ValueError, match="digest"):
        _publication(digest="sha256:1234")


def test_fixture_publication_validation_rejects_missing_unknown_and_digest_drift() -> None:
    fixtures = load_fixture_manifest(_fixture_root() / "manifest.json")

    unknown = BenchmarkFixturePublicationManifest(
        schema_version="1.0",
        data_classification="public",
        publications=(_publication(fixture_id="multimodal.unknown"),),
    )
    with pytest.raises(ValueError, match="does not match fixture catalog"):
        validate_fixture_publications(fixtures, unknown)

    drift = BenchmarkFixturePublicationManifest(
        schema_version="1.0",
        data_classification="public",
        publications=(_publication(digest="sha256:" + "0" * 64),),
    )
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_fixture_publications(fixtures, drift)


def test_fixture_publication_loader_rejects_unknown_fields(tmp_path: Path) -> None:
    invalid_manifest = tmp_path / "publication.json"
    invalid_manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "data_classification": "public",
                "publications": [
                    {
                        "fixture_id": _FIXTURE_ID,
                        "digest": _DIGEST,
                        "source": "github_raw_commit",
                        "source_revision": _REVISION,
                        "url": _URL,
                        "mutable": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown fields"):
        load_fixture_publication_manifest(invalid_manifest)
