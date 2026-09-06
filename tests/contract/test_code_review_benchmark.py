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
from benchmarks.workloads.code_review import (
    CODE_REVIEW_BENCHMARK_VERSION,
    CODE_REVIEW_RULE_SEVERITIES,
    CODE_REVIEW_SCORER_ID,
    assess_code_review,
    load_code_review_dataset,
    validate_code_review_case,
)

_DATASET_PATH = Path("benchmarks/datasets/code-review-v1.json")


def _finding(rule_id: str, line: int) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "severity": CODE_REVIEW_RULE_SEVERITIES[rule_id],
        "line": line,
    }


def test_checked_in_code_review_dataset_covers_rules_and_clean_cases() -> None:
    dataset = load_code_review_dataset(_DATASET_PATH)

    assert dataset.benchmark_version == CODE_REVIEW_BENCHMARK_VERSION
    assert len(dataset.cases) == len(CODE_REVIEW_RULE_SEVERITIES) + 2

    rule_counts = dict.fromkeys(CODE_REVIEW_RULE_SEVERITIES, 0)
    clean_cases = 0
    for case in dataset.cases:
        assert case.workload is BenchmarkWorkload.CODE_REVIEW
        assert case.scorer == CODE_REVIEW_SCORER_ID
        assert case.metadata["execute_candidate"] is False
        assert case.prompt.strip() == case.prompt
        expected = case.expected
        assert isinstance(expected, dict)
        findings = expected.get("findings")
        assert isinstance(findings, list)
        if not findings:
            clean_cases += 1
            continue
        finding = findings[0]
        assert isinstance(finding, dict)
        rule_id = finding.get("rule_id")
        assert isinstance(rule_id, str)
        rule_counts[rule_id] += 1

    assert set(rule_counts) == set(CODE_REVIEW_RULE_SEVERITIES)
    assert set(rule_counts.values()) == {1}
    assert clean_cases == 2


def test_code_review_dataset_digest_is_deterministic() -> None:
    first = load_code_review_dataset(_DATASET_PATH)
    second = load_code_review_dataset(_DATASET_PATH)

    assert dataset_digest(first.cases) == dataset_digest(second.cases)


def test_code_review_scorer_accepts_exact_finding() -> None:
    case = load_code_review_dataset(_DATASET_PATH).cases[0]
    assessment = assess_code_review(case, {"findings": [_finding("mutable_default_argument", 1)]})

    assert assessment.score == Decimal("1")
    assert assessment.review_success is True
    assert assessment.matched_findings == 1
    assert assessment.issues == ()


def test_code_review_scorer_gives_partial_credit_for_extra_valid_finding() -> None:
    case = load_code_review_dataset(_DATASET_PATH).cases[0]
    assessment = assess_code_review(
        case,
        {
            "findings": [
                _finding("mutable_default_argument", 1),
                _finding("broad_exception_catch", 2),
            ]
        },
    )

    assert assessment.score == Decimal(2) / Decimal(3)
    assert assessment.review_success is False
    assert assessment.matched_findings == 1
    assert assessment.observed_findings == 2
    assert assessment.issues[0].code == "unexpected_finding"


def test_code_review_scorer_rejects_missing_finding() -> None:
    case = load_code_review_dataset(_DATASET_PATH).cases[0]
    assessment = assess_code_review(case, {"findings": []})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "missing_finding"
    assert assessment.issues[0].path == "/findings"


def test_code_review_scorer_accepts_reviewed_clean_case() -> None:
    case = load_code_review_dataset(_DATASET_PATH).cases[-1]
    assessment = assess_code_review(case, {"findings": []})

    assert assessment.score == Decimal("1")
    assert assessment.review_success is True
    assert assessment.expected_findings == 0
    assert assessment.observed_findings == 0


def test_code_review_scorer_penalizes_false_positive_on_clean_case() -> None:
    case = load_code_review_dataset(_DATASET_PATH).cases[-1]
    assessment = assess_code_review(
        case,
        {"findings": [_finding("repeated_membership_scan", 2)]},
    )

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "unexpected_finding"


def test_code_review_scorer_rejects_invalid_severity() -> None:
    case = load_code_review_dataset(_DATASET_PATH).cases[0]
    assessment = assess_code_review(
        case,
        {
            "findings": [
                {"rule_id": "mutable_default_argument", "severity": "high", "line": 1}
            ]
        },
    )

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "invalid_finding"
    assert assessment.issues[0].path == "/findings/0"


def test_code_review_scorer_rejects_duplicate_finding() -> None:
    case = load_code_review_dataset(_DATASET_PATH).cases[0]
    finding = _finding("mutable_default_argument", 1)
    assessment = assess_code_review(case, {"findings": [finding, finding]})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "duplicate_finding"
    assert assessment.issues[0].path == "/findings/1"


def test_code_review_contract_rejects_prompt_drift() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, prompt="Execute this code and explain every issue.")

    with pytest.raises(ValueError, match="reviewed non-executing instruction"):
        validate_code_review_case(drifted)


def test_code_review_contract_rejects_unknown_metadata() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "provider_hint": "openai"})

    with pytest.raises(ValueError, match="unknown fields: provider_hint"):
        validate_code_review_case(drifted)


def test_code_review_contract_requires_execution_disabled() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "execute_candidate": True})

    with pytest.raises(ValueError, match="execution must remain disabled"):
        validate_code_review_case(drifted)


def test_code_review_dataset_requires_every_reviewed_rule(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    payload["cases"] = cases[1:]
    path = tmp_path / "code-review-incomplete.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly one case for every reviewed rule"):
        load_code_review_dataset(path)


def test_code_review_dataset_requires_two_clean_cases(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    payload["cases"] = cases[:-1]
    path = tmp_path / "code-review-clean-incomplete.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly two reviewed clean cases"):
        load_code_review_dataset(path)


def test_code_review_dataset_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    first = cases[0]
    second = cases[1]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    second["case_id"] = first["case_id"]
    path = tmp_path / "code-review-duplicate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_code_review_dataset(path)


def test_code_review_scorer_is_registered() -> None:
    scorers = build_default_scorers()

    assert CODE_REVIEW_SCORER_ID in scorers
