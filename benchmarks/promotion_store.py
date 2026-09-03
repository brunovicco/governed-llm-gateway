"""Immutable persistence for explicitly promoted Phase 11 benchmark evidence."""

from __future__ import annotations

from pathlib import Path

from .promotion import PromotedBenchmarkEvidence, canonical_promoted_evidence_json


def persist_promoted_evidence(root: Path, evidence: PromotedBenchmarkEvidence) -> Path:
    """Persist content-addressed promotion evidence idempotently and fail on collisions."""
    version_dir = root / evidence.promotion_version
    version_dir.mkdir(parents=True, exist_ok=True)
    evidence_name = evidence.evidence_id.removeprefix("sha256:")
    path = version_dir / f"{evidence_name}.json"
    content = canonical_promoted_evidence_json(evidence)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError("promoted evidence ID collision with different content")
        return path
    path.write_text(content, encoding="utf-8")
    return path
