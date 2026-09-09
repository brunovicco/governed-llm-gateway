import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.contracts import BenchmarkWorkload, JsonValue
from benchmarks.dataset import load_dataset
from benchmarks.scoring import build_default_scorers
from benchmarks.snapshot import dataset_digest
from benchmarks.workloads.reasoning import (
    REASONING_BENCHMARK_VERSION,
    REASONING_FAMILIES,
    REASONING_SCORER_ID,
    assess_reasoning,
    load_reasoning_dataset,
    validate_reasoning_case,
)

_DATASET_PATH = Path("benchmarks/datasets/reasoning-v1.json")


def test_checked_in_reasoning_dataset_covers_reviewed_families() -> None:
    dataset = load_reasoning_dataset(_DATASET_PATH)

    assert dataset.benchmark_version == REASONING_BENCHMARK_VERSION
    assert len(dataset.cases) == len(REASONING_FAMILIES) * 3

    counts = dict.fromkeys(REASONING_FAMILIES, 0)
    for case in dataset.cases:
        assert case.workload is BenchmarkWorkload.REASONING
        assert case.scorer == REASONING_SCORER_ID
        assert case.metadata["answer_only"] is True
        assert case.prompt.strip() == case.prompt
        family = case.metadata["family"]
        assert isinstance(family, str)
        counts[family] += 1

    assert set(counts) == REASONING_FAMILIES
    assert set(counts.values()) == {3}


def test_reasoning_dataset_digest_is_deterministic() -> None:
    first = load_reasoning_dataset(_DATASET_PATH)
    second = load_reasoning_dataset(_DATASET_PATH)

    assert dataset_digest(first.cases) == dataset_digest(second.cases)


@pytest.mark.parametrize(
    ("case_index", "output"),
    [
        (0, {"answer": 395}),
        (3, {"answer": True}),
        (6, {"answer": "bruno"}),
    ],
)
def test_reasoning_scorer_accepts_exact_type_sensitive_answer(
    case_index: int,
    output: JsonValue,
) -> None:
    case = load_reasoning_dataset(_DATASET_PATH).cases[case_index]
    assessment = assess_reasoning(case, output)

    assert assessment.score == Decimal("1")
    assert assessment.reasoning_success is True
    assert assessment.issues == ()


def test_reasoning_scorer_rejects_wrong_answer() -> None:
    case = load_reasoning_dataset(_DATASET_PATH).cases[0]
    assessment = assess_reasoning(case, {"answer": 396})

    assert assessment.score == Decimal("0")
    assert assessment.reasoning_success is False
    assert assessment.issues[0].code == "wrong_answer"
    assert assessment.issues[0].path == "/answer"


def test_reasoning_scorer_rejects_wrong_answer_type() -> None:
    case = load_reasoning_dataset(_DATASET_PATH).cases[3]
    assessment = assess_reasoning(case, {"answer": 1})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "wrong_answer_type"
    assert assessment.issues[0].path == "/answer"


def test_reasoning_scorer_rejects_explanation_field() -> None:
    case = load_reasoning_dataset(_DATASET_PATH).cases[0]
    assessment = assess_reasoning(case, {"answer": 395, "explanation": "hidden reasoning"})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "invalid_output_shape"
    assert assessment.issues[0].path == "/"


def test_reasoning_contract_rejects_prompt_drift() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, prompt="Explain your reasoning and then give the answer.")

    with pytest.raises(ValueError, match="reviewed answer-only instruction"):
        validate_reasoning_case(drifted)


def test_reasoning_contract_rejects_unknown_metadata() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "provider_hint": "openai"})

    with pytest.raises(ValueError, match="unknown fields: provider_hint"):
        validate_reasoning_case(drifted)


def test_reasoning_contract_requires_answer_only() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "answer_only": False})

    with pytest.raises(ValueError, match="must remain answer-only"):
        validate_reasoning_case(drifted)


def test_reasoning_contract_rejects_unbounded_expected_type() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, expected={"answer": 3.14})

    with pytest.raises(ValueError, match="string, integer, or boolean"):
        validate_reasoning_case(drifted)


def test_reasoning_dataset_requires_three_cases_per_family(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    payload["cases"] = cases[:-1]
    path = tmp_path / "reasoning-incomplete.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly three cases for every reviewed family"):
        load_reasoning_dataset(path)


def test_reasoning_dataset_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    first = cases[0]
    second = cases[1]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    second["case_id"] = first["case_id"]
    path = tmp_path / "reasoning-duplicate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_reasoning_dataset(path)


def test_reasoning_scorer_is_registered() -> None:
    scorers = build_default_scorers()

    assert REASONING_SCORER_ID in scorers
