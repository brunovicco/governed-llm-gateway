"""Structured-extraction v1 benchmark contract and end-to-end evidence tests."""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import (
    BenchmarkCase,
    BenchmarkTarget,
    BenchmarkWorkload,
    ObservationStatus,
    ProviderCall,
)
from benchmarks.promotion import PromotionMapping, promote_snapshot
from benchmarks.runner import BenchmarkRunner
from benchmarks.scoring import build_default_scorers
from benchmarks.snapshot import build_snapshot, canonical_snapshot_json
from benchmarks.workloads.structured_extraction import (
    STRUCTURED_EXTRACTION_SCORER_ID,
    load_structured_extraction_dataset,
    score_structured_extraction,
)

_DATASET = Path("benchmarks/datasets/structured-extraction-v1.json")


class _DeterministicStructuredExecutor:
    """Credential-free fixture executor that echoes reviewed expected objects."""

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        assert target.target_id == "fixture-structured-v1"
        return ProviderCall(
            output=case.expected,
            latency_ms=25,
            ttft_ms=10,
            input_units=20,
            output_units=8,
            cost_usd=Decimal("0.001"),
        )


def test_structured_extraction_dataset_is_versioned_public_and_bounded() -> None:
    dataset = load_structured_extraction_dataset(_DATASET)

    assert dataset.schema_version == "1.0"
    assert dataset.benchmark_version == "structured-extraction-v1"
    assert dataset.data_classification == "public"
    assert len(dataset.cases) == 6
    assert all(case.workload is BenchmarkWorkload.STRUCTURED_EXTRACTION for case in dataset.cases)
    assert all(case.scorer == STRUCTURED_EXTRACTION_SCORER_ID for case in dataset.cases)


def test_structured_extraction_scorer_penalizes_missing_extra_and_wrong_typed_fields() -> None:
    dataset = load_structured_extraction_dataset(_DATASET)
    invoice = dataset.cases[0]
    ticket = dataset.cases[2]

    assert score_structured_extraction(invoice, invoice.expected) == Decimal("1")

    assert isinstance(invoice.expected, dict)
    missing = dict(invoice.expected)
    missing.pop("currency")
    assert score_structured_extraction(invoice, missing) == Decimal("0.75")

    extra = dict(invoice.expected)
    extra["unexpected"] = "value"
    assert score_structured_extraction(invoice, extra) == Decimal("0.8")

    assert isinstance(ticket.expected, dict)
    wrong_type = dict(ticket.expected)
    wrong_type["production_impact"] = 1
    assert score_structured_extraction(ticket, wrong_type) == Decimal("0.75")

    assert score_structured_extraction(invoice, "not-an-object") == Decimal("0")


def test_structured_extraction_pipeline_reaches_explicit_promotion() -> None:
    dataset = load_structured_extraction_dataset(_DATASET)
    target = BenchmarkTarget(
        target_id="fixture-structured-v1",
        provider="fixture",
        model="structured-model",
        api="fixture-v1",
        configuration="temperature=0;structured_output=true",
        source_date=date(2026, 9, 4),
    )
    runner = BenchmarkRunner(_DeterministicStructuredExecutor(), build_default_scorers())

    observations, scorecards = asyncio.run(runner.run(dataset.cases, (target,)))

    assert len(observations) == len(dataset.cases)
    assert all(item.status is ObservationStatus.SUCCEEDED for item in observations)
    assert all(item.quality_score == Decimal("1") for item in observations)
    assert len(scorecards) == 1

    scorecard = scorecards[0]
    assert scorecard.workload is BenchmarkWorkload.STRUCTURED_EXTRACTION
    assert scorecard.total_cases == 6
    assert scorecard.completed_calls == 6
    assert scorecard.provider_failures == 0
    assert scorecard.mean_quality_score == Decimal("1")
    assert scorecard.availability_rate == Decimal("1")
    assert scorecard.total_input_units == 120
    assert scorecard.total_output_units == 48
    assert scorecard.total_cost_usd == Decimal("0.006")

    snapshot = build_snapshot(
        benchmark_version=dataset.benchmark_version,
        runner_version="structured-extraction-runner-v1",
        run_date=date(2026, 9, 4),
        cases=dataset.cases,
        targets=(target,),
        observations=observations,
        scorecards=scorecards,
    )
    assert snapshot.snapshot_id.startswith("sha256:")
    assert snapshot.dataset_digest.startswith("sha256:")
    snapshot_json = canonical_snapshot_json(snapshot)
    assert '"workload":"structured_extraction"' in snapshot_json
    assert '"quality_score":"1"' in snapshot_json

    promoted = promote_snapshot(
        snapshot,
        promotion_version="structured-extraction-promotion-v1",
        approval_date=date(2026, 9, 4),
        approved_by="benchmark-review",
        mappings=(
            PromotionMapping(
                target_id=target.target_id,
                benchmark_workload=BenchmarkWorkload.STRUCTURED_EXTRACTION,
                deployment_id="fixture-deployment",
                runtime_workload="benchmark.structured_extraction",
            ),
        ),
    )

    assert promoted.evidence_id.startswith("sha256:")
    assert promoted.benchmark_snapshot_id == snapshot.snapshot_id
    assert len(promoted.records) == 1
    record = promoted.records[0]
    assert record.quality_score == Decimal("1")
    assert record.availability_rate == Decimal("1")
    assert record.total_cases == 6
    assert record.completed_calls == 6
    assert record.cost_per_completed_call_usd == Decimal("0.001")
