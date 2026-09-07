"""Tests for deterministic metadata-only task-complexity assessment."""

from uuid import UUID

import pytest
from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayRequest,
    Message,
    MessageRole,
    RiskLevel,
    TaskComplexity,
    WorkloadRequirements,
)
from governed_llm_gateway_core.domain import (
    ComplexityPolicy,
    DeterministicComplexityEvaluator,
    WorkloadComplexityFloor,
)


def _policy(
    *,
    workload_floors: tuple[WorkloadComplexityFloor, ...] = (),
) -> ComplexityPolicy:
    return ComplexityPolicy(
        policy_id="deterministic-complexity",
        version="v1",
        medium_context_tokens=8_000,
        high_context_tokens=32_000,
        medium_output_tokens=2_000,
        high_output_tokens=8_000,
        tool_calling_floor=TaskComplexity.MEDIUM,
        structured_output_floor=TaskComplexity.MEDIUM,
        vision_floor=TaskComplexity.HIGH,
        workload_floors=workload_floors,
    )


def _request(
    *,
    workload: str = "demo.classification",
    requirements: WorkloadRequirements | None = None,
    content: str = "classify this request",
) -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=UUID("00000000-0000-0000-0000-000000000001"),
        workload=workload,
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.INTERNAL,
        requirements=requirements or WorkloadRequirements(),
        messages=(Message(role=MessageRole.USER, content=content),),
    )


def test_identical_metadata_and_policy_produce_identical_assessment() -> None:
    evaluator = DeterministicComplexityEvaluator(_policy())
    request = _request()

    first = evaluator.assess(
        request,
        context_tokens_estimated=500,
        max_output_tokens_estimated=200,
    )
    second = evaluator.assess(
        request,
        context_tokens_estimated=500,
        max_output_tokens_estimated=200,
    )

    assert first == second
    assert first.level is TaskComplexity.LOW
    assert len(first.assessment_id) == 64
    assert first.evaluator_id == "deterministic-complexity"
    assert first.evaluator_version == "v1"


def test_assessment_id_does_not_depend_on_prompt_content() -> None:
    evaluator = DeterministicComplexityEvaluator(_policy())
    first_request = _request(content="first secret prompt payload")
    second_request = _request(content="entirely different prompt payload")

    first = evaluator.assess(
        first_request,
        context_tokens_estimated=500,
        max_output_tokens_estimated=200,
    )
    second = evaluator.assess(
        second_request,
        context_tokens_estimated=500,
        max_output_tokens_estimated=200,
    )

    assert first == second
    assert "secret" not in first.assessment_id
    assert "prompt" not in first.assessment_id


@pytest.mark.parametrize(
    ("context_tokens", "output_tokens", "expected"),
    [
        (7_999, 1_999, TaskComplexity.LOW),
        (8_000, 1_999, TaskComplexity.MEDIUM),
        (31_999, 2_000, TaskComplexity.MEDIUM),
        (32_000, 1, TaskComplexity.HIGH),
        (1, 8_000, TaskComplexity.HIGH),
    ],
)
def test_token_threshold_boundaries_are_monotonic(
    context_tokens: int,
    output_tokens: int,
    expected: TaskComplexity,
) -> None:
    assessment = DeterministicComplexityEvaluator(_policy()).assess(
        _request(),
        context_tokens_estimated=context_tokens,
        max_output_tokens_estimated=output_tokens,
    )

    assert assessment.level is expected


def test_minimum_context_requirement_cannot_be_underclassified() -> None:
    request = _request(requirements=WorkloadRequirements(min_context_tokens=32_000))

    assessment = DeterministicComplexityEvaluator(_policy()).assess(
        request,
        context_tokens_estimated=100,
        max_output_tokens_estimated=100,
    )

    assert assessment.level is TaskComplexity.HIGH


@pytest.mark.parametrize(
    ("requirements", "expected"),
    [
        (WorkloadRequirements(tool_calling=True), TaskComplexity.MEDIUM),
        (WorkloadRequirements(structured_output=True), TaskComplexity.MEDIUM),
        (WorkloadRequirements(vision=True), TaskComplexity.HIGH),
    ],
)
def test_capability_floors_are_explicit_policy_inputs(
    requirements: WorkloadRequirements,
    expected: TaskComplexity,
) -> None:
    assessment = DeterministicComplexityEvaluator(_policy()).assess(
        _request(requirements=requirements),
        context_tokens_estimated=100,
        max_output_tokens_estimated=100,
    )

    assert assessment.level is expected


def test_workload_floor_is_applied_without_widening_any_candidate_set() -> None:
    policy = _policy(
        workload_floors=(
            WorkloadComplexityFloor(
                workload="security.analysis",
                minimum=TaskComplexity.HIGH,
            ),
        )
    )

    assessment = DeterministicComplexityEvaluator(policy).assess(
        _request(workload="security.analysis"),
        context_tokens_estimated=100,
        max_output_tokens_estimated=100,
    )

    assert assessment.level is TaskComplexity.HIGH


@pytest.mark.parametrize(
    ("context_tokens", "output_tokens", "error"),
    [
        (-1, 100, "context_tokens_estimated must be non-negative"),
        (100, 0, "max_output_tokens_estimated must be positive"),
    ],
)
def test_invalid_estimates_fail_closed(
    context_tokens: int,
    output_tokens: int,
    error: str,
) -> None:
    evaluator = DeterministicComplexityEvaluator(_policy())

    with pytest.raises(ValueError, match=error):
        evaluator.assess(
            _request(),
            context_tokens_estimated=context_tokens,
            max_output_tokens_estimated=output_tokens,
        )


def test_policy_rejects_invalid_threshold_ordering() -> None:
    with pytest.raises(
        ValueError,
        match="complexity high context token threshold must exceed medium threshold",
    ):
        ComplexityPolicy(
            policy_id="deterministic-complexity",
            version="v1",
            medium_context_tokens=8_000,
            high_context_tokens=8_000,
            medium_output_tokens=2_000,
            high_output_tokens=8_000,
            tool_calling_floor=TaskComplexity.MEDIUM,
            structured_output_floor=TaskComplexity.MEDIUM,
            vision_floor=TaskComplexity.HIGH,
        )


def test_policy_rejects_duplicate_or_unsorted_workload_floors() -> None:
    first = WorkloadComplexityFloor(
        workload="security.analysis",
        minimum=TaskComplexity.HIGH,
    )
    duplicate = WorkloadComplexityFloor(
        workload="security.analysis",
        minimum=TaskComplexity.MEDIUM,
    )
    earlier = WorkloadComplexityFloor(
        workload="demo.classification",
        minimum=TaskComplexity.LOW,
    )

    with pytest.raises(ValueError, match="must not contain duplicate workloads"):
        _policy(workload_floors=(first, duplicate))
    with pytest.raises(ValueError, match="must be sorted by workload"):
        _policy(workload_floors=(first, earlier))
