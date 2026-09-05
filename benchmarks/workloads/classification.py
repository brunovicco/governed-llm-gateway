"""Deterministic closed-set classification benchmark contract and scorer."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

CLASSIFICATION_BENCHMARK_VERSION = "classification-v1"
CLASSIFICATION_CONTRACT_VERSION = "1.0"
CLASSIFICATION_SCORER_ID = "classification_v1"
CLASSIFICATION_LABEL_SET = "support-intents-v1"
CLASSIFICATION_RESPONSE_FORMAT = "classification_label_v1"
CLASSIFICATION_LABELS = frozenset(
    {
        "account_access",
        "billing",
        "general_information",
        "sales",
        "security",
        "technical_support",
    }
)

_ALLOWED_METADATA_FIELDS = {
    "contract_version",
    "label_set",
    "response_format",
    "synthetic",
}
_EXPECTED_CASES_PER_LABEL = 2


@dataclass(frozen=True, slots=True, order=True)
class ClassificationIssue:
    """Stable reason code and JSON-pointer-like path for one classification issue."""

    code: str
    path: str


@dataclass(frozen=True, slots=True)
class ClassificationAssessment:
    """Explainable deterministic evidence for one closed-set classification answer."""

    score: Decimal
    issues: tuple[ClassificationIssue, ...]

    @property
    def classification_success(self) -> bool:
        """Return whether the reviewed label matched exactly."""
        return self.score == Decimal("1") and not self.issues


def load_classification_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate the complete reviewed classification-v1 dataset."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    if dataset.benchmark_version != CLASSIFICATION_BENCHMARK_VERSION:
        raise ValueError("classification v1 requires benchmark_version classification-v1")

    case_ids = [case.case_id for case in dataset.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("classification v1 case IDs must be unique")

    label_counts = {label: 0 for label in CLASSIFICATION_LABELS}
    for case in dataset.cases:
        validate_classification_case(case)
        label = _validated_expected_label(case.expected)
        label_counts[label] += 1

    if any(count != _EXPECTED_CASES_PER_LABEL for count in label_counts.values()):
        raise ValueError("classification v1 requires exactly two cases for every reviewed label")
    return dataset


def validate_classification_case(case: BenchmarkCase) -> None:
    """Fail closed when a case drifts from the reviewed v1 classification contract."""
    if case.workload is not BenchmarkWorkload.CLASSIFICATION:
        raise ValueError("classification v1 dataset contains a different workload")
    if case.scorer != CLASSIFICATION_SCORER_ID:
        raise ValueError("classification v1 requires its versioned deterministic scorer")

    metadata = case.metadata
    unknown_metadata = sorted(set(metadata) - _ALLOWED_METADATA_FIELDS)
    if unknown_metadata:
        fields = ", ".join(unknown_metadata)
        raise ValueError(f"classification v1 metadata contains unknown fields: {fields}")
    if metadata.get("contract_version") != CLASSIFICATION_CONTRACT_VERSION:
        raise ValueError("classification v1 contract_version must be 1.0")
    if metadata.get("label_set") != CLASSIFICATION_LABEL_SET:
        raise ValueError("classification v1 label_set must be support-intents-v1")
    if metadata.get("response_format") != CLASSIFICATION_RESPONSE_FORMAT:
        raise ValueError("classification v1 response_format must be classification_label_v1")
    if metadata.get("synthetic") is not True:
        raise ValueError("classification v1 cases must be explicitly synthetic")

    _validated_expected_label(case.expected)


def assess_classification(
    case: BenchmarkCase,
    output: JsonValue,
) -> ClassificationAssessment:
    """Return deterministic exact-label classification evidence."""
    validate_classification_case(case)
    expected_label = _validated_expected_label(case.expected)

    if not isinstance(output, dict) or set(output) != {"label"}:
        return _zero_assessment(ClassificationIssue("invalid_output_shape", "/"))

    label = output.get("label")
    if not isinstance(label, str):
        return _zero_assessment(ClassificationIssue("wrong_label_type", "/label"))
    if label not in CLASSIFICATION_LABELS:
        return _zero_assessment(ClassificationIssue("unknown_label", "/label"))
    if label != expected_label:
        return _zero_assessment(ClassificationIssue("wrong_label", "/label"))
    return ClassificationAssessment(score=Decimal("1"), issues=())


def score_classification(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Return the scalar v1 score consumed by BenchmarkRunner."""
    return assess_classification(case, output).score


def _validated_expected_label(expected: JsonValue) -> str:
    if not isinstance(expected, dict) or set(expected) != {"label"}:
        raise ValueError("classification v1 expected output must contain exactly the label field")
    label = expected.get("label")
    if not isinstance(label, str) or label not in CLASSIFICATION_LABELS:
        raise ValueError("classification v1 expected label must be in the reviewed label set")
    return label


def _zero_assessment(issue: ClassificationIssue) -> ClassificationAssessment:
    return ClassificationAssessment(score=Decimal("0"), issues=(issue,))
