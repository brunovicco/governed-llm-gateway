"""Strict JSON adapter for content-addressed operational sample batches."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from governed_llm_gateway_core.application.operational_sample_batch import (
    OperationalSampleBatch,
    OperationalSampleBatchError,
    build_operational_sample_batch,
)


def load_operational_sample_batch(path: str | Path) -> OperationalSampleBatch:
    """Load and validate one UTF-8 operational sample batch artifact."""
    return load_operational_sample_batch_text(Path(path).read_text(encoding="utf-8"))


def load_operational_sample_batch_text(text: str) -> OperationalSampleBatch:
    """Strictly parse and validate operational sample batch JSON text."""
    try:
        payload = json.loads(text, object_pairs_hook=_unique_object)
    except OperationalSampleBatchError:
        raise
    except json.JSONDecodeError as exc:
        raise OperationalSampleBatchError("operational sample batch is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise OperationalSampleBatchError("operational sample batch root must be a mapping")
    return build_operational_sample_batch(cast(Mapping[str, object], payload))


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise OperationalSampleBatchError(f"duplicate operational sample batch key: {key!r}")
        payload[key] = value
    return payload
