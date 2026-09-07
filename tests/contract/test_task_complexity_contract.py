"""Contract tests for provider-neutral task-complexity metadata."""

from typing import cast

import pytest
from governed_llm_gateway_contracts import ComplexityAssessment, TaskComplexity


def test_task_complexity_vocabulary_is_stable() -> None:
    assert tuple(item.value for item in TaskComplexity) == ("low", "medium", "high")


def test_complexity_assessment_preserves_bounded_metadata_only_provenance() -> None:
    assessment = ComplexityAssessment(
        level=TaskComplexity.HIGH,
        assessment_id="assessment-001",
        evaluator_id="deterministic-complexity",
        evaluator_version="v1",
    )

    assert assessment.level is TaskComplexity.HIGH
    assert assessment.assessment_id == "assessment-001"
    assert assessment.evaluator_id == "deterministic-complexity"
    assert assessment.evaluator_version == "v1"


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("assessment_id", ""),
        ("assessment_id", " assessment-001"),
        ("evaluator_id", "Evaluator"),
        ("evaluator_version", "v1/preview"),
    ],
)
def test_complexity_assessment_rejects_malformed_provenance(
    field_name: str,
    invalid_value: str,
) -> None:
    assessment_id = invalid_value if field_name == "assessment_id" else "assessment-001"
    evaluator_id = invalid_value if field_name == "evaluator_id" else "deterministic-complexity"
    evaluator_version = invalid_value if field_name == "evaluator_version" else "v1"
    error_pattern = rf"complexity {field_name} must be a normalized identifier"

    with pytest.raises(ValueError, match=error_pattern):
        ComplexityAssessment(
            level=TaskComplexity.MEDIUM,
            assessment_id=assessment_id,
            evaluator_id=evaluator_id,
            evaluator_version=evaluator_version,
        )


def test_complexity_assessment_rejects_non_vocab_level() -> None:
    error_pattern = "complexity level must use the provider-neutral vocabulary"

    with pytest.raises(ValueError, match=error_pattern):
        ComplexityAssessment(
            level=cast(TaskComplexity, "high"),
            assessment_id="assessment-001",
            evaluator_id="deterministic-complexity",
            evaluator_version="v1",
        )
