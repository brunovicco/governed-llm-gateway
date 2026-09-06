from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from benchmarks import (
    BenchmarkCase,
    BenchmarkObservation,
    BenchmarkProviderFailure,
    BenchmarkQualityMetric,
    BenchmarkRunner,
    BenchmarkSnapshot,
    BenchmarkTarget,
    BenchmarkWorkload,
    ObservationStatus,
    ProviderCall,
    build_default_scorers,
    build_scorecards,
    build_snapshot,
    canonical_snapshot_json,
    evaluate_scorer,
)
from benchmarks.promotion import (
    PromotionMapping,
    canonical_promoted_evidence_json,
    promote_snapshot,
)
from benchmarks.scoring import require_scorer
from benchmarks.workloads.agent_orchestration import load_agent_orchestration_dataset
from benchmarks.workloads.json_schema_compliance import load_json_schema_compliance_dataset
from benchmarks.workloads.multi_step_tool_use import load_multi_step_tool_use_dataset
from benchmarks.workloads.rag_answer import load_rag_answer_dataset
from benchmarks.workloads.rag_ptbr import load_rag_ptbr_dataset
from benchmarks.workloads.structured_extraction_v2 import load_structured_extraction_v2_dataset
from benchmarks.workloads.tool_argument_generation import load_tool_argument_generation_dataset
from benchmarks.workloads.tool_selection import load_tool_selection_dataset
from benchmarks.workloads.tool_use import load_tool_use_dataset

_TARGET = BenchmarkTarget(
    target_id="fixture-quality-components",
    provider="fixture",
    model="quality-model",
    api="fixture-v1",
    configuration="temperature=0",
    source_date=date(2026, 9, 6),
)


class _ExpectedExecutor:
    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        return ProviderCall(
            output=case.expected,
            latency_ms=20,
            ttft_ms=5,
            input_units=10,
            output_units=4,
            cost_usd=Decimal("0.001"),
        )


class _ToolAverageExecutor:
    def __init__(self, second_case_id: str) -> None:
        self._second_case_id = second_case_id

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        output = None if case.case_id == self._second_case_id else case.expected
        return ProviderCall(output=output, latency_ms=10)


class _ToolFailureExecutor:
    def __init__(self, failed_case_id: str) -> None:
        self._failed_case_id = failed_case_id

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        if case.case_id == self._failed_case_id:
            raise BenchmarkProviderFailure(code="timeout", status_code=504, latency_ms=250)
        return ProviderCall(output=case.expected, latency_ms=10)


def _observation(
    *,
    case_id: str,
    metrics: Mapping[BenchmarkQualityMetric, Decimal],
) -> BenchmarkObservation:
    return BenchmarkObservation(
        target_id="fixture",
        case_id=case_id,
        workload=BenchmarkWorkload.TOOL_USE,
        status=ObservationStatus.SUCCEEDED,
        quality_score=Decimal("1"),
        latency_ms=10,
        ttft_ms=None,
        input_units=None,
        output_units=None,
        cost_usd=None,
        fallback_count=0,
        quality_metrics=metrics,
    )


def _component_snapshot(*, matrix: bool = False) -> BenchmarkSnapshot:
    dataset = load_tool_use_dataset(Path("benchmarks/datasets/tool-use-v1.json"))
    cases = dataset.cases[:2]
    runner = BenchmarkRunner(_ExpectedExecutor(), build_default_scorers())
    observations, scorecards = asyncio.run(runner.run(cases, (_TARGET,)))
    return build_snapshot(
        benchmark_version=dataset.benchmark_version,
        runner_version="quality-components-v1",
        run_date=date(2026, 9, 6),
        cases=cases,
        targets=(_TARGET,),
        observations=observations,
        scorecards=scorecards,
        target_matrix_version="quality-components-matrix-v1" if matrix else None,
    )


@pytest.mark.parametrize(
    ("path", "loader", "expected_metrics"),
    [
        (
            "benchmarks/datasets/structured-extraction-v2.json",
            load_structured_extraction_v2_dataset,
            {BenchmarkQualityMetric.SCHEMA_VALIDITY},
        ),
        (
            "benchmarks/datasets/json-schema-compliance-v1.json",
            load_json_schema_compliance_dataset,
            {BenchmarkQualityMetric.SCHEMA_VALIDITY},
        ),
        (
            "benchmarks/datasets/tool-use-v1.json",
            load_tool_use_dataset,
            {
                BenchmarkQualityMetric.TOOL_SELECTION_ACCURACY,
                BenchmarkQualityMetric.TOOL_ARGUMENT_ACCURACY,
            },
        ),
        (
            "benchmarks/datasets/tool-selection-v1.json",
            load_tool_selection_dataset,
            {BenchmarkQualityMetric.TOOL_SELECTION_ACCURACY},
        ),
        (
            "benchmarks/datasets/tool-argument-generation-v1.json",
            load_tool_argument_generation_dataset,
            {BenchmarkQualityMetric.TOOL_ARGUMENT_ACCURACY},
        ),
        (
            "benchmarks/datasets/multi-step-tool-use-v1.json",
            load_multi_step_tool_use_dataset,
            {
                BenchmarkQualityMetric.TOOL_SELECTION_ACCURACY,
                BenchmarkQualityMetric.TOOL_ARGUMENT_ACCURACY,
                BenchmarkQualityMetric.TRAJECTORY_SUCCESS,
            },
        ),
        (
            "benchmarks/datasets/agent-orchestration-v1.json",
            load_agent_orchestration_dataset,
            {BenchmarkQualityMetric.TRAJECTORY_SUCCESS},
        ),
        (
            "benchmarks/datasets/rag-answer-v1.json",
            load_rag_answer_dataset,
            {BenchmarkQualityMetric.GROUNDING},
        ),
    ],
)
def test_reviewed_component_scorers_preserve_scalar_api_and_metrics(
    path: str,
    loader: object,
    expected_metrics: set[BenchmarkQualityMetric],
) -> None:
    typed_loader = cast(object, loader)
    if not callable(typed_loader):
        raise AssertionError("parameterized dataset loader must be callable")
    dataset = typed_loader(Path(path))
    case = dataset.cases[0]
    scorer = require_scorer(build_default_scorers(), case.scorer)

    scalar = scorer(case, case.expected)
    measurement = evaluate_scorer(scorer, case, case.expected)

    assert scalar == Decimal("1")
    assert measurement.score == scalar
    assert set(measurement.metrics) == expected_metrics
    assert all(value == Decimal("1") for value in measurement.metrics.values())


def test_rag_ptbr_does_not_claim_a_separate_language_quality_component() -> None:
    dataset = load_rag_ptbr_dataset(Path("benchmarks/datasets/rag-ptbr-v1.json"))
    case = dataset.cases[0]
    expected = case.expected
    assert isinstance(expected, list)
    output = " ".join(item for item in expected if isinstance(item, str))
    scorer = require_scorer(build_default_scorers(), case.scorer)

    measurement = evaluate_scorer(scorer, case, output)

    assert measurement.score == Decimal("1")
    assert measurement.metrics == {}


def test_runner_preserves_and_aggregates_component_metrics() -> None:
    dataset = load_tool_use_dataset(Path("benchmarks/datasets/tool-use-v1.json"))
    cases = dataset.cases[:2]
    runner = BenchmarkRunner(
        _ToolAverageExecutor(cases[1].case_id),
        build_default_scorers(),
    )

    observations, scorecards = asyncio.run(runner.run(cases, (_TARGET,)))

    assert observations[0].quality_metrics == {
        BenchmarkQualityMetric.TOOL_SELECTION_ACCURACY: Decimal("1"),
        BenchmarkQualityMetric.TOOL_ARGUMENT_ACCURACY: Decimal("1"),
    }
    assert observations[1].quality_metrics == {
        BenchmarkQualityMetric.TOOL_SELECTION_ACCURACY: Decimal("0"),
        BenchmarkQualityMetric.TOOL_ARGUMENT_ACCURACY: Decimal("0"),
    }
    assert scorecards[0].mean_quality_metrics == {
        BenchmarkQualityMetric.TOOL_SELECTION_ACCURACY: Decimal("0.5"),
        BenchmarkQualityMetric.TOOL_ARGUMENT_ACCURACY: Decimal("0.5"),
    }


def test_provider_failure_does_not_create_or_dilute_quality_components() -> None:
    dataset = load_tool_use_dataset(Path("benchmarks/datasets/tool-use-v1.json"))
    cases = dataset.cases[:3]
    runner = BenchmarkRunner(
        _ToolFailureExecutor(cases[0].case_id),
        build_default_scorers(),
    )

    observations, scorecards = asyncio.run(runner.run(cases, (_TARGET,)))

    assert observations[0].status is ObservationStatus.PROVIDER_FAILURE
    assert observations[0].quality_score is None
    assert observations[0].quality_metrics == {}
    assert scorecards[0].completed_calls == 2
    assert scorecards[0].provider_failures == 1
    assert scorecards[0].mean_quality_metrics == {
        BenchmarkQualityMetric.TOOL_SELECTION_ACCURACY: Decimal("1"),
        BenchmarkQualityMetric.TOOL_ARGUMENT_ACCURACY: Decimal("1"),
    }


def test_scorecard_fails_closed_on_partial_component_coverage() -> None:
    observations = (
        _observation(
            case_id="case-1",
            metrics={BenchmarkQualityMetric.TOOL_SELECTION_ACCURACY: Decimal("1")},
        ),
        _observation(case_id="case-2", metrics={}),
    )

    with pytest.raises(ValueError, match="consistent quality metrics"):
        build_scorecards(observations)


def test_quality_component_contracts_are_bounded_and_immutable() -> None:
    observation = _observation(
        case_id="case-1",
        metrics={BenchmarkQualityMetric.SCHEMA_VALIDITY: Decimal("1")},
    )
    mutable = cast(dict[BenchmarkQualityMetric, Decimal], observation.quality_metrics)
    with pytest.raises(TypeError):
        mutable[BenchmarkQualityMetric.SCHEMA_VALIDITY] = Decimal("0")

    invalid_key = cast(
        Mapping[BenchmarkQualityMetric, Decimal],
        {"schema_validity": Decimal("1")},
    )
    with pytest.raises(ValueError, match="keys must use BenchmarkQualityMetric"):
        _observation(case_id="case-2", metrics=invalid_key)

    with pytest.raises(ValueError, match="values must be Decimal values from 0 to 1"):
        _observation(
            case_id="case-3",
            metrics={BenchmarkQualityMetric.SCHEMA_VALIDITY: Decimal("1.1")},
        )

    with pytest.raises(ValueError, match="provider failures must not carry quality component"):
        BenchmarkObservation(
            target_id="fixture",
            case_id="provider-failure",
            workload=BenchmarkWorkload.TOOL_USE,
            status=ObservationStatus.PROVIDER_FAILURE,
            quality_score=None,
            latency_ms=10,
            ttft_ms=None,
            input_units=None,
            output_units=None,
            cost_usd=None,
            fallback_count=0,
            provider_error_code="timeout",
            quality_metrics={BenchmarkQualityMetric.TOOL_SELECTION_ACCURACY: Decimal("0")},
        )


def test_component_snapshot_uses_schema_1_2_and_is_content_addressed() -> None:
    first = _component_snapshot()
    second = _component_snapshot()

    assert first.schema_version == "1.2"
    assert first.snapshot_id == second.snapshot_id
    canonical = canonical_snapshot_json(first)
    assert '"quality_metrics":{"tool_argument_accuracy":"1","tool_selection_accuracy":"1"}' in canonical
    assert '"mean_quality_metrics":{"tool_argument_accuracy":"1","tool_selection_accuracy":"1"}' in canonical


def test_component_snapshot_can_retain_target_matrix_provenance() -> None:
    snapshot = _component_snapshot(matrix=True)

    assert snapshot.schema_version == "1.2"
    assert snapshot.target_matrix_version == "quality-components-matrix-v1"
    assert snapshot.target_matrix_digest is not None
    assert snapshot.target_matrix_digest.startswith("sha256:")


def test_historical_snapshot_schemas_remain_component_free() -> None:
    case = BenchmarkCase(
        case_id="legacy-exact",
        workload=BenchmarkWorkload.CLASSIFICATION,
        scorer="exact_json",
        prompt="legacy component-free snapshot",
        expected={"label": "alpha"},
    )
    runner = BenchmarkRunner(_ExpectedExecutor(), build_default_scorers())
    observations, scorecards = asyncio.run(runner.run((case,), (_TARGET,)))

    schema_1_0 = build_snapshot(
        benchmark_version="legacy-v1",
        runner_version="legacy-runner",
        run_date=date(2026, 9, 6),
        cases=(case,),
        targets=(_TARGET,),
        observations=observations,
        scorecards=scorecards,
    )
    schema_1_1 = build_snapshot(
        benchmark_version="legacy-v1",
        runner_version="legacy-runner",
        run_date=date(2026, 9, 6),
        cases=(case,),
        targets=(_TARGET,),
        observations=observations,
        scorecards=scorecards,
        target_matrix_version="legacy-matrix-v1",
    )

    assert schema_1_0.schema_version == "1.0"
    assert schema_1_1.schema_version == "1.1"
    assert "quality_metrics" not in canonical_snapshot_json(schema_1_0)
    assert "quality_metrics" not in canonical_snapshot_json(schema_1_1)


def test_historical_schema_versions_reject_component_evidence() -> None:
    component = _component_snapshot()
    with pytest.raises(ValueError, match="schema 1.0 must not carry quality component"):
        replace(
            component,
            schema_version="1.0",
            target_matrix_version=None,
            target_matrix_digest=None,
        )

    matrix_component = _component_snapshot(matrix=True)
    with pytest.raises(ValueError, match="schema 1.1 must not carry quality component"):
        replace(matrix_component, schema_version="1.1")


def test_promotion_remains_scalar_and_does_not_implicitly_promote_components() -> None:
    snapshot = _component_snapshot()
    promoted = promote_snapshot(
        snapshot,
        promotion_version="quality-components-promotion-v1",
        approval_date=date(2026, 9, 6),
        approved_by="benchmark-review",
        mappings=(
            PromotionMapping(
                target_id=_TARGET.target_id,
                benchmark_workload=BenchmarkWorkload.TOOL_USE,
                deployment_id="fixture-deployment",
                runtime_workload="benchmark.tool_use",
            ),
        ),
    )

    assert promoted.records[0].quality_score == Decimal("1")
    canonical = canonical_promoted_evidence_json(promoted)
    assert "quality_metrics" not in canonical
    assert "mean_quality_metrics" not in canonical
