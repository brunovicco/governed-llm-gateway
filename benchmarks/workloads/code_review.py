"""Deterministic structured-findings code-review benchmark contract and scorer."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

CODE_REVIEW_BENCHMARK_VERSION = "code-review-v1"
CODE_REVIEW_CONTRACT_VERSION = "1.0"
CODE_REVIEW_SCORER_ID = "code_review_findings_v1"
CODE_REVIEW_RESPONSE_FORMAT = "code_review_findings_v1"
CODE_REVIEW_RULE_SEVERITIES = MappingProxyType(
    {
        "broad_exception_catch": "medium",
        "duplicate_branch_logic": "low",
        "missing_return_path": "high",
        "mutable_default_argument": "medium",
        "off_by_one_range": "medium",
        "repeated_membership_scan": "low",
    }
)

_ALLOWED_METADATA_FIELDS = {
    "contract_version",
    "execute_candidate",
    "language",
    "response_format",
    "synthetic",
}
_PROMPT_PREFIX = (
    "Review this synthetic Python snippet using only the reviewed non-security code-review rules. "
    "Do not execute the code. Return only JSON with the key findings. Code:\n```python\n"
)
_PROMPT_SUFFIX = "\n```"
_EXPECTED_CLEAN_CASES = 2
_MAX_OBSERVED_FINDINGS = 8


@dataclass(frozen=True, slots=True, order=True)
class CodeReviewFinding:
    """One normalized reviewed code-review finding."""

    rule_id: str
    severity: str
    line: int


@dataclass(frozen=True, slots=True, order=True)
class CodeReviewIssue:
    """Stable reason code and JSON-pointer-like path for one scoring issue."""

    code: str
    path: str


@dataclass(frozen=True, slots=True)
class CodeReviewAssessment:
    """Explainable deterministic evidence for one structured code review."""

    score: Decimal
    matched_findings: int
    expected_findings: int
    observed_findings: int
    issues: tuple[CodeReviewIssue, ...]

    @property
    def review_success(self) -> bool:
        """Return whether the observed finding set matched exactly."""
        return self.score == Decimal("1") and not self.issues


def load_code_review_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate the complete reviewed code-review-v1 dataset."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    if dataset.benchmark_version != CODE_REVIEW_BENCHMARK_VERSION:
        raise ValueError("code review v1 requires benchmark_version code-review-v1")

    case_ids = [case.case_id for case in dataset.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("code review v1 case IDs must be unique")

    rule_counts = dict.fromkeys(CODE_REVIEW_RULE_SEVERITIES, 0)
    clean_cases = 0
    for case in dataset.cases:
        validate_code_review_case(case)
        expected = _validated_expected_findings(case.expected)
        if not expected:
            clean_cases += 1
            continue
        for finding in expected:
            rule_counts[finding.rule_id] += 1

    if any(count != 1 for count in rule_counts.values()):
        raise ValueError("code review v1 requires exactly one case for every reviewed rule")
    if clean_cases != _EXPECTED_CLEAN_CASES:
        raise ValueError("code review v1 requires exactly two reviewed clean cases")
    return dataset


def validate_code_review_case(case: BenchmarkCase) -> None:
    """Fail closed when a case drifts from the reviewed non-executing v1 contract."""
    if case.workload is not BenchmarkWorkload.CODE_REVIEW:
        raise ValueError("code review v1 dataset contains a different workload")
    if case.scorer != CODE_REVIEW_SCORER_ID:
        raise ValueError("code review v1 requires its versioned deterministic scorer")
    if (
        not case.prompt.startswith(_PROMPT_PREFIX)
        or not case.prompt.endswith(_PROMPT_SUFFIX)
        or case.prompt.strip() != case.prompt
        or len(case.prompt) <= len(_PROMPT_PREFIX) + len(_PROMPT_SUFFIX)
    ):
        raise ValueError("code review v1 prompt must use the reviewed non-executing instruction")

    metadata = case.metadata
    unknown_metadata = sorted(set(metadata) - _ALLOWED_METADATA_FIELDS)
    if unknown_metadata:
        fields = ", ".join(unknown_metadata)
        raise ValueError(f"code review v1 metadata contains unknown fields: {fields}")
    if metadata.get("contract_version") != CODE_REVIEW_CONTRACT_VERSION:
        raise ValueError("code review v1 contract_version must be 1.0")
    if metadata.get("language") != "python":
        raise ValueError("code review v1 language must be python")
    if metadata.get("response_format") != CODE_REVIEW_RESPONSE_FORMAT:
        raise ValueError("code review v1 response_format must be code_review_findings_v1")
    if metadata.get("synthetic") is not True:
        raise ValueError("code review v1 cases must be explicitly synthetic")
    if metadata.get("execute_candidate") is not False:
        raise ValueError("code review v1 candidate execution must remain disabled")

    _validated_expected_findings(case.expected)


def assess_code_review(case: BenchmarkCase, output: JsonValue) -> CodeReviewAssessment:
    """Score an order-independent structured finding set without executing code."""
    validate_code_review_case(case)
    expected = _validated_expected_findings(case.expected)

    if not isinstance(output, dict) or set(output) != {"findings"}:
        return _zero_assessment(
            expected_count=len(expected),
            issue=CodeReviewIssue("invalid_output_shape", "/"),
        )

    raw_findings = output.get("findings")
    if not isinstance(raw_findings, list) or len(raw_findings) > _MAX_OBSERVED_FINDINGS:
        return _zero_assessment(
            expected_count=len(expected),
            issue=CodeReviewIssue("invalid_findings", "/findings"),
        )

    observed: list[CodeReviewFinding] = []
    for index, raw_finding in enumerate(raw_findings):
        finding = _parse_observed_finding(raw_finding)
        if finding is None:
            return _zero_assessment(
                expected_count=len(expected),
                issue=CodeReviewIssue("invalid_finding", f"/findings/{index}"),
            )
        if finding in observed:
            return _zero_assessment(
                expected_count=len(expected),
                issue=CodeReviewIssue("duplicate_finding", f"/findings/{index}"),
            )
        observed.append(finding)

    expected_set = set(expected)
    observed_set = set(observed)
    matched = len(expected_set & observed_set)
    denominator = len(expected_set) + len(observed_set)
    score = Decimal("1") if denominator == 0 else Decimal(2 * matched) / Decimal(denominator)

    issues: list[CodeReviewIssue] = []
    if expected_set - observed_set:
        issues.append(CodeReviewIssue("missing_finding", "/findings"))
    if observed_set - expected_set:
        issues.append(CodeReviewIssue("unexpected_finding", "/findings"))

    return CodeReviewAssessment(
        score=score,
        matched_findings=matched,
        expected_findings=len(expected_set),
        observed_findings=len(observed_set),
        issues=tuple(issues),
    )


def score_code_review(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Return the scalar v1 score consumed by BenchmarkRunner."""
    return assess_code_review(case, output).score


def _validated_expected_findings(expected: JsonValue) -> tuple[CodeReviewFinding, ...]:
    if not isinstance(expected, dict) or set(expected) != {"findings"}:
        raise ValueError("code review v1 expected output must contain exactly findings")
    findings = expected.get("findings")
    if not isinstance(findings, list) or len(findings) > 1:
        raise ValueError("code review v1 expected findings must contain zero or one finding")

    validated: list[CodeReviewFinding] = []
    for finding in findings:
        parsed = _parse_observed_finding(finding)
        if parsed is None:
            raise ValueError("code review v1 expected finding is invalid")
        validated.append(parsed)
    return tuple(validated)


def _parse_observed_finding(value: JsonValue) -> CodeReviewFinding | None:
    if not isinstance(value, dict) or set(value) != {"line", "rule_id", "severity"}:
        return None
    rule_id = value.get("rule_id")
    severity = value.get("severity")
    line = value.get("line")
    if not isinstance(rule_id, str) or rule_id not in CODE_REVIEW_RULE_SEVERITIES:
        return None
    if not isinstance(severity, str) or severity != CODE_REVIEW_RULE_SEVERITIES[rule_id]:
        return None
    if not isinstance(line, int) or isinstance(line, bool) or line <= 0:
        return None
    return CodeReviewFinding(rule_id=rule_id, severity=severity, line=line)


def _zero_assessment(
    *,
    expected_count: int,
    issue: CodeReviewIssue,
) -> CodeReviewAssessment:
    return CodeReviewAssessment(
        score=Decimal("0"),
        matched_findings=0,
        expected_findings=expected_count,
        observed_findings=0,
        issues=(issue,),
    )
