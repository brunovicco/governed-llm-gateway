"""Contract tests for provider-neutral task-complexity metadata."""

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
    values = {
        "level": TaskComplexity.MEDIUM,
        "assessment_id": "assessment-001",
        "evaluator_id": "deterministic-complexity",
        "evaluator_version": "v1",
    }
    values[field_name] = invalid_value

    with pytest.raises(ValueError, match=rf"complexity {field_name} must be a normalized identifier"):
        ComplexityAssessment(**values)  # type: ignore[arg-type]


def test_complexity_assessment_rejects_non_vocab_level() -> None:
    with pytest.raises(ValueError, match="complexity level must use the provider-neutral vocabulary"):
        ComplexityAssessment(
            level="high",  # type: ignore[arg-type]
            assessment_id="assessment-001",
            evaluator_id="deterministic-complexity",
            evaluator_version="v1",
        )
