from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.contracts import BenchmarkWorkload, JsonValue
from benchmarks.dataset import load_dataset
from benchmarks.scoring import build_default_scorers
from benchmarks.snapshot import dataset_digest
from benchmarks.workloads.tool_argument_generation import (
    TOOL_ARGUMENT_GENERATION_BENCHMARK_VERSION,
    TOOL_ARGUMENT_GENERATION_CATALOG,
    TOOL_ARGUMENT_GENERATION_SCORER_ID,
    assess_tool_argument_generation,
    load_tool_argument_generation_dataset,
    validate_tool_argument_generation_case,
)

_DATASET_PATH = Path("benchmarks/datasets/tool-argument-generation-v1.json")


def _expected_arguments(case_index: int) -> dict[str, JsonValue]:
    case = load_tool_argument_generation_dataset(_DATASET_PATH).cases[case_index]
    expected = case.expected
    assert isinstance(expected, dict)
    arguments = expected.get("arguments")
    assert isinstance(arguments, dict)
    return arguments


def test_checked_in_tool_argument_dataset_covers_every_reviewed_tool() -> None:
    dataset = load_tool_argument_generation_dataset(_DATASET_PATH)

    assert dataset.benchmark_version == TOOL_ARGUMENT_GENERATION_BENCHMARK_VERSION
    assert len(dataset.cases) == len(TOOL_ARGUMENT_GENERATION_CATALOG)

    counts = dict.fromkeys(TOOL_ARGUMENT_GENERATION_CATALOG, 0)
    for case in dataset.cases:
        assert case.workload is BenchmarkWorkload.TOOL_ARGUMENT_GENERATION
        assert case.scorer == TOOL_ARGUMENT_GENERATION_SCORER_ID
        assert case.metadata["execute_tool"] is False
        selected_tool = case.metadata.get("selected_tool")
        assert isinstance(selected_tool, str)
        counts[selected_tool] += 1

    assert set(counts.values()) == {1}


def test_tool_argument_dataset_digest_is_deterministic() -> None:
    first = load_tool_argument_generation_dataset(_DATASET_PATH)
    second = load_tool_argument_generation_dataset(_DATASET_PATH)

    assert dataset_digest(first.cases) == dataset_digest(second.cases)


def test_tool_argument_scorer_accepts_exact_arguments() -> None:
    case = load_tool_argument_generation_dataset(_DATASET_PATH).cases[0]
    assessment = assess_tool_argument_generation(
        case,
        {"arguments": _expected_arguments(0)},
    )

    assert assessment.score == Decimal("1")
    assert assessment.arguments_success is True
    assert assessment.issues == ()


def test_tool_argument_scorer_rejects_tool_selection_field() -> None:
    case = load_tool_argument_generation_dataset(_DATASET_PATH).cases[0]
    assessment = assess_tool_argument_generation(
        case,
        {"tool": "account_lookup", "arguments": _expected_arguments(0)},
    )

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "invalid_output_shape"


def test_tool_argument_scorer_rejects_wrong_arguments_type() -> None:
    case = load_tool_argument_generation_dataset(_DATASET_PATH).cases[0]
    assessment = assess_tool_argument_generation(case, {"arguments": []})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "wrong_arguments_type"


def test_tool_argument_scorer_reports_missing_argument() -> None:
    case = load_tool_argument_generation_dataset(_DATASET_PATH).cases[0]
    assessment = assess_tool_argument_generation(case, {"arguments": {"account_id": "A-104"}})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "missing_argument"
    assert assessment.issues[0].path == "/arguments/include_history"


def test_tool_argument_scorer_reports_extra_argument() -> None:
    case = load_tool_argument_generation_dataset(_DATASET_PATH).cases[0]
    arguments = dict(_expected_arguments(0))
    arguments["extra"] = True
    assessment = assess_tool_argument_generation(case, {"arguments": arguments})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "extra_argument"
    assert assessment.issues[0].path == "/arguments/extra"


def test_tool_argument_scorer_is_type_sensitive_for_boolean() -> None:
    case = load_tool_argument_generation_dataset(_DATASET_PATH).cases[0]
    assessment = assess_tool_argument_generation(
        case,
        {"arguments": {"account_id": "A-104", "include_history": 0}},
    )

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "wrong_type"
    assert assessment.issues[0].path == "/arguments/include_history"


def test_tool_argument_scorer_reports_array_length_drift() -> None:
    case = load_tool_argument_generation_dataset(_DATASET_PATH).cases[2]
    assessment = assess_tool_argument_generation(
        case,
        {
            "arguments": {
                "user_id": "U-7",
                "message": "Maintenance moved",
                "channels": ["email"],
            }
        },
    )

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "wrong_array_length"
    assert assessment.issues[0].path == "/arguments/channels"


def test_tool_argument_contract_rejects_execution_enablement() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "execute_tool": True})

    with pytest.raises(ValueError, match="execution must remain disabled"):
        validate_tool_argument_generation_case(drifted)


def test_tool_argument_contract_rejects_selected_tool_drift() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "selected_tool": "knowledge_search"})

    with pytest.raises(ValueError, match="bind the reviewed selected tool"):
        validate_tool_argument_generation_case(drifted)


def test_tool_argument_contract_rejects_unknown_metadata() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "provider_hint": "openai"})

    with pytest.raises(ValueError, match="unknown fields: provider_hint"):
        validate_tool_argument_generation_case(drifted)


def test_tool_argument_dataset_requires_every_reviewed_tool(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    payload["cases"] = cases[:-1]
    path = tmp_path / "tool-arguments-incomplete.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly one case for every reviewed tool"):
        load_tool_argument_generation_dataset(path)


def test_tool_argument_dataset_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    first = cases[0]
    second = cases[1]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    second["case_id"] = first["case_id"]
    path = tmp_path / "tool-arguments-duplicate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_tool_argument_generation_dataset(path)


def test_tool_argument_scorer_is_registered() -> None:
    scorers = build_default_scorers()

    assert TOOL_ARGUMENT_GENERATION_SCORER_ID in scorers
