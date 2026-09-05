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
from benchmarks.workloads.classification import (
    CLASSIFICATION_BENCHMARK_VERSION,
    CLASSIFICATION_LABELS,
    CLASSIFICATION_SCORER_ID,
    assess_classification,
    load_classification_dataset,
    validate_classification_case,
)

_DATASET_PATH = Path("benchmarks/datasets/classification-v1.json")


def test_checked_in_classification_dataset_covers_reviewed_label_set() -> None:
    dataset = load_classification_dataset(_DATASET_PATH)

    assert dataset.benchmark_version == CLASSIFICATION_BENCHMARK_VERSION
    assert len(dataset.cases) == len(CLASSIFICATION_LABELS) * 2

    counts = {label: 0 for label in CLASSIFICATION_LABELS}
    for case in dataset.cases:
        assert case.workload is BenchmarkWorkload.CLASSIFICATION
        assert case.scorer == CLASSIFICATION_SCORER_ID
        assert case.prompt.strip() == case.prompt
        expected = case.expected
        assert isinstance(expected, dict)
        label = expected.get("label")
        assert isinstance(label, str)
        counts[label] += 1

    assert set(counts) == CLASSIFICATION_LABELS
    assert set(counts.values()) == {2}


def test_classification_dataset_digest_is_deterministic() -> None:
    first = load_classification_dataset(_DATASET_PATH)
    second = load_classification_dataset(_DATASET_PATH)

    assert dataset_digest(first.cases) == dataset_digest(second.cases)


def test_classification_scorer_accepts_exact_label() -> None:
    case = load_classification_dataset(_DATASET_PATH).cases[0]
    assessment = assess_classification(case, {"label": "account_access"})

    assert assessment.score == Decimal("1")
    assert assessment.classification_success is True
    assert assessment.issues == ()


def test_classification_scorer_rejects_wrong_reviewed_label() -> None:
    case = load_classification_dataset(_DATASET_PATH).cases[0]
    assessment = assess_classification(case, {"label": "billing"})

    assert assessment.score == Decimal("0")
    assert assessment.classification_success is False
    assert assessment.issues[0].code == "wrong_label"
    assert assessment.issues[0].path == "/label"


def test_classification_scorer_rejects_unknown_label() -> None:
    case = load_classification_dataset(_DATASET_PATH).cases[0]
    assessment = assess_classification(case, {"label": "other"})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "unknown_label"
    assert assessment.issues[0].path == "/label"


def test_classification_scorer_rejects_wrong_label_type() -> None:
    case = load_classification_dataset(_DATASET_PATH).cases[0]
    assessment = assess_classification(case, {"label": 42})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "wrong_label_type"
    assert assessment.issues[0].path == "/label"


def test_classification_scorer_rejects_invalid_output_shape() -> None:
    case = load_classification_dataset(_DATASET_PATH).cases[0]
    assessment = assess_classification(case, {"label": "account_access", "extra": True})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "invalid_output_shape"
    assert assessment.issues[0].path == "/"


def test_classification_contract_rejects_prompt_drift() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, prompt="Classify this request: account locked")

    with pytest.raises(ValueError, match="reviewed normalized instruction"):
        validate_classification_case(drifted)


def test_classification_contract_rejects_unknown_metadata() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "provider_hint": "openai"})

    with pytest.raises(ValueError, match="unknown fields: provider_hint"):
        validate_classification_case(drifted)


def test_classification_dataset_requires_two_cases_per_label(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    payload["cases"] = cases[:-1]
    path = tmp_path / "classification-incomplete.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly two cases for every reviewed label"):
        load_classification_dataset(path)


def test_classification_dataset_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    first = cases[0]
    second = cases[1]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    second["case_id"] = first["case_id"]
    path = tmp_path / "classification-duplicate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_classification_dataset(path)


def test_classification_scorer_is_registered() -> None:
    scorers = build_default_scorers()

    assert CLASSIFICATION_SCORER_ID in scorers
