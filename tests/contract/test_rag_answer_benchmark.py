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
from benchmarks.workloads.rag_answer import (
    RAG_ANSWER_BENCHMARK_VERSION,
    RAG_ANSWER_SCORER_ID,
    RagAnswerIssue,
    assess_rag_answer,
    load_rag_answer_dataset,
    validate_rag_answer_case,
)

_DATASET_PATH = Path("benchmarks/datasets/rag-answer-v1.json")


def _expected_output(case_index: int) -> dict[str, JsonValue]:
    case = load_rag_answer_dataset(_DATASET_PATH).cases[case_index]
    expected = case.expected
    assert isinstance(expected, dict)
    return deepcopy(expected)


def test_checked_in_rag_answer_dataset_covers_reviewed_boundary() -> None:
    dataset = load_rag_answer_dataset(_DATASET_PATH)

    assert dataset.benchmark_version == RAG_ANSWER_BENCHMARK_VERSION
    assert len(dataset.cases) == 6
    assert {case.metadata["language"] for case in dataset.cases} == {"en", "pt-BR"}
    for case in dataset.cases:
        assert case.workload is BenchmarkWorkload.RAG_ANSWER
        assert case.scorer == RAG_ANSWER_SCORER_ID
        assert case.metadata["synthetic"] is True
        assert "Sources:\n" in case.prompt


def test_rag_answer_dataset_digest_is_deterministic() -> None:
    first = load_rag_answer_dataset(_DATASET_PATH)
    second = load_rag_answer_dataset(_DATASET_PATH)

    assert dataset_digest(first.cases) == dataset_digest(second.cases)


def test_rag_answer_scorer_accepts_exact_grounded_answer() -> None:
    case = load_rag_answer_dataset(_DATASET_PATH).cases[1]
    assessment = assess_rag_answer(case, _expected_output(1))

    assert assessment.score == Decimal("1")
    assert assessment.fact_score == Decimal("1")
    assert assessment.citation_score == Decimal("1")
    assert assessment.grounded_success is True
    assert assessment.issues == ()


def test_rag_answer_scorer_reports_missing_fact() -> None:
    case = load_rag_answer_dataset(_DATASET_PATH).cases[1]
    output = _expected_output(1)
    output["answer"] = "Atlas support is requested through the customer portal."

    assessment = assess_rag_answer(case, output)

    assert assessment.score == Decimal("0.75")
    assert assessment.fact_score == Decimal("0.5")
    assert assessment.citation_score == Decimal("1")
    assert RagAnswerIssue("missing_required_fact", "/answer/required_facts/0") in assessment.issues


def test_rag_answer_scorer_reports_missing_supporting_citation() -> None:
    case = load_rag_answer_dataset(_DATASET_PATH).cases[1]
    output = _expected_output(1)
    output["citations"] = ["atlas-warranty"]

    assessment = assess_rag_answer(case, output)

    assert assessment.fact_score == Decimal("1")
    assert assessment.citation_score == Decimal(2) / Decimal(3)
    assert assessment.score == (Decimal("1") + Decimal(2) / Decimal(3)) / Decimal("2")
    assert (
        RagAnswerIssue("missing_supporting_citation", "/citations/atlas-support")
        in assessment.issues
    )


def test_rag_answer_scorer_penalizes_known_irrelevant_citation() -> None:
    case = load_rag_answer_dataset(_DATASET_PATH).cases[0]
    output = _expected_output(0)
    output["citations"] = ["access-policy", "billing-faq"]

    assessment = assess_rag_answer(case, output)

    assert assessment.fact_score == Decimal("1")
    assert assessment.citation_score == Decimal(2) / Decimal(3)
    assert RagAnswerIssue("unexpected_citation", "/citations/billing-faq") in assessment.issues


def test_rag_answer_scorer_fails_closed_on_unknown_citation() -> None:
    case = load_rag_answer_dataset(_DATASET_PATH).cases[0]
    output = _expected_output(0)
    output["citations"] = ["invented-source"]

    assessment = assess_rag_answer(case, output)

    assert assessment.score == Decimal("0")
    assert assessment.fact_score == Decimal("0")
    assert assessment.citation_score == Decimal("0")
    assert assessment.issues == (RagAnswerIssue("unknown_citation", "/citations/0"),)


def test_rag_answer_scorer_fails_closed_on_forbidden_claim() -> None:
    case = load_rag_answer_dataset(_DATASET_PATH).cases[0]
    output = _expected_output(0)
    output["answer"] = "Temporary access expires after 48 hours with manager approval."

    assessment = assess_rag_answer(case, output)

    assert assessment.score == Decimal("0")
    assert assessment.issues == (RagAnswerIssue("unsupported_claim", "/answer/forbidden_claims/0"),)


def test_rag_answer_scorer_rejects_invalid_top_level_shape() -> None:
    case = load_rag_answer_dataset(_DATASET_PATH).cases[0]
    assessment = assess_rag_answer(case, {"answer": "x"})

    assert assessment.score == Decimal("0")
    assert assessment.issues == (RagAnswerIssue("invalid_output_shape", "/"),)


def test_rag_answer_contract_rejects_prompt_source_drift() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, prompt=case.prompt.replace("[access-policy]", "[other-source]"))

    with pytest.raises(ValueError, match="exactly materialize reviewed sources"):
        validate_rag_answer_case(drifted)


def test_rag_answer_contract_rejects_unknown_metadata() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    drifted = replace(case, metadata={**case.metadata, "provider_hint": "openai"})

    with pytest.raises(ValueError, match="unknown fields: provider_hint"):
        validate_rag_answer_case(drifted)


def test_rag_answer_contract_rejects_unknown_expected_source() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    expected = _expected_output(0)
    expected["citations"] = ["invented-source"]
    drifted = replace(case, expected=expected)

    with pytest.raises(ValueError, match="must reference reviewed sources"):
        validate_rag_answer_case(drifted)


def test_rag_answer_contract_rejects_reference_citations_without_fact_support() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    expected = _expected_output(0)
    expected["citations"] = ["billing-faq"]
    drifted = replace(case, expected=expected)

    with pytest.raises(ValueError, match="must support every required fact"):
        validate_rag_answer_case(drifted)


def test_rag_answer_contract_rejects_duplicate_source_ids() -> None:
    case = load_dataset(_DATASET_PATH).cases[0]
    sources = deepcopy(case.metadata["sources"])
    assert isinstance(sources, list)
    first = sources[0]
    second = sources[1]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    second["source_id"] = first["source_id"]
    drifted = replace(case, metadata={**case.metadata, "sources": sources})

    with pytest.raises(ValueError, match="source IDs must be unique"):
        validate_rag_answer_case(drifted)


def test_rag_answer_dataset_requires_exact_reviewed_case_count(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    payload["cases"] = cases[:-1]
    path = tmp_path / "rag-answer-incomplete.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="requires exactly six reviewed cases"):
        load_rag_answer_dataset(path)


def test_rag_answer_dataset_requires_both_reviewed_languages(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    for case in cases:
        assert isinstance(case, dict)
        metadata = case.get("metadata")
        assert isinstance(metadata, dict)
        if metadata.get("language") == "pt-BR":
            metadata["language"] = "en"
    path = tmp_path / "rag-answer-one-language.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="must cover exactly en and pt-BR"):
        load_rag_answer_dataset(path)


def test_rag_answer_dataset_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    cases = payload.get("cases")
    assert isinstance(cases, list)
    first = cases[0]
    second = cases[1]
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    second["case_id"] = first["case_id"]
    path = tmp_path / "rag-answer-duplicate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="case IDs must be unique"):
        load_rag_answer_dataset(path)


def test_rag_answer_scorer_is_registered() -> None:
    scorers = build_default_scorers()

    assert RAG_ANSWER_SCORER_ID in scorers
