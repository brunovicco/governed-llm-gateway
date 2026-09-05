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
from benchmarks.workloads.long_context import (
    LONG_CONTEXT_BENCHMARK_VERSION,
    LONG_CONTEXT_RECORD_COUNT,
    LONG_CONTEXT_SCORER_ID,
    assess_long_context,
    load_long_context_dataset,
    materialize_long_context_case,
    validate_long_context_case,
)

_DATASET_PATH = Path("benchmarks/datasets/long-context-v1.json")


def test_checked_in_long_context_dataset_materializes_reviewed_positions() -> None:
    dataset = load_long_context_dataset(_DATASET_PATH)

    assert dataset.benchmark_version == LONG_CONTEXT_BENCHMARK_VERSION
    assert [case.metadata["needle_position"] for case in dataset.cases] == [
        "early",
        "middle",
        "late",
    ]

    for case in dataset.cases:
        assert case.workload is BenchmarkWorkload.LONG_CONTEXT
        assert case.scorer == LONG_CONTEXT_SCORER_ID
        assert case.prompt.count("record-") == LONG_CONTEXT_RECORD_COUNT
        assert len(case.prompt) > 300_000
        assert case.prompt.count("needle=") == 1

        expected = case.expected
        assert isinstance(expected, dict)
        needle = expected.get("needle")
        assert isinstance(needle, str)
        needle_record = case.metadata.get("needle_record")
        assert isinstance(needle_record, int)
        assert not isinstance(needle_record, bool)
        assert f"record-{needle_record:05d}: needle={needle}\n" in case.prompt


def test_long_context_materialization_is_deterministic() -> None:
    first = load_long_context_dataset(_DATASET_PATH)
    second = load_long_context_dataset(_DATASET_PATH)

    assert [case.prompt for case in first.cases] == [case.prompt for case in second.cases]
    assert dataset_digest(first.cases) == dataset_digest(second.cases)


def test_long_context_scorer_accepts_exact_needle() -> None:
    case = load_long_context_dataset(_DATASET_PATH).cases[0]
    assessment = assess_long_context(case, {"needle": "amber-signal"})

    assert assessment.score == Decimal("1")
    assert assessment.retrieval_success is True
    assert assessment.issues == ()


def test_long_context_scorer_rejects_wrong_needle() -> None:
    case = load_long_context_dataset(_DATASET_PATH).cases[0]
    assessment = assess_long_context(case, {"needle": "violet-signal"})

    assert assessment.score == Decimal("0")
    assert assessment.retrieval_success is False
    assert assessment.issues[0].code == "wrong_needle"
    assert assessment.issues[0].path == "/needle"


def test_long_context_scorer_rejects_invalid_shape() -> None:
    case = load_long_context_dataset(_DATASET_PATH).cases[0]
    assessment = assess_long_context(case, {"needle": "amber-signal", "extra": True})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "invalid_output_shape"
    assert assessment.issues[0].path == "/"


def test_long_context_scorer_rejects_wrong_value_type() -> None:
    case = load_long_context_dataset(_DATASET_PATH).cases[0]
    assessment = assess_long_context(case, {"needle": 42})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "wrong_value_type"
    assert assessment.issues[0].path == "/needle"


def test_long_context_contract_rejects_record_count_drift() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "record_count": 8193})

    with pytest.raises(ValueError, match="record_count must be 8192"):
        validate_long_context_case(drifted)


def test_long_context_contract_rejects_position_record_drift() -> None:
    case = load_dataset(_DATASET_PATH).cases[1]
    drifted = replace(case, metadata={**case.metadata, "needle_record": 4095})

    with pytest.raises(ValueError, match="needle_record does not match"):
        validate_long_context_case(drifted)


def test_long_context_materializer_rejects_instruction_drift() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, prompt="Different instruction")

    with pytest.raises(ValueError, match="prompt instruction drifted"):
        materialize_long_context_case(drifted)


def test_long_context_dataset_requires_all_reviewed_positions(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    payload["cases"] = cases[:2]
    path = tmp_path / "long-context-incomplete.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly one early, middle, and late case"):
        load_long_context_dataset(path)


def test_long_context_scorer_is_registered() -> None:
    scorers = build_default_scorers()

    assert LONG_CONTEXT_SCORER_ID in scorers
