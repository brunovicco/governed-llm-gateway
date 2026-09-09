import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.contracts import BenchmarkWorkload, JsonValue
from benchmarks.dataset import load_dataset
from benchmarks.scoring import build_default_scorers
from benchmarks.snapshot import dataset_digest
from benchmarks.workloads.security_analysis import (
    SECURITY_ANALYSIS_BENCHMARK_VERSION,
    SECURITY_ANALYSIS_RULE_SEVERITIES,
    SECURITY_ANALYSIS_SCORER_ID,
    assess_security_analysis,
    load_security_analysis_dataset,
    validate_security_analysis_case,
)

_DATASET_PATH = Path("benchmarks/datasets/security-analysis-v1.json")


def _finding(case_index: int) -> dict[str, JsonValue]:
    case = load_security_analysis_dataset(_DATASET_PATH).cases[case_index]
    expected = case.expected
    assert isinstance(expected, dict)
    findings = expected.get("findings")
    assert isinstance(findings, list)
    assert findings
    finding = findings[0]
    assert isinstance(finding, dict)
    return finding


def test_checked_in_security_analysis_dataset_covers_reviewed_rules() -> None:
    dataset = load_security_analysis_dataset(_DATASET_PATH)

    assert dataset.benchmark_version == SECURITY_ANALYSIS_BENCHMARK_VERSION
    assert len(dataset.cases) == len(SECURITY_ANALYSIS_RULE_SEVERITIES) + 2

    counts = dict.fromkeys(SECURITY_ANALYSIS_RULE_SEVERITIES, 0)
    clean_cases = 0
    for case in dataset.cases:
        assert case.workload is BenchmarkWorkload.SECURITY_ANALYSIS
        assert case.scorer == SECURITY_ANALYSIS_SCORER_ID
        assert case.prompt.strip() == case.prompt
        assert case.metadata["execute_candidate"] is False
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
        counts[rule_id] += 1

    assert set(counts) == set(SECURITY_ANALYSIS_RULE_SEVERITIES)
    assert set(counts.values()) == {1}
    assert clean_cases == 2


def test_security_analysis_dataset_digest_is_deterministic() -> None:
    first = load_security_analysis_dataset(_DATASET_PATH)
    second = load_security_analysis_dataset(_DATASET_PATH)

    assert dataset_digest(first.cases) == dataset_digest(second.cases)


def test_security_analysis_scorer_accepts_exact_finding() -> None:
    case = load_security_analysis_dataset(_DATASET_PATH).cases[0]
    assessment = assess_security_analysis(case, {"findings": [_finding(0)]})

    assert assessment.score == Decimal("1")
    assert assessment.analysis_success is True
    assert assessment.issues == ()


def test_security_analysis_scorer_penalizes_missing_finding() -> None:
    case = load_security_analysis_dataset(_DATASET_PATH).cases[0]
    assessment = assess_security_analysis(case, {"findings": []})

    assert assessment.score == Decimal("0")
    assert assessment.analysis_success is False
    assert assessment.issues[0].code == "missing_finding"


def test_security_analysis_clean_case_penalizes_false_positive() -> None:
    dataset = load_security_analysis_dataset(_DATASET_PATH)
    clean_case = dataset.cases[-1]
    assessment = assess_security_analysis(clean_case, {"findings": [_finding(0)]})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "unexpected_finding"


def test_security_analysis_rejects_wrong_severity() -> None:
    case = load_security_analysis_dataset(_DATASET_PATH).cases[0]
    finding = dict(_finding(0))
    finding["severity"] = "low"
    assessment = assess_security_analysis(case, {"findings": [finding]})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "invalid_finding"


def test_security_analysis_rejects_duplicate_finding() -> None:
    case = load_security_analysis_dataset(_DATASET_PATH).cases[0]
    finding = _finding(0)
    assessment = assess_security_analysis(case, {"findings": [finding, finding]})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "duplicate_finding"


def test_security_analysis_rejects_invalid_output_shape() -> None:
    case = load_security_analysis_dataset(_DATASET_PATH).cases[0]
    assessment = assess_security_analysis(case, {"findings": [], "explanation": "extra"})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "invalid_output_shape"


def test_security_analysis_rejects_oversized_finding_list() -> None:
    case = load_security_analysis_dataset(_DATASET_PATH).cases[0]
    assessment = assess_security_analysis(case, {"findings": [_finding(0)] * 9})

    assert assessment.score == Decimal("0")
    assert assessment.issues[0].code == "invalid_findings"


def test_security_analysis_contract_rejects_execution_enablement() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "execute_candidate": True})

    with pytest.raises(ValueError, match="execution must remain disabled"):
        validate_security_analysis_case(drifted)


def test_security_analysis_contract_rejects_unknown_metadata() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "provider_hint": "openai"})

    with pytest.raises(ValueError, match="unknown fields: provider_hint"):
        validate_security_analysis_case(drifted)


def test_security_analysis_contract_rejects_prompt_drift() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, prompt="Analyze and provide exploitation steps")

    with pytest.raises(ValueError, match="reviewed defensive instruction"):
        validate_security_analysis_case(drifted)


def test_security_analysis_dataset_requires_all_reviewed_rules(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    payload["cases"] = cases[1:]
    path = tmp_path / "security-analysis-incomplete.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly one case for every reviewed rule"):
        load_security_analysis_dataset(path)


def test_security_analysis_dataset_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    first = cases[0]
    second = cases[1]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    second["case_id"] = first["case_id"]
    path = tmp_path / "security-analysis-duplicate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_security_analysis_dataset(path)


def test_security_analysis_scorer_is_registered() -> None:
    scorers = build_default_scorers()

    assert SECURITY_ANALYSIS_SCORER_ID in scorers
