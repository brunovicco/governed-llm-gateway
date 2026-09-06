from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import FrozenInstanceError
from typing import cast

import pytest
from governed_llm_gateway_core.adapters.operational_evidence_json import (
    load_operational_evidence_text,
)
from governed_llm_gateway_core.domain.operational_evidence import (
    OperationalEvidenceError,
    OperationalEvidenceRecord,
    canonical_operational_evidence_json,
)


def _record(
    *,
    workload: str = "rag.answer",
    deployment: str = "openai-primary",
    gateway_requests: int = 10,
    attempts: int = 12,
    successes: int = 10,
    errors: int = 2,
    rate_limits: int = 1,
    timeouts: int = 1,
    fallback_requests: int = 2,
    p50_ms: int = 320,
    p95_ms: int = 780,
) -> dict[str, object]:
    return {
        "runtime_workload": workload,
        "deployment_id": deployment,
        "gateway_request_count": gateway_requests,
        "provider_attempt_count": attempts,
        "successful_provider_attempt_count": successes,
        "provider_error_count": errors,
        "rate_limit_error_count": rate_limits,
        "timeout_count": timeouts,
        "fallback_request_count": fallback_requests,
        "provider_latency_p50_ms": p50_ms,
        "provider_latency_p95_ms": p95_ms,
    }


def _payload(*, records: list[dict[str, object]] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "snapshot_version": "runtime-window-v1",
        "collector_id": "gateway-runtime",
        "collector_version": "collector-v1",
        "window_start": "2026-09-06T18:00:00Z",
        "window_end": "2026-09-06T19:00:00Z",
        "captured_at": "2026-09-06T19:00:05Z",
        "records": records or [_record()],
    }
    return _with_id(payload)


def _with_id(payload: dict[str, object]) -> dict[str, object]:
    result = deepcopy(payload)
    result.pop("evidence_id", None)
    records = cast(list[dict[str, object]], result["records"])
    result["records"] = sorted(
        records,
        key=lambda item: (str(item["runtime_workload"]), str(item["deployment_id"])),
    )
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    result["evidence_id"] = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return result


def _text(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def test_operational_evidence_loads_with_canonical_order_and_lookup() -> None:
    records = [
        _record(workload="reasoning.complex", deployment="z-deployment"),
        _record(workload="rag.answer", deployment="a-deployment"),
    ]
    payload = _payload(records=records)

    snapshot = load_operational_evidence_text(_text(payload))

    assert snapshot.schema_version == "1.0"
    assert [(item.runtime_workload, item.deployment_id) for item in snapshot.records] == [
        ("rag.answer", "a-deployment"),
        ("reasoning.complex", "z-deployment"),
    ]
    record = snapshot.for_runtime("rag.answer", "a-deployment")
    assert record is not None
    assert record.provider_attempt_count == 12
    assert snapshot.for_runtime("rag.answer", "missing") is None
    assert canonical_operational_evidence_json(snapshot) == _text(payload)


def test_operational_evidence_is_content_addressed() -> None:
    first_payload = _payload()
    second_payload = _payload(records=[_record(p95_ms=900)])

    first = load_operational_evidence_text(_text(first_payload))
    second = load_operational_evidence_text(_text(second_payload))

    assert first.evidence_id != second.evidence_id
    assert first.evidence_id.startswith("sha256:")


def test_operational_evidence_rejects_stale_content_identity() -> None:
    payload = _payload()
    records = cast(list[dict[str, object]], payload["records"])
    records[0]["provider_latency_p95_ms"] = 901

    with pytest.raises(OperationalEvidenceError, match="evidence_id does not match"):
        load_operational_evidence_text(_text(payload))


def test_operational_evidence_rejects_duplicate_json_keys() -> None:
    text = _text(_payload()).replace(
        '"schema_version":"1.0"',
        '"schema_version":"1.0","schema_version":"1.0"',
        1,
    )

    with pytest.raises(OperationalEvidenceError, match="duplicate operational evidence key"):
        load_operational_evidence_text(text)


def test_operational_evidence_rejects_unknown_and_missing_fields() -> None:
    unknown = _payload()
    unknown["surprise"] = True
    with pytest.raises(OperationalEvidenceError, match="unknown operational evidence fields"):
        load_operational_evidence_text(_text(unknown))

    missing = _payload()
    missing.pop("collector_version")
    missing = _with_id(missing)
    with pytest.raises(OperationalEvidenceError, match="missing operational evidence fields"):
        load_operational_evidence_text(_text(missing))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("window_start", "2026-09-06T19:00:00Z", "window_start must precede window_end"),
        ("window_start", "2026-09-06T18:00:00-03:00", "offset-aware UTC timestamp"),
        ("captured_at", "2026-09-06T18:59:59Z", "captured_at cannot precede window_end"),
    ],
)
def test_operational_evidence_rejects_invalid_time_provenance(
    field: str, value: str, message: str
) -> None:
    payload = _payload()
    payload[field] = value
    payload = _with_id(payload)

    with pytest.raises(OperationalEvidenceError, match=message):
        load_operational_evidence_text(_text(payload))


@pytest.mark.parametrize(
    ("record", "message"),
    [
        (_record(workload="raganswer"), "runtime_workload must be dotted"),
        (_record(gateway_requests=0), "gateway_request_count must be positive"),
        (_record(attempts=0, successes=0, errors=0), "provider_attempt_count must be positive"),
        (
            _record(attempts=12, successes=9, errors=2),
            "successful_provider_attempt_count.*must equal provider_attempt_count",
        ),
        (_record(errors=2, rate_limits=3), "rate_limit_error_count cannot exceed"),
        (_record(errors=2, timeouts=3), "timeout_count cannot exceed"),
        (
            _record(gateway_requests=10, fallback_requests=11),
            "fallback_request_count cannot exceed",
        ),
        (_record(p50_ms=800, p95_ms=700), "provider_latency_p95_ms cannot be less than p50"),
    ],
)
def test_operational_evidence_rejects_inconsistent_records(
    record: dict[str, object], message: str
) -> None:
    payload = _payload(records=[record])

    with pytest.raises(OperationalEvidenceError, match=message):
        load_operational_evidence_text(_text(payload))


def test_operational_evidence_rejects_duplicate_runtime_records() -> None:
    payload = _payload(records=[_record(), _record()])

    with pytest.raises(OperationalEvidenceError, match="duplicate runtime workload/deployment"):
        load_operational_evidence_text(_text(payload))


def test_operational_evidence_record_is_immutable() -> None:
    snapshot = load_operational_evidence_text(_text(_payload()))
    record = snapshot.records[0]

    with pytest.raises(FrozenInstanceError):
        delattr(record, "provider_error_count")


def test_direct_record_construction_preserves_fail_closed_invariants() -> None:
    with pytest.raises(OperationalEvidenceError, match="must equal provider_attempt_count"):
        OperationalEvidenceRecord(
            runtime_workload="rag.answer",
            deployment_id="openai-primary",
            gateway_request_count=10,
            provider_attempt_count=10,
            successful_provider_attempt_count=10,
            provider_error_count=1,
            rate_limit_error_count=0,
            timeout_count=0,
            fallback_request_count=0,
            provider_latency_p50_ms=100,
            provider_latency_p95_ms=200,
        )


def test_operational_evidence_rejects_non_mapping_or_invalid_json_root() -> None:
    with pytest.raises(OperationalEvidenceError, match="root must be a mapping"):
        load_operational_evidence_text("[]")

    with pytest.raises(OperationalEvidenceError, match="not valid JSON"):
        load_operational_evidence_text("{")
