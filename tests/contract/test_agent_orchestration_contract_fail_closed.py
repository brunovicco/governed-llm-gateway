"""Fail-closed regressions for the agent-orchestration v1 benchmark contract."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from benchmarks.contracts import BenchmarkCase, BenchmarkWorkload
from benchmarks.workloads.agent_orchestration import (
    load_agent_orchestration_dataset,
    validate_agent_orchestration_case,
)

_DATASET = Path("benchmarks/datasets/agent-orchestration-v1.json")


def _first_case() -> BenchmarkCase:
    return load_agent_orchestration_dataset(_DATASET).cases[0]


def _payload() -> dict[str, object]:
    value = json.loads(_DATASET.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "agent-orchestration-v1-invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_rejects_wrong_workload() -> None:
    case = replace(_first_case(), workload=BenchmarkWorkload.TOOL_USE)

    with pytest.raises(ValueError, match="different workload"):
        validate_agent_orchestration_case(case)


def test_rejects_wrong_scorer() -> None:
    case = replace(_first_case(), scorer="ordered_sequence")

    with pytest.raises(ValueError, match="versioned deterministic scorer"):
        validate_agent_orchestration_case(case)


def test_rejects_wrong_contract_version() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["contract_version"] = "2.0"
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="contract_version must be 1.0"):
        validate_agent_orchestration_case(case)


def test_rejects_unknown_metadata() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["runtime_authority"] = True
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="metadata contains unknown fields"):
        validate_agent_orchestration_case(case)


def test_rejects_step_execution_enablement() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["execute_steps"] = True
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="step execution must remain disabled"):
        validate_agent_orchestration_case(case)


def test_rejects_duplicate_allowed_agents() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["allowed_agents"] = ["router", "router"]
    metadata["allowed_actions"] = {"router": ["classify_request"]}
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="allowed_agents must not contain duplicates"):
        validate_agent_orchestration_case(case)


def test_rejects_allowed_actions_without_complete_agent_coverage() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    raw_actions = metadata["allowed_actions"]
    assert isinstance(raw_actions, dict)
    actions = dict(raw_actions)
    actions.pop("escalation")
    metadata["allowed_actions"] = actions
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="must cover every allowed agent"):
        validate_agent_orchestration_case(case)


def test_rejects_duplicate_allowed_actions() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    raw_actions = metadata["allowed_actions"]
    assert isinstance(raw_actions, dict)
    actions = dict(raw_actions)
    actions["router"] = ["classify_request", "classify_request"]
    metadata["allowed_actions"] = actions
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="allowed_actions must not contain duplicates"):
        validate_agent_orchestration_case(case)


def test_rejects_expected_undeclared_agent() -> None:
    original = _first_case()
    assert isinstance(original.expected, dict)
    steps = original.expected["steps"]
    assert isinstance(steps, list)
    first_step = steps[0]
    assert isinstance(first_step, dict)
    changed_first = dict(first_step)
    changed_first["agent"] = "admin"
    expected = {"steps": [changed_first, *steps[1:]]}
    case = replace(original, expected=expected)

    with pytest.raises(ValueError, match="uses an undeclared agent"):
        validate_agent_orchestration_case(case)


def test_rejects_expected_undeclared_action() -> None:
    original = _first_case()
    assert isinstance(original.expected, dict)
    steps = original.expected["steps"]
    assert isinstance(steps, list)
    first_step = steps[0]
    assert isinstance(first_step, dict)
    changed_first = dict(first_step)
    changed_first["action"] = "execute_business_side_effect"
    expected = {"steps": [changed_first, *steps[1:]]}
    case = replace(original, expected=expected)

    with pytest.raises(ValueError, match="uses an undeclared action"):
        validate_agent_orchestration_case(case)


def test_rejects_expected_invalid_handoff_target() -> None:
    original = _first_case()
    assert isinstance(original.expected, dict)
    steps = original.expected["steps"]
    assert isinstance(steps, list)
    first_step = steps[0]
    assert isinstance(first_step, dict)
    changed_first = dict(first_step)
    changed_first["handoff_to"] = "admin"
    expected = {"steps": [changed_first, *steps[1:]]}
    case = replace(original, expected=expected)

    with pytest.raises(ValueError, match="invalid handoff target"):
        validate_agent_orchestration_case(case)


def test_rejects_expected_broken_handoff_chain() -> None:
    original = _first_case()
    assert isinstance(original.expected, dict)
    steps = original.expected["steps"]
    assert isinstance(steps, list)
    first_step = steps[0]
    assert isinstance(first_step, dict)
    changed_first = dict(first_step)
    changed_first["handoff_to"] = "customer_support"
    expected = {"steps": [changed_first, *steps[1:]]}
    case = replace(original, expected=expected)

    with pytest.raises(ValueError, match="handoff chain must match the next agent"):
        validate_agent_orchestration_case(case)


def test_rejects_expected_non_terminal_final_handoff() -> None:
    original = _first_case()
    assert isinstance(original.expected, dict)
    steps = original.expected["steps"]
    assert isinstance(steps, list)
    last_step = steps[-1]
    assert isinstance(last_step, dict)
    changed_last = dict(last_step)
    changed_last["handoff_to"] = "router"
    expected = {"steps": [*steps[:-1], changed_last]}
    case = replace(original, expected=expected)

    with pytest.raises(ValueError, match="must terminate with null handoff"):
        validate_agent_orchestration_case(case)


def test_rejects_wrong_benchmark_version(tmp_path: Path) -> None:
    payload = _payload()
    payload["benchmark_version"] = "agent-orchestration-v2"

    with pytest.raises(ValueError, match="benchmark_version agent-orchestration-v1"):
        load_agent_orchestration_dataset(_write(tmp_path, payload))


def test_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = _payload()
    cases = payload["cases"]
    assert isinstance(cases, list)
    assert isinstance(cases[0], dict)
    assert isinstance(cases[1], dict)
    cases[1]["case_id"] = cases[0]["case_id"]

    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_agent_orchestration_dataset(_write(tmp_path, payload))
