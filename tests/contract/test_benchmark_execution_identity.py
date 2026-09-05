from __future__ import annotations

import asyncio
from datetime import date

import pytest

from benchmarks import (
    BenchmarkCase,
    BenchmarkRunner,
    BenchmarkTarget,
    BenchmarkTargetMismatchError,
    BenchmarkWorkload,
    ObservationStatus,
    ProviderCall,
    build_default_scorers,
)


class StaticExecutor:
    def __init__(self, call: ProviderCall) -> None:
        self._call = call

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        del case, target
        return self._call


def _case() -> BenchmarkCase:
    return BenchmarkCase(
        case_id="execution-identity",
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
        source_date=date(2026, 9, 5),
    )


def test_provider_call_execution_identity_is_all_or_none() -> None:
    with pytest.raises(ValueError, match="model must be present and normalized"):
        ProviderCall(
            output={"value": 1},
            latency_ms=10,
            provider="openai",
            deployment="openai-control",
        )


def test_runner_accepts_observed_provider_and_model_matching_target() -> None:
    call = ProviderCall(
        output={"value": 1},
        latency_ms=10,
        provider="openai",
        model="gpt-control",
        deployment="openai-control",
    )
    runner = BenchmarkRunner(StaticExecutor(call), build_default_scorers())

    observations, scorecards = asyncio.run(runner.run((_case(),), (_target(),)))

    assert observations[0].status is ObservationStatus.SUCCEEDED
    assert scorecards[0].target_id == "openai-control"


def test_runner_rejects_observed_provider_or_model_mismatch_before_scoring() -> None:
    call = ProviderCall(
        output={"value": 1},
        latency_ms=10,
        provider="anthropic",
        model="claude-control",
        deployment="anthropic-control",
    )
    runner = BenchmarkRunner(StaticExecutor(call), build_default_scorers())

    with pytest.raises(BenchmarkTargetMismatchError, match="does not match declared target"):
        asyncio.run(runner.run((_case(),), (_target(),)))


def test_runner_preserves_legacy_executor_compatibility_without_identity() -> None:
    call = ProviderCall(output={"value": 1}, latency_ms=10)
    runner = BenchmarkRunner(StaticExecutor(call), build_default_scorers())

    observations, _ = asyncio.run(runner.run((_case(),), (_target(),)))

    assert observations[0].status is ObservationStatus.SUCCEEDED
