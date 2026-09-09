"""Deterministic answer-only reasoning benchmark contract and scorer."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

REASONING_BENCHMARK_VERSION = "reasoning-v1"
REASONING_CONTRACT_VERSION = "1.0"
REASONING_SCORER_ID = "reasoning_v1"
REASONING_RESPONSE_FORMAT = "reasoning_answer_v1"
REASONING_FAMILIES = frozenset({"arithmetic", "boolean_logic", "constraint", "sequence"})

_ALLOWED_METADATA_FIELDS = {
    "answer_only",
    "contract_version",
    "family",
    "response_format",
    "synthetic",
}
_EXPECTED_CASES_PER_FAMILY = 3
_PROMPT_PREFIX = (
    "Solve this synthetic reasoning problem. Return only JSON with the key answer and do not "
    "provide chain-of-thought or explanation. Problem: "
)


@dataclass(frozen=True, slots=True, order=True)
class ReasoningIssue:
    """Stable reason code and JSON-pointer-like path for one reasoning-answer issue."""

    code: str
    path: str


@dataclass(frozen=True, slots=True)
class ReasoningAssessment:
    """Explainable deterministic evidence for one observable final answer."""

    score: Decimal
    issues: tuple[ReasoningIssue, ...]

    @property
    def reasoning_success(self) -> bool:
        """Return whether the reviewed final answer matched exactly."""
        return self.score == Decimal("1") and not self.issues


def load_reasoning_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate the complete reviewed reasoning-v1 dataset."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    if dataset.benchmark_version != REASONING_BENCHMARK_VERSION:
        raise ValueError("reasoning v1 requires benchmark_version reasoning-v1")

    case_ids = [case.case_id for case in dataset.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("reasoning v1 case IDs must be unique")

    family_counts = dict.fromkeys(REASONING_FAMILIES, 0)
    for case in dataset.cases:
        validate_reasoning_case(case)
        family = case.metadata.get("family")
        if not isinstance(family, str):
            raise AssertionError("validated reasoning family must be a string")
        family_counts[family] += 1

    if any(count != _EXPECTED_CASES_PER_FAMILY for count in family_counts.values()):
        raise ValueError("reasoning v1 requires exactly three cases for every reviewed family")
    return dataset


def validate_reasoning_case(case: BenchmarkCase) -> None:
    """Fail closed when a case drifts from the reviewed answer-only v1 contract."""
    if case.workload is not BenchmarkWorkload.REASONING:
        raise ValueError("reasoning v1 dataset contains a different workload")
    if case.scorer != REASONING_SCORER_ID:
        raise ValueError("reasoning v1 requires its versioned deterministic scorer")
    if (
        not case.prompt.startswith(_PROMPT_PREFIX)
        or case.prompt.strip() != case.prompt
        or len(case.prompt) == len(_PROMPT_PREFIX)
    ):
        raise ValueError("reasoning v1 prompt must use the reviewed answer-only instruction")

    metadata = case.metadata
    unknown_metadata = sorted(set(metadata) - _ALLOWED_METADATA_FIELDS)
    if unknown_metadata:
        fields = ", ".join(unknown_metadata)
        raise ValueError(f"reasoning v1 metadata contains unknown fields: {fields}")
    if metadata.get("contract_version") != REASONING_CONTRACT_VERSION:
        raise ValueError("reasoning v1 contract_version must be 1.0")
    family = metadata.get("family")
    if not isinstance(family, str) or family not in REASONING_FAMILIES:
        raise ValueError("reasoning v1 family must be in the reviewed family set")
    if metadata.get("response_format") != REASONING_RESPONSE_FORMAT:
        raise ValueError("reasoning v1 response_format must be reasoning_answer_v1")
    if metadata.get("synthetic") is not True:
        raise ValueError("reasoning v1 cases must be explicitly synthetic")
    if metadata.get("answer_only") is not True:
        raise ValueError("reasoning v1 cases must remain answer-only")

    _validated_expected_answer(case.expected)


def assess_reasoning(case: BenchmarkCase, output: JsonValue) -> ReasoningAssessment:
    """Return deterministic exact final-answer evidence without hidden reasoning."""
    validate_reasoning_case(case)
    expected_answer = _validated_expected_answer(case.expected)

    if not isinstance(output, dict) or set(output) != {"answer"}:
        return _zero_assessment(ReasoningIssue("invalid_output_shape", "/"))

    answer = output.get("answer")
    if type(answer) is not type(expected_answer):
        return _zero_assessment(ReasoningIssue("wrong_answer_type", "/answer"))
    if answer != expected_answer:
        return _zero_assessment(ReasoningIssue("wrong_answer", "/answer"))
    return ReasoningAssessment(score=Decimal("1"), issues=())


def score_reasoning(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Return the scalar v1 score consumed by BenchmarkRunner."""
    return assess_reasoning(case, output).score


def _validated_expected_answer(expected: JsonValue) -> str | int | bool:
    if not isinstance(expected, dict) or set(expected) != {"answer"}:
        raise ValueError("reasoning v1 expected output must contain exactly the answer field")
    answer = expected.get("answer")
    if isinstance(answer, bool):
        return answer
    if isinstance(answer, int):
        return answer
    if isinstance(answer, str):
        valid_characters = all(
            character.isascii() and (character.isalnum() or character in "_-")
            for character in answer
        )
        if (
            not answer
            or len(answer) > 64
            or answer.strip() != answer
            or answer.casefold() != answer
            or not valid_characters
        ):
            raise ValueError(
                "reasoning v1 string answers must be normalized lowercase ASCII tokens"
            )
        return answer
    raise ValueError("reasoning v1 answer must be a string, integer, or boolean")


def _zero_assessment(issue: ReasoningIssue) -> ReasoningAssessment:
    return ReasoningAssessment(score=Decimal("0"), issues=(issue,))
