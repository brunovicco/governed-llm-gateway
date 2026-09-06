from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.contracts import BenchmarkWorkload, JsonValue
from benchmarks.dataset import load_dataset
from benchmarks.scoring import build_default_scorers
from benchmarks.snapshot import dataset_digest
from benchmarks.workloads.multi_step_tool_use import (
    MULTI_STEP_TOOL_USE_BENCHMARK_VERSION,
    MULTI_STEP_TOOL_USE_CATALOG,
    MULTI_STEP_TOOL_USE_SCORER_ID,
    MultiStepToolUseIssue,
    assess_multi_step_tool_use,
    load_multi_step_tool_use_dataset,
    validate_multi_step_tool_use_case,
)

_DATASET_PATH = Path("benchmarks/datasets/multi-step-tool-use-v1.json")


def _expected_output(case_index: int) -> dict[str, JsonValue]:
    case = load_multi_step_tool_use_dataset(_DATASET_PATH).cases[case_index]
    expected = case.expected
    assert isinstance(expected, dict)
    return deepcopy(expected)


def test_checked_in_multi_step_dataset_covers_reviewed_boundary() -> None:
    dataset = load_multi_step_tool_use_dataset(_DATASET_PATH)

    assert dataset.benchmark_version == MULTI_STEP_TOOL_USE_BENCHMARK_VERSION
    assert len(dataset.cases) == 4

    observed_tools: set[str] = set()
    observed_lengths: set[int] = set()
    for case in dataset.cases:
        assert case.workload is BenchmarkWorkload.MULTI_STEP_TOOL_USE
        assert case.scorer == MULTI_STEP_TOOL_USE_SCORER_ID
        assert case.metadata["execute_tools"] is False
        expected = case.expected
        assert isinstance(expected, dict)
        steps = expected.get("steps")
        assert isinstance(steps, list)
        observed_lengths.add(len(steps))
        for step in steps:
            assert isinstance(step, dict)
            tool = step.get("tool")
            assert isinstance(tool, str)
            observed_tools.add(tool)

    assert observed_tools == set(MULTI_STEP_TOOL_USE_CATALOG)
    assert observed_lengths == {2, 3}


def test_multi_step_dataset_digest_is_deterministic() -> None:
    first = load_multi_step_tool_use_dataset(_DATASET_PATH)
    second = load_multi_step_tool_use_dataset(_DATASET_PATH)

    assert dataset_digest(first.cases) == dataset_digest(second.cases)


def test_multi_step_scorer_accepts_exact_trajectory() -> None:
    case = load_multi_step_tool_use_dataset(_DATASET_PATH).cases[0]
    assessment = assess_multi_step_tool_use(case, _expected_output(0))

    assert assessment.score == Decimal("1")
    assert assessment.selection_score == Decimal("1")
    assert assessment.arguments_score == Decimal("1")
    assert assessment.trajectory_success is True
    assert assessment.issues == ()


def test_multi_step_scorer_reports_wrong_tool_without_rewarding_arguments() -> None:
    case = load_multi_step_tool_use_dataset(_DATASET_PATH).cases[0]
    output = _expected_output(0)
    steps = output.get("steps")
    assert isinstance(steps, list)
    second = steps[1]
    assert isinstance(second, dict)
    second["tool"] = "knowledge_search"

    assessment = assess_multi_step_tool_use(case, output)

    assert assessment.score == Decimal("0.5")
    assert assessment.selection_score == Decimal("0.5")
    assert assessment.arguments_score == Decimal("0.5")
    assert assessment.issues[0].code == "wrong_tool"
    assert assessment.issues[0].path == "/steps/1/tool"


def test_multi_step_scorer_is_type_sensitive_for_arguments() -> None:
    case = load_multi_step_tool_use_dataset(_DATASET_PATH).cases[0]
    output = _expected_output(0)
    steps = output.get("steps")
    assert isinstance(steps, list)
    second = steps[1]
    assert isinstance(second, dict)
    arguments = second.get("arguments")
    assert isinstance(arguments, dict)
    arguments["channels"] = "email"

    assessment = assess_multi_step_tool_use(case, output)

    assert assessment.score == Decimal("0.75")
    assert assessment.selection_score == Decimal("1")
    assert assessment.arguments_score == Decimal("0.5")
    assert assessment.issues[0].code == "wrong_argument_type"
    assert assessment.issues[0].path == "/steps/1/arguments/channels"


def test_multi_step_scorer_rejects_invalid_top_level_shape() -> None:
    case = load_multi_step_tool_use_dataset(_DATASET_PATH).cases[0]
    assessment = assess_multi_step_tool_use(case, {"calls": []})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "invalid_output_shape"


def test_multi_step_scorer_rejects_unknown_tool() -> None:
    case = load_multi_step_tool_use_dataset(_DATASET_PATH).cases[0]
    output = _expected_output(0)
    steps = output.get("steps")
    assert isinstance(steps, list)
    first = steps[0]
    assert isinstance(first, dict)
    first["tool"] = "unreviewed_tool"

    assessment = assess_multi_step_tool_use(case, output)

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "unknown_tool"
    assert assessment.issues[0].path == "/steps/0/tool"


def test_multi_step_scorer_reports_step_count_mismatch() -> None:
    case = load_multi_step_tool_use_dataset(_DATASET_PATH).cases[0]
    output = _expected_output(0)
    steps = output.get("steps")
    assert isinstance(steps, list)
    output["steps"] = steps[:1]

    assessment = assess_multi_step_tool_use(case, output)

    assert assessment.score == Decimal("0.5")
    assert MultiStepToolUseIssue("missing_step", "/steps/1") in assessment.issues
    assert MultiStepToolUseIssue("step_count_mismatch", "/steps") in assessment.issues


def test_multi_step_contract_rejects_execution_enablement() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "execute_tools": True})

    with pytest.raises(ValueError, match="tool execution must remain disabled"):
        validate_multi_step_tool_use_case(drifted)


def test_multi_step_contract_rejects_prompt_drift() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, prompt="Plan some tools.")

    with pytest.raises(ValueError, match="reviewed non-executing instruction"):
        validate_multi_step_tool_use_case(drifted)


def test_multi_step_contract_rejects_unknown_metadata() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "provider_hint": "openai"})

    with pytest.raises(ValueError, match="unknown fields: provider_hint"):
        validate_multi_step_tool_use_case(drifted)


def test_multi_step_contract_requires_two_or_three_expected_steps() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    expected = case.expected
    assert isinstance(expected, dict)
    steps = expected.get("steps")
    assert isinstance(steps, list)
    drifted = replace(case, expected={"steps": steps[:1]})

    with pytest.raises(ValueError, match="must contain two or three steps"):
        validate_multi_step_tool_use_case(drifted)


def test_multi_step_dataset_requires_exact_reviewed_case_count(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    payload["cases"] = cases[:-1]
    path = tmp_path / "multi-step-incomplete.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="requires exactly four reviewed cases"):
        load_multi_step_tool_use_dataset(path)


def test_multi_step_dataset_requires_every_reviewed_tool(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    weather_case = cases[1]
    assert isinstance(weather_case, dict)
    expected = weather_case.get("expected")
    assert isinstance(expected, dict)
    steps = expected.get("steps")
    assert isinstance(steps, list)
    first = steps[0]
    assert isinstance(first, dict)
    first["tool"] = "account_lookup"
    path = tmp_path / "multi-step-missing-tool.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="must cover every reviewed tool"):
        load_multi_step_tool_use_dataset(path)


def test_multi_step_dataset_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    first = cases[0]
    second = cases[1]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    second["case_id"] = first["case_id"]
    path = tmp_path / "multi-step-duplicate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_multi_step_tool_use_dataset(path)


def test_multi_step_scorer_is_registered() -> None:
    scorers = build_default_scorers()

    assert MULTI_STEP_TOOL_USE_SCORER_ID in scorers
