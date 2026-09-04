"""Strict JSON adapter for promoted Phase 11 ranking evidence."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from governed_llm_gateway_core.domain.ranking_evidence import (
    PromotedRankingEvidence,
    RankingEvidenceError,
    build_promoted_ranking_evidence,
)


def load_promoted_ranking_evidence(path: str | Path) -> PromotedRankingEvidence:
    """Load and validate one UTF-8 promoted-evidence JSON artifact."""
    evidence_path = Path(path)
    return load_promoted_ranking_evidence_text(evidence_path.read_text(encoding="utf-8"))


def load_promoted_ranking_evidence_text(text: str) -> PromotedRankingEvidence:
    """Load, strictly parse, and validate promoted ranking evidence supplied as JSON text."""
    try:
        payload = json.loads(text, object_pairs_hook=_unique_object)
    except RankingEvidenceError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RankingEvidenceError("promoted ranking evidence is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise RankingEvidenceError("promoted ranking evidence root must be a mapping")
    return build_promoted_ranking_evidence(cast(Mapping[str, object], payload))


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise RankingEvidenceError(f"duplicate promoted ranking evidence key: {key!r}")
        payload[key] = value
    return payload
