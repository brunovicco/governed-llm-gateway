"""Deterministic tool-argument-generation benchmark contract and scorer."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

TOOL_ARGUMENT_GENERATION_BENCHMARK_VERSION = "tool-argument-generation-v1"
TOOL_ARGUMENT_GENERATION_CONTRACT_VERSION = "1.0"
TOOL_ARGUMENT_GENERATION_SCORER_ID = "tool_argument_generation_v1"
TOOL_ARGUMENT_GENERATION_RESPONSE_FORMAT = "tool_arguments_v1"
TOOL_ARGUMENT_GENERATION_CATALOG = (
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
    "selected_tool",
    "synthetic",
}
_CATALOG_VERSION = "support-tools-v1"
_PROMPT_PREFIX = (
    "The reviewed tool is already selected. Generate only the arguments for that tool; do not "
    "select another tool and do not execute anything. Return only JSON with the key arguments. "
    "Selected tool: "
)


@dataclass(frozen=True, slots=True, order=True)
class ToolArgumentIssue:
    """Stable reason code and JSON-pointer-like path for one argument issue."""

    code: str
    path: str


@dataclass(frozen=True, slots=True)
class ToolArgumentAssessment:
    """Explainable deterministic evidence for one generated argument object."""

    score: Decimal
    issues: tuple[ToolArgumentIssue, ...]

    @property
    def arguments_success(self) -> bool:
        """Return whether the reviewed argument object matched exactly."""
        return self.score == Decimal("1") and not self.issues


def load_tool_argument_generation_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate the complete reviewed tool-argument-generation-v1 dataset."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    if dataset.benchmark_version != TOOL_ARGUMENT_GENERATION_BENCHMARK_VERSION:
        raise ValueError(
            "tool argument generation v1 requires benchmark_version tool-argument-generation-v1"
        )

    case_ids = [case.case_id for case in dataset.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("tool argument generation v1 case IDs must be unique")

    tool_counts = dict.fromkeys(TOOL_ARGUMENT_GENERATION_CATALOG, 0)
    for case in dataset.cases:
        validate_tool_argument_generation_case(case)
        selected_tool = case.metadata.get("selected_tool")
        if not isinstance(selected_tool, str):
            raise AssertionError("validated selected_tool must be a string")
        tool_counts[selected_tool] += 1

    if any(count != 1 for count in tool_counts.values()):
        raise ValueError(
            "tool argument generation v1 requires exactly one case for every reviewed tool"
        )
    return dataset


def validate_tool_argument_generation_case(case: BenchmarkCase) -> None:
    """Fail closed when a case drifts from the reviewed v1 argument contract."""
    if case.workload is not BenchmarkWorkload.TOOL_ARGUMENT_GENERATION:
        raise ValueError("tool argument generation v1 dataset contains a different workload")
    if case.scorer != TOOL_ARGUMENT_GENERATION_SCORER_ID:
        raise ValueError("tool argument generation v1 requires its versioned deterministic scorer")

    metadata = case.metadata
    unknown_metadata = sorted(set(metadata) - _ALLOWED_METADATA_FIELDS)
    if unknown_metadata:
        fields = ", ".join(unknown_metadata)
        raise ValueError(f"tool argument generation v1 metadata contains unknown fields: {fields}")
    if metadata.get("contract_version") != TOOL_ARGUMENT_GENERATION_CONTRACT_VERSION:
        raise ValueError("tool argument generation v1 contract_version must be 1.0")
    if metadata.get("catalog_version") != _CATALOG_VERSION:
        raise ValueError("tool argument generation v1 catalog_version must be support-tools-v1")
    if metadata.get("response_format") != TOOL_ARGUMENT_GENERATION_RESPONSE_FORMAT:
        raise ValueError("tool argument generation v1 response_format must be tool_arguments_v1")
    if metadata.get("synthetic") is not True:
        raise ValueError("tool argument generation v1 cases must be explicitly synthetic")
    if metadata.get("execute_tool") is not False:
        raise ValueError("tool argument generation v1 tool execution must remain disabled")

    selected_tool = metadata.get("selected_tool")
    if not isinstance(selected_tool, str) or selected_tool not in TOOL_ARGUMENT_GENERATION_CATALOG:
        raise ValueError("tool argument generation v1 selected_tool must be reviewed")
    expected_prefix = f"{_PROMPT_PREFIX}{selected_tool}. Request: "
    if (
        not case.prompt.startswith(expected_prefix)
        or len(case.prompt) <= len(expected_prefix)
        or case.prompt.strip() != case.prompt
    ):
        raise ValueError("tool argument generation v1 prompt must bind the reviewed selected tool")

    _validated_expected_arguments(case.expected)


def assess_tool_argument_generation(
    case: BenchmarkCase,
    output: JsonValue,
) -> ToolArgumentAssessment:
    """Return deterministic recursive argument evidence without re-scoring tool selection."""
    validate_tool_argument_generation_case(case)
    expected = _validated_expected_arguments(case.expected)

    if not isinstance(output, dict) or set(output) != {"arguments"}:
        return _zero_assessment(ToolArgumentIssue("invalid_output_shape", "/"))
    observed = output.get("arguments")
    if not isinstance(observed, dict):
        return _zero_assessment(ToolArgumentIssue("wrong_arguments_type", "/arguments"))

    issues: list[ToolArgumentIssue] = []
    _compare_json(expected, observed, "/arguments", issues)
    if issues:
        return ToolArgumentAssessment(score=Decimal("0"), issues=tuple(issues))
    return ToolArgumentAssessment(score=Decimal("1"), issues=())


def score_tool_argument_generation(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Return the scalar v1 score consumed by BenchmarkRunner."""
    return assess_tool_argument_generation(case, output).score


def _validated_expected_arguments(expected: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(expected, dict) or set(expected) != {"arguments"}:
        raise ValueError(
            "tool argument generation v1 expected output must contain exactly arguments"
        )
    arguments = expected.get("arguments")
    if not isinstance(arguments, dict):
        raise ValueError("tool argument generation v1 expected arguments must be an object")
    return arguments


def _compare_json(
    expected: JsonValue,
    observed: JsonValue,
    path: str,
    issues: list[ToolArgumentIssue],
) -> None:
    if isinstance(expected, bool):
        if not isinstance(observed, bool):
            issues.append(ToolArgumentIssue("wrong_type", path))
        elif observed != expected:
            issues.append(ToolArgumentIssue("wrong_value", path))
        return

    if isinstance(expected, int) and not isinstance(expected, bool):
        if not isinstance(observed, int) or isinstance(observed, bool):
            issues.append(ToolArgumentIssue("wrong_type", path))
        elif observed != expected:
            issues.append(ToolArgumentIssue("wrong_value", path))
        return

    if isinstance(expected, str):
        if not isinstance(observed, str):
            issues.append(ToolArgumentIssue("wrong_type", path))
        elif observed != expected:
            issues.append(ToolArgumentIssue("wrong_value", path))
        return

    if expected is None:
        if observed is not None:
            issues.append(ToolArgumentIssue("wrong_value", path))
        return

    if isinstance(expected, list):
        if not isinstance(observed, list):
            issues.append(ToolArgumentIssue("wrong_type", path))
            return
        if len(observed) != len(expected):
            issues.append(ToolArgumentIssue("wrong_array_length", path))
            return
        for index, expected_item in enumerate(expected):
            _compare_json(expected_item, observed[index], f"{path}/{index}", issues)
        return

    if isinstance(expected, dict):
        if not isinstance(observed, dict):
            issues.append(ToolArgumentIssue("wrong_type", path))
            return
        for key in sorted(set(expected) - set(observed)):
            issues.append(ToolArgumentIssue("missing_argument", f"{path}/{key}"))
        for key in sorted(set(observed) - set(expected)):
            issues.append(ToolArgumentIssue("extra_argument", f"{path}/{key}"))
        for key in sorted(set(expected) & set(observed)):
            _compare_json(expected[key], observed[key], f"{path}/{key}", issues)
        return

    if isinstance(expected, float):
        if not isinstance(observed, float) or isinstance(observed, bool):
            issues.append(ToolArgumentIssue("wrong_type", path))
        elif observed != expected:
            issues.append(ToolArgumentIssue("wrong_value", path))
        return

    raise AssertionError("validated expected arguments contain unsupported JSON value")


def _zero_assessment(issue: ToolArgumentIssue) -> ToolArgumentAssessment:
    return ToolArgumentAssessment(score=Decimal("0"), issues=(issue,))
