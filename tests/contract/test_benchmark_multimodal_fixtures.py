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


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _fixture(*, digest: str, relative_path: str = "images/sample.png") -> BenchmarkFixture:
    return BenchmarkFixture(
        fixture_id="multimodal.sample_001",
        media_type="image/png",
        relative_path=relative_path,
        digest=digest,
    )


def test_fixture_manifest_loads_strict_public_catalog(tmp_path: Path) -> None:
    content = b"synthetic-image-bytes"
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
                        "digest": _digest(content),
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
    digest = _digest(b"fixture")

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
    digest = _digest(b"fixture")

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
    content = b"synthetic-image-bytes-v1"
    (image_dir / "sample.png").write_bytes(content)
    fixture = _fixture(digest=_digest(content))

    resolved = resolve_fixture(root, fixture)

    assert resolved.fixture is fixture
    assert resolved.content == content
    assert resolved.size_bytes == len(content)


def test_resolve_fixture_fails_closed_on_digest_size_and_empty_content(tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    image_dir = root / "images"
    image_dir.mkdir(parents=True)
    path = image_dir / "sample.png"
    content = b"fixture-content"
    path.write_bytes(content)

    with pytest.raises(ValueError, match="digest mismatch"):
        resolve_fixture(root, _fixture(digest=_digest(b"different")))

    with pytest.raises(ValueError, match="byte limit"):
        resolve_fixture(root, _fixture(digest=_digest(content)), max_bytes=len(content) - 1)

    path.write_bytes(b"")
    with pytest.raises(ValueError, match="must not be empty"):
        resolve_fixture(root, _fixture(digest=_digest(b"")))


def test_resolve_fixture_rejects_paths_that_escape_root_via_symlink(tmp_path: Path) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    outside = tmp_path / "outside.png"
    content = b"outside-content"
    outside.write_bytes(content)
    link_dir = root / "images"
    link_dir.mkdir()
    link = link_dir / "sample.png"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not supported in this environment")

    with pytest.raises(ValueError, match="escapes the configured root"):
        resolve_fixture(root, _fixture(digest=_digest(content)))
