"""PT-BR RAG v1 benchmark contract and end-to-end evidence tests."""

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
from benchmarks.snapshot import build_snapshot
from benchmarks.workloads.rag_ptbr import load_rag_ptbr_dataset, score_rag_ptbr

_DATASET = Path("benchmarks/datasets/rag-ptbr-v1.json")


class _GroundedFixtureExecutor:
    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        assert isinstance(case.expected, list)
        output = "Resposta baseada no contexto: " + "; ".join(
            item for item in case.expected if isinstance(item, str)
        )
        return ProviderCall(
            output=output,
            latency_ms=30,
            ttft_ms=12,
            input_units=30,
            output_units=12,
            cost_usd=Decimal("0.002"),
        )


def test_rag_ptbr_dataset_is_public_synthetic_and_bounded() -> None:
    dataset = load_rag_ptbr_dataset(_DATASET)

    assert dataset.benchmark_version == "rag-ptbr-v1"
    assert dataset.data_classification == "public"
    assert len(dataset.cases) == 6
    assert all(case.workload is BenchmarkWorkload.RAG_PTBR for case in dataset.cases)


def test_rag_ptbr_scorer_measures_fact_coverage_and_forbidden_claims() -> None:
    case = load_rag_ptbr_dataset(_DATASET).cases[0]

    assert score_rag_ptbr(case, "O prazo é 24 horas e aprova o gestor responsável.") == Decimal("1")
    assert score_rag_ptbr(case, "O prazo é 24 horas.") == Decimal("0.5")
    assert score_rag_ptbr(
        case,
        "O prazo é 24 horas, mas há aprovação automática pelo gestor responsável.",
    ) == Decimal("0")
    assert score_rag_ptbr(case, {"answer": "24 horas"}) == Decimal("0")


def test_rag_ptbr_pipeline_reaches_explicit_promotion() -> None:
    dataset = load_rag_ptbr_dataset(_DATASET)
    target = BenchmarkTarget(
        target_id="fixture-rag-ptbr-v1",
        provider="fixture",
        model="rag-model",
        api="fixture-v1",
        configuration="temperature=0;context_only=true",
        source_date=date(2026, 9, 4),
    )
    runner = BenchmarkRunner(_GroundedFixtureExecutor(), build_default_scorers())

    observations, scorecards = asyncio.run(runner.run(dataset.cases, (target,)))

    assert all(item.status is ObservationStatus.SUCCEEDED for item in observations)
    assert all(item.quality_score == Decimal("1") for item in observations)
    assert len(scorecards) == 1
    scorecard = scorecards[0]
    assert scorecard.workload is BenchmarkWorkload.RAG_PTBR
    assert scorecard.total_cases == 6
    assert scorecard.mean_quality_score == Decimal("1")
    assert scorecard.total_cost_usd == Decimal("0.012")

    snapshot = build_snapshot(
        benchmark_version=dataset.benchmark_version,
        runner_version="rag-ptbr-runner-v1",
        run_date=date(2026, 9, 4),
        cases=dataset.cases,
        targets=(target,),
        observations=observations,
        scorecards=scorecards,
    )
    promoted = promote_snapshot(
        snapshot,
        promotion_version="rag-ptbr-promotion-v1",
        approval_date=date(2026, 9, 4),
        approved_by="benchmark-review",
        mappings=(
            PromotionMapping(
                target_id=target.target_id,
                benchmark_workload=BenchmarkWorkload.RAG_PTBR,
                deployment_id="fixture-deployment",
                runtime_workload="benchmark.rag_ptbr",
            ),
        ),
    )

    assert promoted.benchmark_snapshot_id == snapshot.snapshot_id
    assert promoted.records[0].quality_score == Decimal("1")
