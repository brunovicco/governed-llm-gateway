import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from governed_llm_gateway_core.adapters.operational_sample_batch_json import (
    load_operational_sample_batch_text,
)
from governed_llm_gateway_core.adapters.operational_sample_batch_source import (
    OperationalSampleBatchSource,
)
from governed_llm_gateway_core.application.operational_evidence import (
    OperationalAttemptSample,
    OperationalEvidenceMaterializationError,
    OperationalEvidenceMaterializer,
    OperationalProviderErrorKind,
    OperationalSampleOutcome,
)
from governed_llm_gateway_core.application.operational_sample_batch import (
    OperationalSampleBatchError,
    OperationalSampleBatchExporter,
    build_operational_sample_batch,
    canonical_operational_sample_batch_json,
    create_operational_sample_batch,
)

START = datetime(2026, 9, 6, 20, 0, tzinfo=UTC)
END = START + timedelta(minutes=5)
EXPORTED = END + timedelta(seconds=1)
REQUEST_A = UUID("00000000-0000-0000-0000-000000000001")
REQUEST_B = UUID("00000000-0000-0000-0000-000000000002")


def _sample(
    *,
    observed_at: datetime,
    request_id: UUID,
    attempt_number: int,
    fallback_index: int = 0,
    outcome: OperationalSampleOutcome = OperationalSampleOutcome.SUCCEEDED,
    error_kind: OperationalProviderErrorKind | None = None,
    latency_ms: int = 100,
    deployment_id: str = "openai-primary",
) -> OperationalAttemptSample:
    return OperationalAttemptSample(
        observed_at=observed_at,
        gateway_request_id=request_id,
        runtime_workload="support.answer",
        deployment_id=deployment_id,
        attempt_number=attempt_number,
        fallback_index=fallback_index,
        outcome=outcome,
        error_kind=error_kind,
        latency_ms=latency_ms,
    )


def _samples() -> tuple[OperationalAttemptSample, ...]:
    return (
        _sample(
            observed_at=START + timedelta(seconds=10),
            request_id=REQUEST_A,
            attempt_number=1,
            latency_ms=120,
        ),
        _sample(
            observed_at=START + timedelta(seconds=20),
            request_id=REQUEST_A,
            attempt_number=2,
            outcome=OperationalSampleOutcome.PROVIDER_ERROR,
            error_kind=OperationalProviderErrorKind.RATE_LIMIT,
            latency_ms=180,
        ),
        _sample(
            observed_at=START + timedelta(seconds=30),
            request_id=REQUEST_B,
            attempt_number=1,
            fallback_index=1,
            latency_ms=90,
            deployment_id="anthropic-fallback",
        ),
    )


def _batch():
    return create_operational_sample_batch(
        batch_version="runtime-samples-v1",
        source_instance_id="gateway-replica-a",
        exporter_id="local-batch-exporter",
        exporter_version="1.0",
        window_start=START,
        window_end=END,
        exported_at=EXPORTED,
        samples=_samples(),
    )


class StaticSource:
    def __init__(self, samples: tuple[OperationalAttemptSample, ...]) -> None:
        self.samples = samples
        self.calls: list[tuple[datetime, datetime]] = []

    async def read_window(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[OperationalAttemptSample, ...]:
        self.calls.append((window_start, window_end))
        return self.samples


class FailingSource:
    async def read_window(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[OperationalAttemptSample, ...]:
        del window_start, window_end
        raise OperationalEvidenceMaterializationError("incomplete runtime history")


def test_factory_canonicalizes_samples_and_derives_stable_identity() -> None:
    reversed_samples = tuple(reversed(_samples()))
    first = create_operational_sample_batch(
        batch_version="runtime-samples-v1",
        source_instance_id="gateway-replica-a",
        exporter_id="local-batch-exporter",
        exporter_version="1.0",
        window_start=START,
        window_end=END,
        exported_at=EXPORTED,
        samples=reversed_samples,
    )
    second = _batch()

    assert first.samples == second.samples
    assert first.batch_id == second.batch_id
    assert first.batch_id.startswith("sha256:")


def test_canonical_json_round_trip_preserves_identity() -> None:
    batch = _batch()

    loaded = load_operational_sample_batch_text(
        canonical_operational_sample_batch_json(batch)
    )

    assert loaded == batch


def test_loader_rejects_duplicate_json_object_keys() -> None:
    text = canonical_operational_sample_batch_json(_batch())
    duplicated = text.replace(
        '"schema_version":"1.0"',
        '"schema_version":"1.0","schema_version":"1.0"',
        1,
    )

    with pytest.raises(OperationalSampleBatchError, match="duplicate operational sample batch key"):
        load_operational_sample_batch_text(duplicated)


def test_builder_rejects_unknown_fields() -> None:
    payload = json.loads(canonical_operational_sample_batch_json(_batch()))
    payload["unexpected"] = True

    with pytest.raises(OperationalSampleBatchError, match="unknown operational sample batch fields"):
        build_operational_sample_batch(payload)


def test_builder_rejects_noncanonical_sample_order() -> None:
    payload = json.loads(canonical_operational_sample_batch_json(_batch()))
    payload["samples"] = list(reversed(payload["samples"]))

    with pytest.raises(OperationalSampleBatchError, match="canonical ordering"):
        build_operational_sample_batch(payload)


def test_builder_rejects_duplicate_attempt_identity() -> None:
    payload = json.loads(canonical_operational_sample_batch_json(_batch()))
    samples = payload["samples"]
    samples.insert(1, dict(samples[0]))

    with pytest.raises(OperationalSampleBatchError, match="duplicate operational provider-attempt"):
        build_operational_sample_batch(payload)


def test_builder_rejects_sample_outside_declared_window() -> None:
    payload = json.loads(canonical_operational_sample_batch_json(_batch()))
    payload["samples"][0]["observed_at"] = (START - timedelta(seconds=1)).isoformat().replace(
        "+00:00", "Z"
    )

    with pytest.raises(OperationalSampleBatchError, match="outside declared window"):
        build_operational_sample_batch(payload)


def test_builder_rejects_tampered_content_identity() -> None:
    payload = json.loads(canonical_operational_sample_batch_json(_batch()))
    payload["exporter_version"] = "2.0"

    with pytest.raises(OperationalSampleBatchError, match="batch_id does not match"):
        build_operational_sample_batch(payload)


def test_exporter_reads_exact_complete_window_and_preserves_provenance() -> None:
    source = StaticSource(_samples())
    exporter = OperationalSampleBatchExporter(
        source,
        source_instance_id="gateway-replica-a",
        exporter_id="local-batch-exporter",
        exporter_version="1.0",
        clock=lambda: EXPORTED,
    )

    batch = asyncio.run(
        exporter.export(
            batch_version="runtime-samples-v1",
            window_start=START,
            window_end=END,
        )
    )

    assert source.calls == [(START, END)]
    assert batch.source_instance_id == "gateway-replica-a"
    assert batch.exporter_id == "local-batch-exporter"
    assert batch.exporter_version == "1.0"
    assert batch.window_start == START
    assert batch.window_end == END
    assert batch.exported_at == EXPORTED
    assert batch.samples == _samples()


def test_exporter_rejects_empty_window() -> None:
    exporter = OperationalSampleBatchExporter(
        StaticSource(()),
        source_instance_id="gateway-replica-a",
        exporter_id="local-batch-exporter",
        exporter_version="1.0",
        clock=lambda: EXPORTED,
    )

    with pytest.raises(OperationalSampleBatchError, match="contains no provider-attempt samples"):
        asyncio.run(
            exporter.export(
                batch_version="runtime-samples-v1",
                window_start=START,
                window_end=END,
            )
        )


def test_exporter_fails_closed_when_source_cannot_prove_completeness() -> None:
    exporter = OperationalSampleBatchExporter(
        FailingSource(),
        source_instance_id="gateway-replica-a",
        exporter_id="local-batch-exporter",
        exporter_version="1.0",
        clock=lambda: EXPORTED,
    )

    with pytest.raises(OperationalSampleBatchError, match="complete export window"):
        asyncio.run(
            exporter.export(
                batch_version="runtime-samples-v1",
                window_start=START,
                window_end=END,
            )
        )


def test_batch_source_returns_complete_subwindow_and_exposes_scope() -> None:
    source = OperationalSampleBatchSource(_batch())
    sub_start = START + timedelta(seconds=15)
    sub_end = START + timedelta(seconds=31)

    samples = asyncio.run(
        source.read_window(window_start=sub_start, window_end=sub_end)
    )

    assert source.source_instance_id == "gateway-replica-a"
    assert source.window_start == START
    assert source.window_end == END
    assert len(samples) == 2
    assert samples[0].gateway_request_id == REQUEST_A
    assert samples[1].gateway_request_id == REQUEST_B


def test_batch_source_rejects_window_outside_declared_coverage() -> None:
    source = OperationalSampleBatchSource(_batch())

    with pytest.raises(OperationalEvidenceMaterializationError, match="cannot prove"):
        asyncio.run(
            source.read_window(
                window_start=START - timedelta(seconds=1),
                window_end=END,
            )
        )

    with pytest.raises(OperationalEvidenceMaterializationError, match="cannot prove"):
        asyncio.run(
            source.read_window(
                window_start=START,
                window_end=END + timedelta(seconds=1),
            )
        )


def test_loaded_batch_source_is_compatible_with_existing_materializer() -> None:
    loaded = load_operational_sample_batch_text(
        canonical_operational_sample_batch_json(_batch())
    )
    materializer = OperationalEvidenceMaterializer(
        OperationalSampleBatchSource(loaded),
        collector_id="batch-materializer",
        collector_version="1.0",
        clock=lambda: EXPORTED + timedelta(seconds=1),
    )

    snapshot = asyncio.run(
        materializer.materialize(
            snapshot_version="operational-v1",
            window_start=START,
            window_end=END,
        )
    )

    assert len(snapshot.records) == 2
    primary = snapshot.for_runtime("support.answer", "openai-primary")
    fallback = snapshot.for_runtime("support.answer", "anthropic-fallback")
    assert primary is not None
    assert primary.provider_attempt_count == 2
    assert primary.provider_error_count == 1
    assert primary.rate_limit_error_count == 1
    assert fallback is not None
    assert fallback.fallback_request_count == 1


def test_batch_contract_rejects_export_timestamp_before_window_end() -> None:
    with pytest.raises(OperationalSampleBatchError, match="exported_at cannot precede"):
        create_operational_sample_batch(
            batch_version="runtime-samples-v1",
            source_instance_id="gateway-replica-a",
            exporter_id="local-batch-exporter",
            exporter_version="1.0",
            window_start=START,
            window_end=END,
            exported_at=END - timedelta(microseconds=1),
            samples=_samples(),
        )
