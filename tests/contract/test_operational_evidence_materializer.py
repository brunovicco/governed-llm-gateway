import asyncio
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
from governed_llm_gateway_core.adapters.operational_evidence_json import (
    load_operational_evidence_text,
)
from governed_llm_gateway_core.adapters.operational_samples_memory import (
    InMemoryOperationalSampleStore,
)
from governed_llm_gateway_core.application.operational_evidence import (
    OperationalAttemptSample,
    OperationalEvidenceMaterializationError,
    OperationalEvidenceMaterializer,
    OperationalProviderErrorKind,
    OperationalSampleOutcome,
)
from governed_llm_gateway_core.domain.operational_evidence import (
    OperationalEvidenceRecord,
    canonical_operational_evidence_json,
    create_operational_evidence_snapshot,
)

REQUEST_A = UUID("11111111-1111-4111-8111-111111111111")
REQUEST_B = UUID("22222222-2222-4222-8222-222222222222")
BASE = datetime(2026, 9, 6, 20, 0, tzinfo=UTC)


class MutableUtcClock:
    def __init__(self, value: datetime = BASE) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class StaticSource:
    def __init__(self, *samples: OperationalAttemptSample) -> None:
        self.samples = tuple(samples)

    async def read_window(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[OperationalAttemptSample, ...]:
        del window_start, window_end
        return self.samples


def _sample(
    *,
    seconds: int,
    request_id: UUID = REQUEST_A,
    workload: str = "rag.answer",
    deployment: str = "openai-primary",
    attempt: int = 1,
    fallback_index: int = 0,
    outcome: OperationalSampleOutcome = OperationalSampleOutcome.SUCCEEDED,
    error_kind: OperationalProviderErrorKind | None = None,
    latency_ms: int = 100,
) -> OperationalAttemptSample:
    return OperationalAttemptSample(
        observed_at=BASE + timedelta(seconds=seconds),
        gateway_request_id=request_id,
        runtime_workload=workload,
        deployment_id=deployment,
        attempt_number=attempt,
        fallback_index=fallback_index,
        outcome=outcome,
        error_kind=error_kind,
        latency_ms=latency_ms,
    )


def test_attempt_sample_is_immutable_and_rejects_invalid_semantics() -> None:
    sample = _sample(seconds=1)
    with pytest.raises(FrozenInstanceError):
        delattr(sample, "latency_ms")

    with pytest.raises(OperationalEvidenceMaterializationError, match="gateway_request_id"):
        OperationalAttemptSample(
            observed_at=BASE,
            gateway_request_id=cast(UUID, "not-a-uuid"),
            runtime_workload="rag.answer",
            deployment_id="openai-primary",
            attempt_number=1,
            fallback_index=0,
            outcome=OperationalSampleOutcome.SUCCEEDED,
            error_kind=None,
            latency_ms=1,
        )
    with pytest.raises(
        OperationalEvidenceMaterializationError,
        match="runtime_workload must be dotted",
    ):
        _sample(seconds=1, workload="raganswer")
    with pytest.raises(OperationalEvidenceMaterializationError, match="attempt_number"):
        _sample(seconds=1, attempt=0)
    with pytest.raises(OperationalEvidenceMaterializationError, match="fallback_index"):
        _sample(seconds=1, fallback_index=-1)
    with pytest.raises(OperationalEvidenceMaterializationError, match="latency_ms"):
        _sample(seconds=1, latency_ms=-1)
    with pytest.raises(OperationalEvidenceMaterializationError, match="cannot carry error_kind"):
        _sample(
            seconds=1,
            outcome=OperationalSampleOutcome.SUCCEEDED,
            error_kind=OperationalProviderErrorKind.OTHER,
        )
    with pytest.raises(OperationalEvidenceMaterializationError, match="must carry error_kind"):
        _sample(seconds=1, outcome=OperationalSampleOutcome.PROVIDER_ERROR)


def test_attempt_sample_rejects_boolean_integer_fields() -> None:
    with pytest.raises(OperationalEvidenceMaterializationError, match="attempt_number"):
        _sample(seconds=1, attempt=True)
    with pytest.raises(OperationalEvidenceMaterializationError, match="fallback_index"):
        _sample(seconds=1, fallback_index=False)
    with pytest.raises(OperationalEvidenceMaterializationError, match="latency_ms"):
        _sample(seconds=1, latency_ms=False)


def test_in_memory_source_requires_complete_recent_coverage() -> None:
    clock = MutableUtcClock()
    store = InMemoryOperationalSampleStore(max_samples=4, clock=clock)
    clock.advance(10)
    store.record(_sample(seconds=5))

    assert store.coverage_start == BASE
    result = asyncio.run(
        store.read_window(
            window_start=BASE,
            window_end=BASE + timedelta(seconds=10),
        )
    )
    assert result == (_sample(seconds=5),)

    with pytest.raises(
        OperationalEvidenceMaterializationError,
        match="before process-local source coverage",
    ):
        asyncio.run(
            store.read_window(
                window_start=BASE - timedelta(seconds=1),
                window_end=BASE + timedelta(seconds=1),
            )
        )
    with pytest.raises(
        OperationalEvidenceMaterializationError,
        match="window_end cannot be in the future",
    ):
        asyncio.run(
            store.read_window(
                window_start=BASE,
                window_end=BASE + timedelta(seconds=11),
            )
        )


def test_in_memory_source_fails_closed_after_capacity_eviction() -> None:
    clock = MutableUtcClock()
    store = InMemoryOperationalSampleStore(max_samples=2, clock=clock)
    for seconds in (1, 2, 3):
        clock.value = BASE + timedelta(seconds=seconds)
        store.record(_sample(seconds=seconds, attempt=seconds))

    assert store.evicted_through == BASE + timedelta(seconds=1)
    with pytest.raises(OperationalEvidenceMaterializationError, match="capacity-evicted history"):
        asyncio.run(
            store.read_window(
                window_start=BASE,
                window_end=BASE + timedelta(seconds=3),
            )
        )

    result = asyncio.run(
        store.read_window(
            window_start=BASE + timedelta(seconds=1, microseconds=1),
            window_end=BASE + timedelta(seconds=3),
        )
    )
    assert [sample.attempt_number for sample in result] == [2]


def test_in_memory_source_rejects_future_and_out_of_order_samples() -> None:
    clock = MutableUtcClock()
    store = InMemoryOperationalSampleStore(max_samples=3, clock=clock)
    clock.advance(10)
    store.record(_sample(seconds=5))
    with pytest.raises(OperationalEvidenceMaterializationError, match="non-decreasing"):
        store.record(_sample(seconds=4, attempt=2))
    with pytest.raises(OperationalEvidenceMaterializationError, match="from the future"):
        store.record(_sample(seconds=11, attempt=2))


def test_materializer_aggregates_retries_fallbacks_errors_and_percentiles() -> None:
    samples = (
        _sample(
            seconds=1,
            request_id=REQUEST_A,
            attempt=1,
            outcome=OperationalSampleOutcome.PROVIDER_ERROR,
            error_kind=OperationalProviderErrorKind.RATE_LIMIT,
            latency_ms=10,
        ),
        _sample(seconds=2, request_id=REQUEST_A, attempt=2, latency_ms=20),
        _sample(
            seconds=3,
            request_id=REQUEST_B,
            attempt=1,
            outcome=OperationalSampleOutcome.PROVIDER_ERROR,
            error_kind=OperationalProviderErrorKind.TIMEOUT,
            latency_ms=30,
        ),
        _sample(
            seconds=4,
            request_id=REQUEST_B,
            attempt=2,
            outcome=OperationalSampleOutcome.PROVIDER_ERROR,
            error_kind=OperationalProviderErrorKind.OTHER,
            latency_ms=40,
        ),
        _sample(
            seconds=5,
            request_id=REQUEST_B,
            deployment="anthropic-fallback",
            attempt=1,
            fallback_index=1,
            latency_ms=50,
        ),
    )
    clock = MutableUtcClock(BASE + timedelta(seconds=10))
    materializer = OperationalEvidenceMaterializer(
        StaticSource(*samples),
        collector_id="gateway-runtime",
        collector_version="collector-v1",
        clock=clock,
    )

    snapshot = asyncio.run(
        materializer.materialize(
            snapshot_version="window-v1",
            window_start=BASE,
            window_end=BASE + timedelta(seconds=6),
        )
    )

    primary = snapshot.for_runtime("rag.answer", "openai-primary")
    assert primary is not None
    assert primary.gateway_request_count == 2
    assert primary.provider_attempt_count == 4
    assert primary.successful_provider_attempt_count == 1
    assert primary.provider_error_count == 3
    assert primary.rate_limit_error_count == 1
    assert primary.timeout_count == 1
    assert primary.fallback_request_count == 0
    assert primary.provider_latency_p50_ms == 20
    assert primary.provider_latency_p95_ms == 40

    fallback = snapshot.for_runtime("rag.answer", "anthropic-fallback")
    assert fallback is not None
    assert fallback.gateway_request_count == 1
    assert fallback.provider_attempt_count == 1
    assert fallback.fallback_request_count == 1
    assert fallback.provider_latency_p50_ms == 50
    assert fallback.provider_latency_p95_ms == 50


def test_materializer_counts_fallback_requests_once_per_request() -> None:
    samples = (
        _sample(seconds=1, fallback_index=1, attempt=1, latency_ms=10),
        _sample(seconds=2, fallback_index=1, attempt=2, latency_ms=20),
    )
    clock = MutableUtcClock(BASE + timedelta(seconds=5))
    snapshot = asyncio.run(
        OperationalEvidenceMaterializer(
            StaticSource(*samples),
            collector_id="gateway-runtime",
            collector_version="collector-v1",
            clock=clock,
        ).materialize(
            snapshot_version="window-v1",
            window_start=BASE,
            window_end=BASE + timedelta(seconds=3),
        )
    )
    record = snapshot.records[0]
    assert record.gateway_request_count == 1
    assert record.provider_attempt_count == 2
    assert record.fallback_request_count == 1


def test_materializer_fails_closed_on_duplicate_or_out_of_window_samples() -> None:
    duplicate = _sample(seconds=1)
    clock = MutableUtcClock(BASE + timedelta(seconds=10))
    materializer = OperationalEvidenceMaterializer(
        StaticSource(duplicate, duplicate),
        collector_id="gateway-runtime",
        collector_version="collector-v1",
        clock=clock,
    )
    with pytest.raises(OperationalEvidenceMaterializationError, match="duplicate operational"):
        asyncio.run(
            materializer.materialize(
                snapshot_version="window-v1",
                window_start=BASE,
                window_end=BASE + timedelta(seconds=2),
            )
        )

    materializer = OperationalEvidenceMaterializer(
        StaticSource(_sample(seconds=5)),
        collector_id="gateway-runtime",
        collector_version="collector-v1",
        clock=clock,
    )
    with pytest.raises(OperationalEvidenceMaterializationError, match="outside requested window"):
        asyncio.run(
            materializer.materialize(
                snapshot_version="window-v1",
                window_start=BASE,
                window_end=BASE + timedelta(seconds=5),
            )
        )


def test_materializer_rejects_empty_window_and_future_capture_boundary() -> None:
    clock = MutableUtcClock(BASE + timedelta(seconds=4))
    empty = OperationalEvidenceMaterializer(
        StaticSource(),
        collector_id="gateway-runtime",
        collector_version="collector-v1",
        clock=clock,
    )
    with pytest.raises(
        OperationalEvidenceMaterializationError,
        match="contains no provider-attempt",
    ):
        asyncio.run(
            empty.materialize(
                snapshot_version="window-v1",
                window_start=BASE,
                window_end=BASE + timedelta(seconds=3),
            )
        )

    too_early = OperationalEvidenceMaterializer(
        StaticSource(_sample(seconds=1)),
        collector_id="gateway-runtime",
        collector_version="collector-v1",
        clock=MutableUtcClock(BASE + timedelta(seconds=1)),
    )
    with pytest.raises(OperationalEvidenceMaterializationError, match="captured_at cannot precede"):
        asyncio.run(
            too_early.materialize(
                snapshot_version="window-v1",
                window_start=BASE,
                window_end=BASE + timedelta(seconds=2),
            )
        )


def test_public_factory_preserves_existing_canonical_schema_1_0_identity() -> None:
    record = OperationalEvidenceRecord(
        runtime_workload="rag.answer",
        deployment_id="openai-primary",
        gateway_request_count=1,
        provider_attempt_count=1,
        successful_provider_attempt_count=1,
        provider_error_count=0,
        rate_limit_error_count=0,
        timeout_count=0,
        fallback_request_count=0,
        provider_latency_p50_ms=100,
        provider_latency_p95_ms=100,
    )
    snapshot = create_operational_evidence_snapshot(
        snapshot_version="window-v1",
        collector_id="gateway-runtime",
        collector_version="collector-v1",
        window_start=BASE,
        window_end=BASE + timedelta(seconds=1),
        captured_at=BASE + timedelta(seconds=2),
        records=(record,),
    )
    canonical = canonical_operational_evidence_json(snapshot)
    loaded = load_operational_evidence_text(canonical)

    assert loaded == snapshot
    assert canonical_operational_evidence_json(loaded) == canonical
    assert loaded.evidence_id == snapshot.evidence_id
