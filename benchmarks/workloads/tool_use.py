"""Deterministic single-call tool-use benchmark contract and scorer."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

TOOL_USE_BENCHMARK_VERSION = "tool-use-v1"
TOOL_USE_CONTRACT_VERSION = "1.0"
TOOL_USE_SCORER_ID = "tool_use_v1"

_ALLOWED_METADATA_FIELDS = {"allowed_tools", "contract_version", "execute_tool", "synthetic"}


@dataclass(frozen=True, slots=True, order=True)
class ToolUseIssue:
    """Stable reason code and JSON-pointer-like path for one tool-use scoring issue."""

    code: str
    path: str


@dataclass(frozen=True, slots=True)
class ToolUseAssessment:
    """Explainable tool-selection and argument evidence for one normalized output."""

    score: Decimal
    selection_score: Decimal
    arguments_score: Decimal
    issues: tuple[ToolUseIssue, ...]


def load_tool_use_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate a dataset containing only tool-use v1 cases."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    if dataset.benchmark_version != TOOL_USE_BENCHMARK_VERSION:
        raise ValueError("tool use v1 requires benchmark_version tool-use-v1")
    case_ids = [case.case_id for case in dataset.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("tool use v1 case IDs must be unique")
    for case in dataset.cases:
        validate_tool_use_case(case)
    return dataset


def validate_tool_use_case(case: BenchmarkCase) -> None:
    """Fail closed when a tool-use case drifts from the v1 benchmark contract."""
    if case.workload is not BenchmarkWorkload.TOOL_USE:
        raise ValueError("tool use v1 dataset contains a different workload")
    if case.scorer != TOOL_USE_SCORER_ID:
        raise ValueError("tool use v1 requires its versioned deterministic scorer")

    metadata = case.metadata
    unknown_metadata = sorted(set(metadata) - _ALLOWED_METADATA_FIELDS)
    if unknown_metadata:
        fields = ", ".join(unknown_metadata)
        raise ValueError(f"tool use v1 metadata contains unknown fields: {fields}")
    if metadata.get("contract_version") != TOOL_USE_CONTRACT_VERSION:
        raise ValueError("tool use v1 contract_version must be 1.0")
    if metadata.get("synthetic") is not True:
        raise ValueError("tool use v1 cases must be explicitly synthetic")
    if metadata.get("execute_tool") is not False:
        raise ValueError("tool use v1 execution must remain disabled")

    allowed_tools = metadata.get("allowed_tools")
    if not isinstance(allowed_tools, list) or not allowed_tools:
        raise ValueError("tool use v1 allowed_tools must be a non-empty string list")
    if not all(isinstance(item, str) and item and item.strip() == item for item in allowed_tools):
        raise ValueError("tool use v1 allowed_tools must contain normalized strings")
    normalized_allowed = [item for item in allowed_tools if isinstance(item, str)]
    if len(normalized_allowed) != len(set(normalized_allowed)):
        raise ValueError("tool use v1 allowed_tools must not contain duplicates")

    expected = case.expected
    if expected is None:
        return
    _validate_call_shape(expected, label="expected output")
    if not isinstance(expected, dict):
        raise AssertionError("validated tool use expected output is not an object")
    expected_name = expected.get("name")
    if not isinstance(expected_name, str):
        raise AssertionError("validated tool use expected name is not a string")
    if expected_name not in normalized_allowed:
        raise ValueError("tool use v1 expected tool must be present in allowed_tools")


def assess_tool_use(case: BenchmarkCase, output: JsonValue) -> ToolUseAssessment:
    """Return deterministic tool-selection, argument, and reason-code evidence."""
    validate_tool_use_case(case)
    expected = case.expected
    allowed_tools = case.metadata["allowed_tools"]
    if not isinstance(allowed_tools, list):
        raise AssertionError("validated tool use allowed_tools must be a list")

    if expected is None:
        if output is None:
            return ToolUseAssessment(
                score=Decimal("1"),
                selection_score=Decimal("1"),
                arguments_score=Decimal("1"),
                issues=(),
            )
        issues = [ToolUseIssue("unexpected_tool_call", "/")]
        if isinstance(output, dict):
            output_name = output.get("name")
            if isinstance(output_name, str) and output_name not in allowed_tools:
                issues.append(ToolUseIssue("undeclared_tool", "/name"))
        else:
            issues.append(ToolUseIssue("invalid_output_shape", "/"))
        return ToolUseAssessment(
            score=Decimal("0"),
            selection_score=Decimal("0"),
            arguments_score=Decimal("0"),
            issues=tuple(sorted(set(issues))),
        )

    if not isinstance(expected, dict):
        raise AssertionError("validated tool use expected output must be an object")

    if output is None:
        return ToolUseAssessment(
            score=Decimal("0"),
            selection_score=Decimal("0"),
            arguments_score=Decimal("0"),
            issues=(ToolUseIssue("missing_tool_call", "/"),),
        )
    if not isinstance(output, dict) or set(output) != {"name", "arguments"}:
        return ToolUseAssessment(
            score=Decimal("0"),
            selection_score=Decimal("0"),
            arguments_score=Decimal("0"),
            issues=(ToolUseIssue("invalid_output_shape", "/"),),
        )

    output_name = output.get("name")
    output_arguments = output.get("arguments")
    if not isinstance(output_name, str):
        return ToolUseAssessment(
            score=Decimal("0"),
            selection_score=Decimal("0"),
            arguments_score=Decimal("0"),
            issues=(ToolUseIssue("wrong_tool_type", "/name"),),
        )
    if not isinstance(output_arguments, dict):
        return ToolUseAssessment(
            score=Decimal("0"),
            selection_score=Decimal("0"),
            arguments_score=Decimal("0"),
            issues=(ToolUseIssue("wrong_arguments_type", "/arguments"),),
        )

    expected_name = expected.get("name")
    expected_arguments = expected.get("arguments")
    if not isinstance(expected_name, str) or not isinstance(expected_arguments, dict):
        raise AssertionError("validated tool use expected output is inconsistent")

    issues: list[ToolUseIssue] = []
    if output_name not in allowed_tools:
        issues.append(ToolUseIssue("undeclared_tool", "/name"))
        return ToolUseAssessment(
            score=Decimal("0"),
            selection_score=Decimal("0"),
            arguments_score=Decimal("0"),
            issues=tuple(issues),
        )

    selection_score = Decimal("1") if output_name == expected_name else Decimal("0")
    if selection_score == Decimal("0"):
        issues.append(ToolUseIssue("wrong_tool", "/name"))

    argument_issues = _compare_values(expected_arguments, output_arguments, path="/arguments")
    arguments_score = Decimal("1") if not argument_issues else Decimal("0")
    issues.extend(argument_issues)
    score = (selection_score + arguments_score) / Decimal("2")
    return ToolUseAssessment(
        score=score,
        selection_score=selection_score,
        arguments_score=arguments_score,
        issues=tuple(sorted(set(issues))),
    )


def score_tool_use(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Return the scalar tool-use v1 score consumed by BenchmarkRunner."""
    return assess_tool_use(case, output).score


def _validate_call_shape(value: JsonValue, *, label: str) -> None:
    if not isinstance(value, dict) or set(value) != {"name", "arguments"}:
        raise ValueError(f"tool use v1 {label} must contain exactly name and arguments")
    name = value.get("name")
    arguments = value.get("arguments")
    if not isinstance(name, str) or not name or name.strip() != name:
        raise ValueError(f"tool use v1 {label} name must be a normalized string")
    if not isinstance(arguments, dict):
        raise ValueError(f"tool use v1 {label} arguments must be an object")


def _compare_values(
    expected: JsonValue,
    output: JsonValue,
    *,
    path: str,
) -> tuple[ToolUseIssue, ...]:
    if type(expected) is not type(output):
        return (ToolUseIssue("wrong_argument_type", path),)

    issues: list[ToolUseIssue] = []
    if isinstance(expected, dict) and isinstance(output, dict):
        for key in sorted(set(expected) - set(output)):
            issues.append(ToolUseIssue("missing_argument", _child_path(path, key)))
        for key in sorted(set(output) - set(expected)):
            issues.append(ToolUseIssue("unexpected_argument", _child_path(path, key)))
        for key in sorted(set(expected) & set(output)):
            issues.extend(
                _compare_values(expected[key], output[key], path=_child_path(path, key))
            )
        return tuple(issues)

    if isinstance(expected, list) and isinstance(output, list):
        if len(expected) != len(output):
            issues.append(ToolUseIssue("argument_array_length_mismatch", path))
        for index, (expected_item, output_item) in enumerate(zip(expected, output, strict=False)):
            issues.extend(
                _compare_values(expected_item, output_item, path=_child_path(path, str(index)))
            )
        return tuple(issues)

    if expected != output:
        issues.append(ToolUseIssue("wrong_argument_value", path))
    return tuple(issues)


def _child_path(path: str, key: str) -> str:
    escaped = key.replace("~", "~0").replace("/", "~1")
    if path == "/":
        return f"/{escaped}"
    return f"{path}/{escaped}"
