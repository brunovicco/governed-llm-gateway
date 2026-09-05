from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.fixtures import (
    BenchmarkFixture,
    BenchmarkFixtureManifest,
    load_fixture_manifest,
    resolve_fixture,
)

_PNG_CONTENT = b"\x89PNG\r\n\x1a\nsynthetic-image-bytes-v1"


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _fixture(
    *,
    digest: str,
    relative_path: str = "images/sample.png",
    media_type: str = "image/png",
) -> BenchmarkFixture:
    return BenchmarkFixture(
        fixture_id="multimodal.sample_001",
        media_type=media_type,
        relative_path=relative_path,
        digest=digest,
    )


def test_fixture_manifest_loads_strict_public_catalog(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "data_classification": "public",
                "fixtures": [
                    {
                        "fixture_id": "multimodal.sample_001",
                        "media_type": "image/png",
                        "relative_path": "images/sample.png",
                        "digest": _digest(_PNG_CONTENT),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_fixture_manifest(manifest_path)

    assert manifest.schema_version == "1.0"
    assert manifest.data_classification == "public"
    assert manifest.require("multimodal.sample_001").relative_path == "images/sample.png"
    with pytest.raises(ValueError, match="unknown benchmark fixture"):
        manifest.require("missing")


def test_fixture_descriptor_rejects_unsupported_media_type_and_unsafe_paths() -> None:
    digest = _digest(_PNG_CONTENT)

    with pytest.raises(ValueError, match="media_type"):
        BenchmarkFixture(
            fixture_id="fixture",
            media_type="image/gif",
            relative_path="images/sample.gif",
            digest=digest,
        )

    for relative_path in (
        "../sample.png",
        "/root/sample.png",
        "images/../sample.png",
        "images\\sample.png",
        " images/sample.png",
    ):
        with pytest.raises(ValueError, match="relative_path"):
            _fixture(digest=digest, relative_path=relative_path)


def test_fixture_descriptor_requires_canonical_sha256_digest() -> None:
    for digest in (
        "",
        "abc",
        "sha256:1234",
        "sha256:" + "A" * 64,
        "sha512:" + "a" * 64,
    ):
        with pytest.raises(ValueError, match="digest"):
            _fixture(digest=digest)


def test_fixture_manifest_rejects_private_unknown_and_duplicate_entries(tmp_path: Path) -> None:
    digest = _digest(_PNG_CONTENT)

    with pytest.raises(ValueError, match="explicitly public"):
        BenchmarkFixtureManifest(
            schema_version="1.0",
            data_classification="confidential",
            fixtures=(_fixture(digest=digest),),
        )

    with pytest.raises(ValueError, match="IDs must be unique"):
        BenchmarkFixtureManifest(
            schema_version="1.0",
            data_classification="public",
            fixtures=(_fixture(digest=digest), _fixture(digest=digest)),
        )

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "data_classification": "public",
                "fixtures": [
                    {
                        "fixture_id": "multimodal.sample_001",
                        "media_type": "image/png",
                        "relative_path": "images/sample.png",
                        "digest": digest,
                        "provider_url": "https://example.test/image.png",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown fields"):
        load_fixture_manifest(manifest_path)


def test_resolve_fixture_returns_verified_bytes(tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    image_dir = root / "images"
    image_dir.mkdir(parents=True)
    (image_dir / "sample.png").write_bytes(_PNG_CONTENT)
    fixture = _fixture(digest=_digest(_PNG_CONTENT))

    resolved = resolve_fixture(root, fixture)

    assert resolved.fixture is fixture
    assert resolved.content == _PNG_CONTENT
    assert resolved.size_bytes == len(_PNG_CONTENT)


def test_resolve_fixture_fails_closed_on_digest_size_empty_and_media_mismatch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "fixtures"
    image_dir = root / "images"
    image_dir.mkdir(parents=True)
    path = image_dir / "sample.png"
    path.write_bytes(_PNG_CONTENT)

    with pytest.raises(ValueError, match="digest mismatch"):
        resolve_fixture(root, _fixture(digest=_digest(b"different")))

    with pytest.raises(ValueError, match="byte limit"):
        resolve_fixture(
            root,
            _fixture(digest=_digest(_PNG_CONTENT)),
            max_bytes=len(_PNG_CONTENT) - 1,
        )

    with pytest.raises(ValueError, match="declared media_type"):
        resolve_fixture(
            root,
            _fixture(digest=_digest(_PNG_CONTENT), media_type="image/jpeg"),
        )

    path.write_bytes(b"")
    with pytest.raises(ValueError, match="must not be empty"):
        resolve_fixture(root, _fixture(digest=_digest(b"")))


def test_resolve_fixture_rejects_paths_that_escape_root_via_symlink(tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(_PNG_CONTENT)
    link_dir = root / "images"
    link_dir.mkdir()
    link = link_dir / "sample.png"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not supported in this environment")

    with pytest.raises(ValueError, match="escapes the configured root"):
        resolve_fixture(root, _fixture(digest=_digest(_PNG_CONTENT)))


def test_checked_in_multimodal_fixture_catalog_resolves_real_png() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    fixture_root = repo_root / "benchmarks" / "fixtures" / "multimodal-v1"
    manifest = load_fixture_manifest(fixture_root / "manifest.json")
    fixture = manifest.require("multimodal.quadrants_rgb_001")

    resolved = resolve_fixture(fixture_root, fixture)

    assert resolved.fixture.media_type == "image/png"
    assert resolved.size_bytes == 91
    assert resolved.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert fixture.digest == (
        "sha256:c016362530bd9a02aff8d3bf0b7114b38d7499b03e2acacb566f657f94bb5f76"
    )
