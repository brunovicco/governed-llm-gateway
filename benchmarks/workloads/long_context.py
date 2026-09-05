"""Deterministic long-context benchmark contract, materializer, and scorer."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

LONG_CONTEXT_BENCHMARK_VERSION = "long-context-v1"
LONG_CONTEXT_CONTRACT_VERSION = "1.0"
LONG_CONTEXT_SCORER_ID = "long_context_v1"
LONG_CONTEXT_GENERATOR_VERSION = "numbered-records-v1"
LONG_CONTEXT_RECORD_COUNT = 8192

_LONG_CONTEXT_INSTRUCTION = (
    "Read the complete synthetic record set. Exactly one numbered record contains a needle "
    'value. Return only a JSON object with the single key "needle" and the exact value from '
    "that record."
)
_RESPONSE_FORMAT = "needle_value_v1"
_POSITION_RECORDS = {
    "early": 128,
    "middle": 4096,
    "late": 8064,
}
_ALLOWED_METADATA_FIELDS = {
    "contract_version",
    "generator_version",
    "needle_position",
    "needle_record",
    "record_count",
    "response_format",
    "synthetic",
}
_ALLOWED_NEEDLE_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")


@dataclass(frozen=True, slots=True, order=True)
class LongContextIssue:
    """Stable reason code and JSON-pointer-like path for one retrieval issue."""

    code: str
    path: str


@dataclass(frozen=True, slots=True)
class LongContextAssessment:
    """Explainable deterministic evidence for one long-context retrieval answer."""

    score: Decimal
    issues: tuple[LongContextIssue, ...]

    @property
    def retrieval_success(self) -> bool:
        """Return whether the reviewed needle was recovered exactly."""
        return self.score == Decimal("1") and not self.issues


def load_long_context_dataset(path: Path) -> BenchmarkDataset:
    """Load long-context v1 and materialize the deterministic synthetic record streams."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    if dataset.benchmark_version != LONG_CONTEXT_BENCHMARK_VERSION:
        raise ValueError("long context v1 requires benchmark_version long-context-v1")

    case_ids = [case.case_id for case in dataset.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("long context v1 case IDs must be unique")

    positions: list[str] = []
    materialized: list[BenchmarkCase] = []
    for case in dataset.cases:
        validate_long_context_case(case)
        position = case.metadata.get("needle_position")
        if not isinstance(position, str):
            raise AssertionError("validated long context needle_position must be a string")
        positions.append(position)
        materialized.append(materialize_long_context_case(case))

    if len(positions) != len(_POSITION_RECORDS) or set(positions) != set(_POSITION_RECORDS):
        raise ValueError("long context v1 requires exactly one early, middle, and late case")

    return BenchmarkDataset(
        schema_version=dataset.schema_version,
        benchmark_version=dataset.benchmark_version,
        data_classification=dataset.data_classification,
        cases=tuple(materialized),
    )


def validate_long_context_case(case: BenchmarkCase) -> None:
    """Fail closed when a case drifts from the reviewed v1 long-context contract."""
    if case.workload is not BenchmarkWorkload.LONG_CONTEXT:
        raise ValueError("long context v1 dataset contains a different workload")
    if case.scorer != LONG_CONTEXT_SCORER_ID:
        raise ValueError("long context v1 requires its versioned deterministic scorer")

    metadata = case.metadata
    unknown_metadata = sorted(set(metadata) - _ALLOWED_METADATA_FIELDS)
    if unknown_metadata:
        fields = ", ".join(unknown_metadata)
        raise ValueError(f"long context v1 metadata contains unknown fields: {fields}")
    if metadata.get("contract_version") != LONG_CONTEXT_CONTRACT_VERSION:
        raise ValueError("long context v1 contract_version must be 1.0")
    if metadata.get("generator_version") != LONG_CONTEXT_GENERATOR_VERSION:
        raise ValueError("long context v1 generator_version must be numbered-records-v1")
    if metadata.get("synthetic") is not True:
        raise ValueError("long context v1 cases must be explicitly synthetic")
    if metadata.get("response_format") != _RESPONSE_FORMAT:
        raise ValueError("long context v1 response_format must be needle_value_v1")

    record_count = metadata.get("record_count")
    if isinstance(record_count, bool) or not isinstance(record_count, int):
        raise ValueError("long context v1 record_count must be an integer")
    if record_count != LONG_CONTEXT_RECORD_COUNT:
        raise ValueError(f"long context v1 record_count must be {LONG_CONTEXT_RECORD_COUNT}")

    position = metadata.get("needle_position")
    if not isinstance(position, str) or position not in _POSITION_RECORDS:
        raise ValueError("long context v1 needle_position must be early, middle, or late")

    needle_record = metadata.get("needle_record")
    if isinstance(needle_record, bool) or not isinstance(needle_record, int):
        raise ValueError("long context v1 needle_record must be an integer")
    if needle_record != _POSITION_RECORDS[position]:
        raise ValueError("long context v1 needle_record does not match its reviewed position")

    _validated_expected(case.expected)


def materialize_long_context_case(case: BenchmarkCase) -> BenchmarkCase:
    """Expand one compact v1 case into the actual deterministic long prompt."""
    validate_long_context_case(case)
    if case.prompt != _LONG_CONTEXT_INSTRUCTION:
        raise ValueError("long context v1 prompt instruction drifted from the reviewed contract")

    expected = _validated_expected(case.expected)
    needle_record = case.metadata.get("needle_record")
    if not isinstance(needle_record, int) or isinstance(needle_record, bool):
        raise AssertionError("validated long context needle_record must be an integer")

    records = [
        _record_line(index=index, needle_record=needle_record, needle=expected)
        for index in range(1, LONG_CONTEXT_RECORD_COUNT + 1)
    ]
    prompt = (
        f"{case.prompt}\n\nBEGIN SYNTHETIC RECORDS\n"
        + "".join(records)
        + "END SYNTHETIC RECORDS\n\nReturn the requested JSON object now."
    )
    return BenchmarkCase(
        case_id=case.case_id,
        workload=case.workload,
        scorer=case.scorer,
        prompt=prompt,
        expected=case.expected,
        metadata=dict(case.metadata),
    )


def assess_long_context(case: BenchmarkCase, output: JsonValue) -> LongContextAssessment:
    """Return deterministic exact needle-retrieval evidence."""
    validate_long_context_case(case)
    expected = _validated_expected(case.expected)

    if not isinstance(output, dict) or set(output) != {"needle"}:
        return _zero_assessment(LongContextIssue("invalid_output_shape", "/"))

    value = output.get("needle")
    if not isinstance(value, str):
        return _zero_assessment(LongContextIssue("wrong_value_type", "/needle"))
    if value != expected:
        return _zero_assessment(LongContextIssue("wrong_needle", "/needle"))
    return LongContextAssessment(score=Decimal("1"), issues=())


def score_long_context(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Return the scalar v1 score consumed by BenchmarkRunner."""
    return assess_long_context(case, output).score


def _validated_expected(expected: JsonValue) -> str:
    if not isinstance(expected, dict) or set(expected) != {"needle"}:
        raise ValueError("long context v1 expected output must contain exactly the needle field")
    needle = expected.get("needle")
    if not isinstance(needle, str):
        raise ValueError("long context v1 expected needle must be a normalized string")
    if not needle or needle.strip() != needle or needle.casefold() != needle:
        raise ValueError("long context v1 expected needle must be a normalized lowercase string")
    if len(needle) > 64 or any(character not in _ALLOWED_NEEDLE_CHARACTERS for character in needle):
        raise ValueError("long context v1 expected needle contains unsupported characters")
    return needle


def _record_line(*, index: int, needle_record: int, needle: str) -> str:
    if index == needle_record:
        return f"record-{index:05d}: needle={needle}\n"
    checksum = (index * 7919) % 100_000
    return f"record-{index:05d}: filler=segment-{index:05d}-{checksum:05d}\n"


def _zero_assessment(issue: LongContextIssue) -> LongContextAssessment:
    return LongContextAssessment(score=Decimal("0"), issues=(issue,))
