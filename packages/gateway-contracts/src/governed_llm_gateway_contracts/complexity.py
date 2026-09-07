"""Provider-neutral task-complexity assessment metadata."""

from dataclasses import dataclass
from re import fullmatch

from .enums import TaskComplexity

_PROVENANCE_IDENTIFIER_PATTERN = r"[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?"


@dataclass(frozen=True, slots=True)
class ComplexityAssessment:
    """Metadata-only, non-authoritative task-complexity assessment provenance."""

    level: TaskComplexity
    assessment_id: str
    evaluator_id: str
    evaluator_version: str

    def __post_init__(self) -> None:
        """Fail closed on malformed or ambiguous complexity provenance."""
        if not isinstance(self.level, TaskComplexity):
            raise ValueError("complexity level must use the provider-neutral vocabulary")
        _validate_identifier(self.assessment_id, "assessment_id")
        _validate_identifier(self.evaluator_id, "evaluator_id")
        _validate_identifier(self.evaluator_version, "evaluator_version")


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or fullmatch(_PROVENANCE_IDENTIFIER_PATTERN, value) is None:
        raise ValueError(f"complexity {field_name} must be a normalized identifier")
