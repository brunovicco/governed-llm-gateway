import asyncio
import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks import (
    BenchmarkCase,
    BenchmarkProviderFailure,
    BenchmarkRunner,
    BenchmarkTarget,
    BenchmarkWorkload,
    ObservationStatus,
    ProviderCall,
    build_default_scorers,
    build_snapshot,
    canonical_snapshot_json,
    dataset_digest,
    load_dataset,
    load_targets,
    persist_snapshot,
)
from benchmarks.contracts import JsonValue

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "benchmarks/datasets/gateway-eval-v1.json"
TARGETS_PATH = ROOT / "benchmarks/runners/targets-v1.json"
TODAY = date(2026, 9, 3)


class SequenceExecutor:
    def __init__(self, outcomes: dict[str, ProviderCall | BenchmarkProviderFailure]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        del target
        self.calls.append(case.case_id)
        outcome = self.outcomes[case.case_id]
        if isinstance(outcome, BenchmarkProviderFailure):
            raise outcome
        return outcome


def _target(configuration: str = "access=test;temperature=0") -> BenchmarkTarget:
    return BenchmarkTarget(
        target_id="provider-model-control",
        provider="provider",
        model="model-v1",
        api="provider/native",
        configuration=configuration,
        source_date=TODAY,
    )


def _case(case_id: str, expected: JsonValue, *, scorer: str = "exact_json") -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        workload=BenchmarkWorkload.STRUCTURED_EXTRACTION,
        scorer=scorer,
        prompt=f"public synthetic prompt for {case_id}",
        expected=expected,
        metadata={"synthetic": True},
    )


def test_initial_dataset_is_public_versioned_and_covers_five_workloads() -> None:
    dataset = load_dataset(DATASET_PATH)

    assert dataset.schema_version == "1.0"
    assert dataset.benchmark_version == "gateway-eval-v1"
    assert dataset.data_classification == "public"
    assert len(dataset.cases) == 10
    assert {case.workload for case in dataset.cases} == set(BenchmarkWorkload)
    assert dataset_digest(dataset.cases) == dataset_digest(load_dataset(DATASET_PATH).cases)


def test_dataset_loader_rejects_unknown_fields(tmp_path: Path) -> None:
    payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown fields"):
        load_dataset(path)


def test_target_matrix_identifies_provider_model_api_configuration_and_date() -> None:
    matrix_version, targets = load_targets(TARGETS_PATH)

    assert matrix_version == "phase10-targets-v1"
    assert len(targets) == 6
    assert {target.provider for target in targets} == {
        "anthropic",
        "google",
        "groq",
        "nvidia",
        "openai",
        "openrouter",
    }
    assert all(target.model for target in targets)
    assert all(target.api for target in targets)
    assert all(target.configuration for target in targets)
    assert {target.source_date for target in targets} == {TODAY}
    assert any("access=free" in target.configuration for target in targets)
    assert any("access=paid_control" in target.configuration for target in targets)


def test_runner_separates_quality_failure_from_provider_availability() -> None:
    cases = (
        _case("success", {"value": 1}),
        _case("quality-failure", {"value": 2}),
        _case("provider-failure", {"value": 3}),
    )
    executor = SequenceExecutor(
        {
            "success": ProviderCall(
                output={"value": 1},
                latency_ms=100,
                ttft_ms=20,
                input_units=10,
                output_units=2,
                cost_usd=Decimal("0.01"),
                fallback_count=1,
            ),
            "quality-failure": ProviderCall(
                output={"value": 0},
                latency_ms=200,
                ttft_ms=40,
                input_units=11,
                output_units=3,
                cost_usd=Decimal("0.02"),
            ),
            "provider-failure": BenchmarkProviderFailure(
                code="rate_limit",
                status_code=429,
                latency_ms=50,
            ),
        }
    )
    runner = BenchmarkRunner(executor, build_default_scorers())

    observations, scorecards = asyncio.run(runner.run(cases, (_target(),)))

    assert [item.status for item in observations] == [
        ObservationStatus.SUCCEEDED,
        ObservationStatus.QUALITY_FAILURE,
        ObservationStatus.PROVIDER_FAILURE,
    ]
    assert observations[2].quality_score is None
    assert observations[2].provider_error_code == "rate_limit"

    scorecard = scorecards[0]
    assert scorecard.total_cases == 3
    assert scorecard.completed_calls == 2
    assert scorecard.provider_failures == 1
    assert scorecard.quality_successes == 1
    assert scorecard.quality_failures == 1
    assert scorecard.availability_rate == Decimal(2) / Decimal(3)
    assert scorecard.quality_success_rate == Decimal("0.5")
    assert scorecard.mean_quality_score == Decimal("0.5")
    assert scorecard.latency_p50_ms == 100
    assert scorecard.latency_p95_ms == 200
    assert scorecard.ttft_p50_ms == 20
    assert scorecard.ttft_p95_ms == 40
    assert scorecard.total_input_units == 21
    assert scorecard.total_output_units == 5
    assert scorecard.total_cost_usd == Decimal("0.03")
    assert scorecard.rate_limit_errors == 1
    assert scorecard.fallback_frequency == Decimal("0.5")
    assert scorecard.provider_error_counts == {"rate_limit": 1}


def test_unknown_scorer_fails_before_any_provider_call() -> None:
    case = _case("unknown-scorer", {"value": 1}, scorer="not-registered")
    executor = SequenceExecutor({})
    runner = BenchmarkRunner(executor, build_default_scorers())

    with pytest.raises(ValueError, match="unknown deterministic scorers"):
        asyncio.run(runner.run((case,), (_target(),)))

    assert executor.calls == []


def test_snapshot_id_is_reproducible_and_covers_configuration(tmp_path: Path) -> None:
    cases = (_case("success", {"value": 1}),)
    executor = SequenceExecutor(
        {
            "success": ProviderCall(
                output={"value": 1},
                latency_ms=100,
                input_units=10,
                output_units=2,
                cost_usd=Decimal("0.01"),
            )
        }
    )
    observations, scorecards = asyncio.run(
        BenchmarkRunner(executor, build_default_scorers()).run(cases, (_target(),))
    )

    first = build_snapshot(
        benchmark_version="gateway-eval-v1",
        runner_version="phase10-runner-v1",
        run_date=TODAY,
        cases=cases,
        targets=(_target(),),
        observations=observations,
        scorecards=scorecards,
    )
    second = build_snapshot(
        benchmark_version="gateway-eval-v1",
        runner_version="phase10-runner-v1",
        run_date=TODAY,
        cases=cases,
        targets=(_target(),),
        observations=observations,
        scorecards=scorecards,
    )
    changed_target = _target("access=test;temperature=0;reasoning=high")
    changed = build_snapshot(
        benchmark_version="gateway-eval-v1",
        runner_version="phase10-runner-v1",
        run_date=TODAY,
        cases=cases,
        targets=(changed_target,),
        observations=observations,
        scorecards=scorecards,
    )

    assert first.snapshot_id == second.snapshot_id
    assert canonical_snapshot_json(first) == canonical_snapshot_json(second)
    assert changed.snapshot_id != first.snapshot_id
    assert first.snapshot_id.startswith("sha256:")
    assert first.dataset_digest == dataset_digest(cases)

    path = persist_snapshot(tmp_path, first)
    assert persist_snapshot(tmp_path, first) == path
    assert path.parent.name == "gateway-eval-v1"
    assert path.read_text(encoding="utf-8") == canonical_snapshot_json(first)


def test_dataset_digest_changes_when_case_content_changes() -> None:
    case = _case("digest", {"value": 1})
    changed = replace(case, prompt="different public synthetic prompt")

    assert dataset_digest((case,)) != dataset_digest((changed,))
