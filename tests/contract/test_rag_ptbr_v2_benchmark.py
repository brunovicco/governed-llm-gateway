from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks import BenchmarkQualityMetric, build_default_scorers, evaluate_scorer
from benchmarks.scoring import require_scorer
from benchmarks.workloads.rag_ptbr import load_rag_ptbr_dataset
from benchmarks.workloads.rag_ptbr_v2 import (
    RAG_PTBR_V2_SCORER_ID,
    assess_rag_ptbr_v2,
    load_rag_ptbr_v2_dataset,
    validate_rag_ptbr_v2_case,
)

_V1_DATASET = Path("benchmarks/datasets/rag-ptbr-v1.json")
_V2_DATASET = Path("benchmarks/datasets/rag-ptbr-v2.json")


def _perfect_output(case_index: int) -> str:
    dataset = load_rag_ptbr_v2_dataset(_V2_DATASET)
    case = dataset.cases[case_index]
    assert isinstance(case.expected, list)
    facts = [item for item in case.expected if isinstance(item, str)]

    rules_value = case.metadata.get("pt_br_quality_rules")
    assert isinstance(rules_value, list)
    preferred: list[str] = []
    for rule in rules_value:
        assert isinstance(rule, dict)
        terms = rule.get("preferred")
        assert isinstance(terms, list)
        first = terms[0]
        assert isinstance(first, str)
        preferred.append(first)
    return " ".join((*facts, *preferred))


def test_rag_ptbr_v2_dataset_is_public_versioned_and_fully_reviewed() -> None:
    dataset = load_rag_ptbr_v2_dataset(_V2_DATASET)

    assert dataset.schema_version == "1.0"
    assert dataset.benchmark_version == "rag-ptbr-v2"
    assert dataset.data_classification == "public"
    assert len(dataset.cases) == 6
    assert len({case.case_id for case in dataset.cases}) == 6

    for index, case in enumerate(dataset.cases):
        assert case.scorer == RAG_PTBR_V2_SCORER_ID
        assessment = assess_rag_ptbr_v2(case, _perfect_output(index))
        assert assessment.score == Decimal("1")
        assert assessment.grounding_score == Decimal("1")
        assert assessment.pt_br_quality_score == Decimal("1")
        assert assessment.unsupported_claim is False


def test_rag_ptbr_v2_registry_exposes_grounding_and_pt_br_quality_components() -> None:
    dataset = load_rag_ptbr_v2_dataset(_V2_DATASET)
    case = dataset.cases[0]
    scorer = require_scorer(build_default_scorers(), case.scorer)

    measurement = evaluate_scorer(scorer, case, _perfect_output(0))

    assert measurement.score == Decimal("1")
    assert measurement.metrics == {
        BenchmarkQualityMetric.GROUNDING: Decimal("1"),
        BenchmarkQualityMetric.PT_BR_QUALITY: Decimal("1"),
    }


def test_rag_ptbr_v1_remains_historical_without_language_quality_component() -> None:
    dataset = load_rag_ptbr_dataset(_V1_DATASET)
    case = dataset.cases[0]
    assert isinstance(case.expected, list)
    output = " ".join(item for item in case.expected if isinstance(item, str))
    scorer = require_scorer(build_default_scorers(), case.scorer)

    measurement = evaluate_scorer(scorer, case, output)

    assert measurement.score == Decimal("1")
    assert measurement.metrics == {}


def test_non_brazilian_locale_terms_do_not_change_grounding_but_reduce_pt_br_quality() -> None:
    case = load_rag_ptbr_v2_dataset(_V2_DATASET).cases[0]
    output = "90 dias equipe de segurança utilizador palavra-passe"

    assessment = assess_rag_ptbr_v2(case, output)

    assert assessment.grounding_score == Decimal("1")
    assert assessment.pt_br_quality_score == Decimal("0")
    assert assessment.score == Decimal("0.5")
    assert assessment.unsupported_claim is False


def test_unsupported_claim_fails_overall_quality_closed_without_erasing_locale_evidence() -> None:
    case = load_rag_ptbr_v2_dataset(_V2_DATASET).cases[0]
    output = "90 dias equipe de segurança usuário senha 180 dias"

    assessment = assess_rag_ptbr_v2(case, output)

    assert assessment.unsupported_claim is True
    assert assessment.grounding_score == Decimal("0")
    assert assessment.pt_br_quality_score == Decimal("1")
    assert assessment.score == Decimal("0")


def test_partial_locale_conformance_is_scored_separately_from_grounding() -> None:
    case = load_rag_ptbr_v2_dataset(_V2_DATASET).cases[0]
    output = "90 dias equipe de segurança usuário"

    assessment = assess_rag_ptbr_v2(case, output)

    assert assessment.grounding_score == Decimal("1")
    assert assessment.pt_br_quality_score == Decimal("0.5")
    assert assessment.score == Decimal("0.75")


def test_locale_matching_uses_phrase_boundaries_instead_of_substrings() -> None:
    case = load_rag_ptbr_v2_dataset(_V2_DATASET).cases[2]
    output = "10 minutos 20 minutos equipamento registro"

    assessment = assess_rag_ptbr_v2(case, output)

    assert assessment.grounding_score == Decimal("1")
    assert assessment.pt_br_quality_score == Decimal("0.5")
    assert assessment.score == Decimal("0.75")


def test_rag_ptbr_v2_rejects_unknown_metadata() -> None:
    case = load_rag_ptbr_v2_dataset(_V2_DATASET).cases[0]
    metadata = dict(case.metadata)
    metadata["unreviewed"] = True

    with pytest.raises(ValueError, match="metadata keys must match"):
        validate_rag_ptbr_v2_case(replace(case, metadata=metadata))


def test_rag_ptbr_v2_requires_expected_facts_to_be_grounded_in_context() -> None:
    case = load_rag_ptbr_v2_dataset(_V2_DATASET).cases[0]

    with pytest.raises(ValueError, match="expected facts must be supported"):
        validate_rag_ptbr_v2_case(replace(case, expected=["365 dias"]))


def test_rag_ptbr_v2_rejects_overlapping_locale_terms() -> None:
    case = load_rag_ptbr_v2_dataset(_V2_DATASET).cases[0]
    metadata = dict(case.metadata)
    rules_value = metadata["pt_br_quality_rules"]
    assert isinstance(rules_value, list)
    rules = list(rules_value)
    assert isinstance(rules[0], dict)
    rules[0] = {"preferred": ["usuário"], "rejected": ["usuário"]}
    metadata["pt_br_quality_rules"] = rules

    with pytest.raises(ValueError, match="preferred and rejected terms must be disjoint"):
        validate_rag_ptbr_v2_case(replace(case, metadata=metadata))


def test_rag_ptbr_v2_requires_explicit_brazilian_portuguese_instruction() -> None:
    case = load_rag_ptbr_v2_dataset(_V2_DATASET).cases[0]
    prompt = case.prompt.replace("português do Brasil", "português")

    with pytest.raises(ValueError, match="must explicitly request português do Brasil"):
        validate_rag_ptbr_v2_case(replace(case, prompt=prompt))
