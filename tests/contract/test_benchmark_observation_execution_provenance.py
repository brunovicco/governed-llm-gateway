from __future__ import annotations

import asyncio
from datetime import date

import pytest

from benchmarks import (
    BenchmarkCase,
    BenchmarkObservation,
    BenchmarkRunner,
    BenchmarkTarget,
    BenchmarkWorkload,
    ObservationStatus,
    ProviderCall,
    Scorecard,
    build_default_scorers,
    build_snapshot,
    canonical_snapshot_json,
)

_RUN_DATE = date(2026, 9, 5)


class StaticExecutor:
    def __init__(self, call: ProviderCall) -> None:
        self._call = call

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        del case, target
        return self._call


def _case() -> BenchmarkCase:
    return BenchmarkCase(
        case_id="observation-provenance",
        workload=BenchmarkWorkload.STRUCTURED_EXTRACTION,
        scorer="exact_json",
        prompt="Return the public synthetic value.",
        expected={"value": 1},
        metadata={"synthetic": True},
    )


def _target() -> BenchmarkTarget:
    return BenchmarkTarget(
        target_id="openai-control",
        provider="openai",
        model="gpt-control",
        api="openai/responses",
        configuration="access=test;reasoning=medium",
        source_date=_RUN_DATE,
    )


def _run(call: ProviderCall) -> tuple[tuple[BenchmarkObservation, ...], tuple[Scorecard, ...]]:
    return asyncio.run(
        BenchmarkRunner(StaticExecutor(call), build_default_scorers()).run(
            (_case(),),
            (_target(),),
        )
    )


def test_completed_observation_preserves_terminal_execution_identity() -> None:
    observations, _ = _run(
        ProviderCall(
            output={"value": 1},
            latency_ms=25,
            provider="openai",
            model="gpt-control",
            deployment="openai-primary",
        )
    )

    observation = observations[0]
    assert observation.status is ObservationStatus.SUCCEEDED
    assert observation.provider == "openai"
    assert observation.model == "gpt-control"
    assert observation.deployment == "openai-primary"


def test_observation_execution_identity_is_all_or_none() -> None:
    with pytest.raises(ValueError, match="model must be present and normalized"):
        BenchmarkObservation(
            target_id="openai-control",
            case_id="partial-identity",
            workload=BenchmarkWorkload.STRUCTURED_EXTRACTION,
            status=ObservationStatus.SUCCEEDED,
            quality_score=None,
            latency_ms=1,
            ttft_ms=None,
            input_units=None,
            output_units=None,
            cost_usd=None,
            fallback_count=0,
            provider="openai",
            deployment="openai-primary",
        )


def test_snapshot_id_covers_observed_deployment_provenance() -> None:
    first_observations, first_scorecards = _run(
        ProviderCall(
            output={"value": 1},
            latency_ms=25,
            provider="openai",
            model="gpt-control",
            deployment="openai-primary",
        )
    )
    second_observations, second_scorecards = _run(
        ProviderCall(
            output={"value": 1},
            latency_ms=25,
            provider="openai",
            model="gpt-control",
            deployment="openai-fallback",
        )
    )

    first = build_snapshot(
        benchmark_version="execution-provenance-v1",
        runner_version="benchmark-runner-v1",
        run_date=_RUN_DATE,
        cases=(_case(),),
        targets=(_target(),),
        observations=first_observations,
        scorecards=first_scorecards,
    )
    second = build_snapshot(
        benchmark_version="execution-provenance-v1",
        runner_version="benchmark-runner-v1",
        run_date=_RUN_DATE,
        cases=(_case(),),
        targets=(_target(),),
        observations=second_observations,
        scorecards=second_scorecards,
    )

    assert first.snapshot_id != second.snapshot_id
    assert '"deployment":"openai-primary"' in canonical_snapshot_json(first)
    assert '"deployment":"openai-fallback"' in canonical_snapshot_json(second)


def test_legacy_snapshot_shape_omits_absent_execution_identity() -> None:
    observations, scorecards = _run(ProviderCall(output={"value": 1}, latency_ms=25))
    snapshot = build_snapshot(
        benchmark_version="legacy-replay-v1",
        runner_version="benchmark-runner-v1",
        run_date=_RUN_DATE,
        cases=(_case(),),
        targets=(_target(),),
        observations=observations,
        scorecards=scorecards,
    )

    assert '"deployment":' not in canonical_snapshot_json(snapshot)
