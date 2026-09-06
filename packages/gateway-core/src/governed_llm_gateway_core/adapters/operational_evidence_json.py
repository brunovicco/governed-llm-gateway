"""Strict JSON adapter for recent operational evidence snapshots."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from governed_llm_gateway_core.domain.operational_evidence import (
    OperationalEvidenceError,
    OperationalEvidenceSnapshot,
    build_operational_evidence_snapshot,
)


def load_operational_evidence(path: str | Path) -> OperationalEvidenceSnapshot:
    """Load and validate one UTF-8 operational-evidence JSON artifact."""
    evidence_path = Path(path)
    return load_operational_evidence_text(evidence_path.read_text(encoding="utf-8"))


def load_operational_evidence_text(text: str) -> OperationalEvidenceSnapshot:
    """Strictly parse and validate operational evidence supplied as JSON text."""
    try:
        payload = json.loads(text, object_pairs_hook=_unique_object)
    except OperationalEvidenceError:
        raise
    except json.JSONDecodeError as exc:
        raise OperationalEvidenceError("operational evidence is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise OperationalEvidenceError("operational evidence root must be a mapping")
    return build_operational_evidence_snapshot(cast(Mapping[str, object], payload))


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise OperationalEvidenceError(f"duplicate operational evidence key: {key!r}")
        payload[key] = value
    return payload
