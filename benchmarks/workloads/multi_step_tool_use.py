"""Deterministic non-executing multi-step tool-use benchmark contract and scorer."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

MULTI_STEP_TOOL_USE_BENCHMARK_VERSION = "multi-step-tool-use-v1"
MULTI_STEP_TOOL_USE_CONTRACT_VERSION = "1.0"
MULTI_STEP_TOOL_USE_SCORER_ID = "multi_step_tool_use_v1"
MULTI_STEP_TOOL_USE_RESPONSE_FORMAT = "multi_step_tool_calls_v1"
MULTI_STEP_TOOL_USE_CATALOG = (
    "account_lookup",
    "knowledge_search",
    "send_notification",
    "weather_forecast",
)

_ALLOWED_METADATA_FIELDS = {
    "catalog_version",
    "contract_version",
    "execute_tools",
    "response_format",
    "synthetic",
}
_CATALOG_VERSION = "support-tools-v1"
_EXPECTED_CASE_COUNT = 4
_MIN_EXPECTED_STEPS = 2
_MAX_EXPECTED_STEPS = 3
_PROMPT_PREFIX = (
    "Plan the complete reviewed synthetic tool trajectory. Intermediate tool results are already "
    "supplied as immutable synthetic context; do not execute any tool. Return only JSON with the "
    "key steps, where every step contains exactly tool and arguments. Catalog: "
    "account_lookup, knowledge_search, send_notification, weather_forecast. Scenario: "
)
_STEP_FIELDS = {"arguments", "tool"}

type _NormalizedStep = tuple[str, dict[str, JsonValue]]


@dataclass(frozen=True, slots=True, order=True)
class MultiStepToolUseIssue:
    """Stable reason code and JSON-pointer-like path for one trajectory issue."""

    code: str
    path: str


@dataclass(frozen=True, slots=True)
class MultiStepToolUseAssessment:
    """Explainable deterministic evidence for one proposed multi-tool trajectory."""

    score: Decimal
    selection_score: Decimal
    arguments_score: Decimal
    issues: tuple[MultiStepToolUseIssue, ...]

    @property
    def trajectory_success(self) -> bool:
        """Return whether the complete reviewed trajectory matched exactly."""
        return self.score == Decimal("1") and not self.issues


def load_multi_step_tool_use_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate the complete reviewed multi-step-tool-use-v1 dataset."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    if dataset.benchmark_version != MULTI_STEP_TOOL_USE_BENCHMARK_VERSION:
        raise ValueError("multi-step tool use v1 requires benchmark_version multi-step-tool-use-v1")

    case_ids = [case.case_id for case in dataset.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("multi-step tool use v1 case IDs must be unique")
    if len(dataset.cases) != _EXPECTED_CASE_COUNT:
        raise ValueError("multi-step tool use v1 requires exactly four reviewed cases")

    observed_tools: set[str] = set()
    observed_lengths: set[int] = set()
    for case in dataset.cases:
        validate_multi_step_tool_use_case(case)
        steps = _validated_expected_steps(case.expected)
        observed_lengths.add(len(steps))
        observed_tools.update(tool for tool, _ in steps)

    if observed_tools != set(MULTI_STEP_TOOL_USE_CATALOG):
        raise ValueError("multi-step tool use v1 must cover every reviewed tool")
    if observed_lengths != {_MIN_EXPECTED_STEPS, _MAX_EXPECTED_STEPS}:
        raise ValueError(
            "multi-step tool use v1 must include reviewed two-step and three-step cases"
        )
    return dataset


def validate_multi_step_tool_use_case(case: BenchmarkCase) -> None:
    """Fail closed when a case drifts from the reviewed v1 trajectory contract."""
    if case.workload is not BenchmarkWorkload.MULTI_STEP_TOOL_USE:
        raise ValueError("multi-step tool use v1 dataset contains a different workload")
    if case.scorer != MULTI_STEP_TOOL_USE_SCORER_ID:
        raise ValueError("multi-step tool use v1 requires its versioned deterministic scorer")
    if (
        not case.prompt.startswith(_PROMPT_PREFIX)
        or len(case.prompt) <= len(_PROMPT_PREFIX)
        or case.prompt.strip() != case.prompt
    ):
        raise ValueError(
            "multi-step tool use v1 prompt must use the reviewed non-executing instruction"
        )

    metadata = case.metadata
    unknown_metadata = sorted(set(metadata) - _ALLOWED_METADATA_FIELDS)
    if unknown_metadata:
        fields = ", ".join(unknown_metadata)
        raise ValueError(f"multi-step tool use v1 metadata contains unknown fields: {fields}")
    if metadata.get("contract_version") != MULTI_STEP_TOOL_USE_CONTRACT_VERSION:
        raise ValueError("multi-step tool use v1 contract_version must be 1.0")
    if metadata.get("catalog_version") != _CATALOG_VERSION:
        raise ValueError("multi-step tool use v1 catalog_version must be support-tools-v1")
    if metadata.get("response_format") != MULTI_STEP_TOOL_USE_RESPONSE_FORMAT:
        raise ValueError("multi-step tool use v1 response_format must be multi_step_tool_calls_v1")
    if metadata.get("synthetic") is not True:
        raise ValueError("multi-step tool use v1 cases must be explicitly synthetic")
    if metadata.get("execute_tools") is not False:
        raise ValueError("multi-step tool use v1 tool execution must remain disabled")

    _validated_expected_steps(case.expected)


def assess_multi_step_tool_use(
    case: BenchmarkCase,
    output: JsonValue,
) -> MultiStepToolUseAssessment:
    """Return deterministic ordered selection and argument evidence without executing tools."""
    validate_multi_step_tool_use_case(case)
    expected_steps = _validated_expected_steps(case.expected)
    output_steps, contract_issues = _normalized_output_steps(output)
    if output_steps is None:
        return _zero_assessment(contract_issues)

    denominator = max(len(expected_steps), len(output_steps), 1)
    common = min(len(expected_steps), len(output_steps))
    selection_matches = 0
    argument_matches = 0
    issues: list[MultiStepToolUseIssue] = []

    if len(expected_steps) != len(output_steps):
        issues.append(MultiStepToolUseIssue("step_count_mismatch", "/steps"))

    for index in range(common):
        expected_tool, expected_arguments = expected_steps[index]
        output_tool, output_arguments = output_steps[index]
        step_path = f"/steps/{index}"

        if output_tool != expected_tool:
            issues.append(MultiStepToolUseIssue("wrong_tool", f"{step_path}/tool"))
            continue

        selection_matches += 1
        argument_issues = _compare_values(
            expected_arguments,
            output_arguments,
            path=f"{step_path}/arguments",
        )
        if argument_issues:
            issues.extend(argument_issues)
        else:
            argument_matches += 1

    for index in range(common, len(expected_steps)):
        issues.append(MultiStepToolUseIssue("missing_step", f"/steps/{index}"))
    for index in range(common, len(output_steps)):
        issues.append(MultiStepToolUseIssue("unexpected_step", f"/steps/{index}"))

    selection_score = Decimal(selection_matches) / Decimal(denominator)
    arguments_score = Decimal(argument_matches) / Decimal(denominator)
    score = (selection_score + arguments_score) / Decimal("2")
    return MultiStepToolUseAssessment(
        score=score,
        selection_score=selection_score,
        arguments_score=arguments_score,
        issues=tuple(sorted(set(issues))),
    )


def score_multi_step_tool_use(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Return the scalar v1 score consumed by BenchmarkRunner."""
    return assess_multi_step_tool_use(case, output).score


def _validated_expected_steps(expected: JsonValue) -> tuple[_NormalizedStep, ...]:
    if not isinstance(expected, dict) or set(expected) != {"steps"}:
        raise ValueError("multi-step tool use v1 expected output must contain exactly steps")
    raw_steps = expected.get("steps")
    if not isinstance(raw_steps, list) or not (
        _MIN_EXPECTED_STEPS <= len(raw_steps) <= _MAX_EXPECTED_STEPS
    ):
        raise ValueError(
            "multi-step tool use v1 expected trajectory must contain two or three steps"
        )

    normalized: list[_NormalizedStep] = []
    for index, raw_step in enumerate(raw_steps):
        path = f"/steps/{index}"
        if not isinstance(raw_step, dict) or set(raw_step) != _STEP_FIELDS:
            raise ValueError(f"multi-step tool use v1 expected step {path} has an invalid shape")
        tool = raw_step.get("tool")
        arguments = raw_step.get("arguments")
        if not isinstance(tool, str) or tool not in MULTI_STEP_TOOL_USE_CATALOG:
            raise ValueError(f"multi-step tool use v1 expected step {path} uses an unknown tool")
        if not isinstance(arguments, dict):
            raise ValueError(
                f"multi-step tool use v1 expected step {path} arguments must be an object"
            )
        normalized.append((tool, arguments))
    return tuple(normalized)


def _normalized_output_steps(
    output: JsonValue,
) -> tuple[tuple[_NormalizedStep, ...] | None, tuple[MultiStepToolUseIssue, ...]]:
    if not isinstance(output, dict) or set(output) != {"steps"}:
        return None, (MultiStepToolUseIssue("invalid_output_shape", "/"),)
    raw_steps = output.get("steps")
    if not isinstance(raw_steps, list):
        return None, (MultiStepToolUseIssue("wrong_steps_type", "/steps"),)

    normalized: list[_NormalizedStep] = []
    issues: list[MultiStepToolUseIssue] = []
    for index, raw_step in enumerate(raw_steps):
        path = f"/steps/{index}"
        if not isinstance(raw_step, dict) or set(raw_step) != _STEP_FIELDS:
            issues.append(MultiStepToolUseIssue("invalid_step_shape", path))
            continue
        tool = raw_step.get("tool")
        arguments = raw_step.get("arguments")
        if not isinstance(tool, str):
            issues.append(MultiStepToolUseIssue("wrong_tool_type", f"{path}/tool"))
            continue
        if tool not in MULTI_STEP_TOOL_USE_CATALOG:
            issues.append(MultiStepToolUseIssue("unknown_tool", f"{path}/tool"))
            continue
        if not isinstance(arguments, dict):
            issues.append(MultiStepToolUseIssue("wrong_arguments_type", f"{path}/arguments"))
            continue
        normalized.append((tool, arguments))

    if issues:
        return None, tuple(sorted(set(issues)))
    return tuple(normalized), ()


def _compare_values(
    expected: JsonValue,
    output: JsonValue,
    *,
    path: str,
) -> tuple[MultiStepToolUseIssue, ...]:
    if type(expected) is not type(output):
        return (MultiStepToolUseIssue("wrong_argument_type", path),)

    issues: list[MultiStepToolUseIssue] = []
    if isinstance(expected, dict) and isinstance(output, dict):
        for key in sorted(set(expected) - set(output)):
            issues.append(MultiStepToolUseIssue("missing_argument", _child_path(path, key)))
        for key in sorted(set(output) - set(expected)):
            issues.append(MultiStepToolUseIssue("extra_argument", _child_path(path, key)))
        for key in sorted(set(expected) & set(output)):
            issues.extend(_compare_values(expected[key], output[key], path=_child_path(path, key)))
        return tuple(issues)

    if isinstance(expected, list) and isinstance(output, list):
        if len(expected) != len(output):
            issues.append(MultiStepToolUseIssue("wrong_array_length", path))
        for index, (expected_item, output_item) in enumerate(zip(expected, output, strict=False)):
            issues.extend(
                _compare_values(expected_item, output_item, path=_child_path(path, str(index)))
            )
        return tuple(issues)

    if expected != output:
        issues.append(MultiStepToolUseIssue("wrong_argument_value", path))
    return tuple(issues)


def _child_path(path: str, key: str) -> str:
    escaped = key.replace("~", "~0").replace("/", "~1")
    return f"{path}/{escaped}"


def _zero_assessment(
    issues: tuple[MultiStepToolUseIssue, ...],
) -> MultiStepToolUseAssessment:
    return MultiStepToolUseAssessment(
        score=Decimal("0"),
        selection_score=Decimal("0"),
        arguments_score=Decimal("0"),
        issues=issues,
    )
