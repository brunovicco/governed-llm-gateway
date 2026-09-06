from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.contracts import BenchmarkWorkload
from benchmarks.dataset import load_dataset
from benchmarks.scoring import build_default_scorers
from benchmarks.snapshot import dataset_digest
from benchmarks.workloads.tool_selection import (
    TOOL_SELECTION_BENCHMARK_VERSION,
    TOOL_SELECTION_CATALOG,
    TOOL_SELECTION_SCORER_ID,
    assess_tool_selection,
    load_tool_selection_dataset,
    validate_tool_selection_case,
)

_DATASET_PATH = Path("benchmarks/datasets/tool-selection-v1.json")


def test_checked_in_tool_selection_dataset_covers_catalog_and_no_tool_cases() -> None:
    dataset = load_tool_selection_dataset(_DATASET_PATH)

    assert dataset.benchmark_version == TOOL_SELECTION_BENCHMARK_VERSION
    assert len(dataset.cases) == len(TOOL_SELECTION_CATALOG) + 2

    counts = dict.fromkeys(TOOL_SELECTION_CATALOG, 0)
    no_tool_cases = 0
    for case in dataset.cases:
        assert case.workload is BenchmarkWorkload.TOOL_SELECTION
        assert case.scorer == TOOL_SELECTION_SCORER_ID
        assert case.metadata["execute_tool"] is False
        expected = case.expected
        assert isinstance(expected, dict)
        tool = expected.get("tool")
        if tool is None:
            no_tool_cases += 1
        else:
            assert isinstance(tool, str)
            counts[tool] += 1

    assert set(counts.values()) == {1}
    assert no_tool_cases == 2


def test_tool_selection_dataset_digest_is_deterministic() -> None:
    first = load_tool_selection_dataset(_DATASET_PATH)
    second = load_tool_selection_dataset(_DATASET_PATH)

    assert dataset_digest(first.cases) == dataset_digest(second.cases)


def test_tool_selection_scorer_accepts_exact_tool() -> None:
    case = load_tool_selection_dataset(_DATASET_PATH).cases[0]
    assessment = assess_tool_selection(case, {"tool": "account_lookup"})

    assert assessment.score == Decimal("1")
    assert assessment.selection_success is True
    assert assessment.issues == ()


def test_tool_selection_scorer_accepts_no_tool() -> None:
    case = load_tool_selection_dataset(_DATASET_PATH).cases[-1]
    assessment = assess_tool_selection(case, {"tool": None})

    assert assessment.score == Decimal("1")
    assert assessment.selection_success is True


def test_tool_selection_scorer_rejects_wrong_tool() -> None:
    case = load_tool_selection_dataset(_DATASET_PATH).cases[0]
    assessment = assess_tool_selection(case, {"tool": "knowledge_search"})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "wrong_tool"
    assert assessment.issues[0].path == "/tool"


def test_tool_selection_scorer_rejects_missing_tool() -> None:
    case = load_tool_selection_dataset(_DATASET_PATH).cases[0]
    assessment = assess_tool_selection(case, {"tool": None})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "missing_tool"


def test_tool_selection_no_tool_case_rejects_unexpected_tool() -> None:
    case = load_tool_selection_dataset(_DATASET_PATH).cases[-1]
    assessment = assess_tool_selection(case, {"tool": "account_lookup"})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "unexpected_tool"


def test_tool_selection_scorer_rejects_unknown_tool() -> None:
    case = load_tool_selection_dataset(_DATASET_PATH).cases[0]
    assessment = assess_tool_selection(case, {"tool": "unknown_tool"})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "unknown_tool"


def test_tool_selection_scorer_rejects_arguments_in_output() -> None:
    case = load_tool_selection_dataset(_DATASET_PATH).cases[0]
    assessment = assess_tool_selection(case, {"tool": "account_lookup", "arguments": {}})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "invalid_output_shape"


def test_tool_selection_contract_rejects_execution_enablement() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "execute_tool": True})

    with pytest.raises(ValueError, match="execution must remain disabled"):
        validate_tool_selection_case(drifted)


def test_tool_selection_contract_rejects_unknown_metadata() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "arguments": {}})

    with pytest.raises(ValueError, match="unknown fields: arguments"):
        validate_tool_selection_case(drifted)


def test_tool_selection_contract_rejects_prompt_drift() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, prompt="Choose any tool and call it")

    with pytest.raises(ValueError, match="reviewed catalog instruction"):
        validate_tool_selection_case(drifted)


def test_tool_selection_dataset_requires_every_reviewed_tool(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    payload["cases"] = cases[1:]
    path = tmp_path / "tool-selection-incomplete.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly one case for every reviewed tool"):
        load_tool_selection_dataset(path)


def test_tool_selection_dataset_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    first = cases[0]
    second = cases[1]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    second["case_id"] = first["case_id"]
    path = tmp_path / "tool-selection-duplicate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_tool_selection_dataset(path)


def test_tool_selection_scorer_is_registered() -> None:
    scorers = build_default_scorers()

    assert TOOL_SELECTION_SCORER_ID in scorers
