"""Code-generation v1 benchmark contract and end-to-end evidence tests."""

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
from benchmarks.workloads.code_generation import (
    load_code_generation_dataset,
    score_code_generation,
)

_DATASET = Path("benchmarks/datasets/code-generation-v1.json")


class _CanonicalCodeExecutor:
    """Credential-free fixture returning reviewed canonical source without executing it."""

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        assert isinstance(case.expected, str)
        return ProviderCall(
            output=case.expected,
            latency_ms=20,
            ttft_ms=8,
            input_units=18,
            output_units=10,
            cost_usd=Decimal("0.0015"),
        )


def test_code_generation_dataset_is_public_synthetic_and_never_executed() -> None:
    dataset = load_code_generation_dataset(_DATASET)

    assert dataset.benchmark_version == "code-generation-v1"
    assert dataset.data_classification == "public"
    assert len(dataset.cases) == 6
    assert all(case.workload is BenchmarkWorkload.CODE_GENERATION for case in dataset.cases)
    assert all(case.metadata["execute_candidate"] is False for case in dataset.cases)


def test_code_generation_scorer_compares_ast_without_execution() -> None:
    case = load_code_generation_dataset(_DATASET).cases[0]

    equivalent = "# formatting is irrelevant\ndef double(value):\n\n    return value * 2\n"
    assert score_code_generation(case, equivalent) == Decimal("1")
    assert score_code_generation(case, "def double(value):\n    return value + 2\n") == Decimal("0")
    assert score_code_generation(case, "def double(value)\n    return value * 2\n") == Decimal("0")
    assert score_code_generation(case, "not code") == Decimal("0")


def test_code_generation_scorer_rejects_dangerous_candidate_primitives() -> None:
    case = load_code_generation_dataset(_DATASET).cases[0]

    subprocess_candidate = "import subprocess\ndef double(value):\n    return value * 2\n"
    eval_candidate = "def double(value):\n    return eval('value * 2')\n"
    open_candidate = "def double(value):\n    return open('x')\n"
    assert score_code_generation(case, subprocess_candidate) == Decimal("0")
    assert score_code_generation(case, eval_candidate) == Decimal("0")
    assert score_code_generation(case, open_candidate) == Decimal("0")


def test_code_generation_pipeline_reaches_explicit_promotion() -> None:
    dataset = load_code_generation_dataset(_DATASET)
    target = BenchmarkTarget(
        target_id="fixture-code-generation-v1",
        provider="fixture",
        model="code-model",
        api="fixture-v1",
        configuration="temperature=0;candidate_execution=false",
        source_date=date(2026, 9, 4),
    )
    runner = BenchmarkRunner(_CanonicalCodeExecutor(), build_default_scorers())

    observations, scorecards = asyncio.run(runner.run(dataset.cases, (target,)))

    assert len(observations) == 6
    assert all(item.status is ObservationStatus.SUCCEEDED for item in observations)
    assert all(item.quality_score == Decimal("1") for item in observations)
    assert len(scorecards) == 1
    scorecard = scorecards[0]
    assert scorecard.workload is BenchmarkWorkload.CODE_GENERATION
    assert scorecard.total_cases == 6
    assert scorecard.mean_quality_score == Decimal("1")
    assert scorecard.total_cost_usd == Decimal("0.0090")

    snapshot = build_snapshot(
        benchmark_version=dataset.benchmark_version,
        runner_version="code-generation-runner-v1",
        run_date=date(2026, 9, 4),
        cases=dataset.cases,
        targets=(target,),
        observations=observations,
        scorecards=scorecards,
    )
    promoted = promote_snapshot(
        snapshot,
        promotion_version="code-generation-promotion-v1",
        approval_date=date(2026, 9, 4),
        approved_by="benchmark-review",
        mappings=(
            PromotionMapping(
                target_id=target.target_id,
                benchmark_workload=BenchmarkWorkload.CODE_GENERATION,
                deployment_id="fixture-deployment",
                runtime_workload="benchmark.code_generation",
            ),
        ),
    )

    assert promoted.benchmark_snapshot_id == snapshot.snapshot_id
    assert promoted.records[0].quality_score == Decimal("1")
