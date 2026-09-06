"""Deterministic closed-catalog tool-selection benchmark contract and scorer."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

TOOL_SELECTION_BENCHMARK_VERSION = "tool-selection-v1"
TOOL_SELECTION_CONTRACT_VERSION = "1.0"
TOOL_SELECTION_SCORER_ID = "tool_selection_v1"
TOOL_SELECTION_RESPONSE_FORMAT = "tool_selection_v1"
TOOL_SELECTION_CATALOG = (
    "account_lookup",
    "knowledge_search",
    "send_notification",
    "weather_forecast",
)

_ALLOWED_METADATA_FIELDS = {
    "catalog_version",
    "contract_version",
    "execute_tool",
    "response_format",
    "synthetic",
}
_CATALOG_VERSION = "support-tools-v1"
_EXPECTED_NO_TOOL_CASES = 2
_PROMPT_PREFIX = (
    "Select exactly one tool from the reviewed catalog when a tool is required; otherwise select "
    "no tool. Do not generate arguments and do not execute any tool. Return only JSON with the key "
    "tool. Catalog: account_lookup=read synthetic account profile; "
    "knowledge_search=search synthetic product documentation; "
    "send_notification=send a synthetic user notification; "
    "weather_forecast=read a synthetic weather forecast. Request: "
)


@dataclass(frozen=True, slots=True, order=True)
class ToolSelectionIssue:
    """Stable reason code and JSON-pointer-like path for one selection issue."""

    code: str
    path: str


@dataclass(frozen=True, slots=True)
class ToolSelectionAssessment:
    """Explainable deterministic evidence for one tool-selection answer."""

    score: Decimal
    issues: tuple[ToolSelectionIssue, ...]

    @property
    def selection_success(self) -> bool:
        """Return whether the reviewed selection matched exactly."""
        return self.score == Decimal("1") and not self.issues


def load_tool_selection_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate the complete reviewed tool-selection-v1 dataset."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    if dataset.benchmark_version != TOOL_SELECTION_BENCHMARK_VERSION:
        raise ValueError("tool selection v1 requires benchmark_version tool-selection-v1")

    case_ids = [case.case_id for case in dataset.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("tool selection v1 case IDs must be unique")

    tool_counts = dict.fromkeys(TOOL_SELECTION_CATALOG, 0)
    no_tool_cases = 0
    for case in dataset.cases:
        validate_tool_selection_case(case)
        expected_tool = _validated_expected_tool(case.expected)
        if expected_tool is None:
            no_tool_cases += 1
        else:
            tool_counts[expected_tool] += 1

    if any(count != 1 for count in tool_counts.values()):
        raise ValueError("tool selection v1 requires exactly one case for every reviewed tool")
    if no_tool_cases != _EXPECTED_NO_TOOL_CASES:
        raise ValueError("tool selection v1 requires exactly two reviewed no-tool cases")
    return dataset


def validate_tool_selection_case(case: BenchmarkCase) -> None:
    """Fail closed when a case drifts from the reviewed v1 selection contract."""
    if case.workload is not BenchmarkWorkload.TOOL_SELECTION:
        raise ValueError("tool selection v1 dataset contains a different workload")
    if case.scorer != TOOL_SELECTION_SCORER_ID:
        raise ValueError("tool selection v1 requires its versioned deterministic scorer")
    if (
        not case.prompt.startswith(_PROMPT_PREFIX)
        or len(case.prompt) <= len(_PROMPT_PREFIX)
        or case.prompt.strip() != case.prompt
    ):
        raise ValueError("tool selection v1 prompt must use the reviewed catalog instruction")

    metadata = case.metadata
    unknown_metadata = sorted(set(metadata) - _ALLOWED_METADATA_FIELDS)
    if unknown_metadata:
        fields = ", ".join(unknown_metadata)
        raise ValueError(f"tool selection v1 metadata contains unknown fields: {fields}")
    if metadata.get("contract_version") != TOOL_SELECTION_CONTRACT_VERSION:
        raise ValueError("tool selection v1 contract_version must be 1.0")
    if metadata.get("catalog_version") != _CATALOG_VERSION:
        raise ValueError("tool selection v1 catalog_version must be support-tools-v1")
    if metadata.get("response_format") != TOOL_SELECTION_RESPONSE_FORMAT:
        raise ValueError("tool selection v1 response_format must be tool_selection_v1")
    if metadata.get("synthetic") is not True:
        raise ValueError("tool selection v1 cases must be explicitly synthetic")
    if metadata.get("execute_tool") is not False:
        raise ValueError("tool selection v1 tool execution must remain disabled")

    _validated_expected_tool(case.expected)


def assess_tool_selection(case: BenchmarkCase, output: JsonValue) -> ToolSelectionAssessment:
    """Return deterministic exact-selection evidence without evaluating arguments."""
    validate_tool_selection_case(case)
    expected_tool = _validated_expected_tool(case.expected)

    if not isinstance(output, dict) or set(output) != {"tool"}:
        return _zero_assessment(ToolSelectionIssue("invalid_output_shape", "/"))

    observed_tool = output.get("tool")
    if observed_tool is not None and not isinstance(observed_tool, str):
        return _zero_assessment(ToolSelectionIssue("wrong_tool_type", "/tool"))
    if isinstance(observed_tool, str) and observed_tool not in TOOL_SELECTION_CATALOG:
        return _zero_assessment(ToolSelectionIssue("unknown_tool", "/tool"))
    if observed_tool != expected_tool:
        code = "unexpected_tool" if expected_tool is None else "wrong_tool"
        if observed_tool is None:
            code = "missing_tool"
        return _zero_assessment(ToolSelectionIssue(code, "/tool"))

    return ToolSelectionAssessment(score=Decimal("1"), issues=())


def score_tool_selection(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Return the scalar v1 score consumed by BenchmarkRunner."""
    return assess_tool_selection(case, output).score


def _validated_expected_tool(expected: JsonValue) -> str | None:
    if not isinstance(expected, dict) or set(expected) != {"tool"}:
        raise ValueError("tool selection v1 expected output must contain exactly tool")
    tool = expected.get("tool")
    if tool is not None and (not isinstance(tool, str) or tool not in TOOL_SELECTION_CATALOG):
        raise ValueError("tool selection v1 expected tool must be reviewed or null")
    return tool


def _zero_assessment(issue: ToolSelectionIssue) -> ToolSelectionAssessment:
    return ToolSelectionAssessment(score=Decimal("0"), issues=(issue,))
