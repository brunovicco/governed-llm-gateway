"""Deterministic PT-BR RAG v2 grounding and locale-quality contract."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

RAG_PTBR_V2_CONTRACT_VERSION = "2.0"
RAG_PTBR_V2_SCORER_ID = "rag_ptbr_v2"

_REQUIRED_METADATA_KEYS = frozenset(
    {
        "contract_version",
        "language",
        "synthetic",
        "context",
        "forbidden_claims",
        "pt_br_quality_rules",
    }
)
_REQUIRED_RULE_KEYS = frozenset({"preferred", "rejected"})


@dataclass(frozen=True, slots=True)
class PtBrQualityRule:
    """One reviewed PT-BR terminology rule for a synthetic case."""

    preferred: tuple[str, ...]
    rejected: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RagPtBrV2Assessment:
    """Separate grounding and bounded PT-BR locale-quality evidence."""

    score: Decimal
    grounding_score: Decimal
    pt_br_quality_score: Decimal
    unsupported_claim: bool


def load_rag_ptbr_v2_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate a dataset containing only reviewed PT-BR RAG v2 cases."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    if dataset.benchmark_version != "rag-ptbr-v2":
        raise ValueError("rag ptbr v2 dataset must use benchmark_version rag-ptbr-v2")
    case_ids: set[str] = set()
    for case in dataset.cases:
        if case.case_id in case_ids:
            raise ValueError("rag ptbr v2 case ids must be unique")
        case_ids.add(case.case_id)
        validate_rag_ptbr_v2_case(case)
    return dataset


def validate_rag_ptbr_v2_case(case: BenchmarkCase) -> None:
    """Fail closed when a PT-BR RAG v2 case drifts from its reviewed evidence contract."""
    if case.workload is not BenchmarkWorkload.RAG_PTBR:
        raise ValueError("rag ptbr v2 dataset contains a different workload")
    if case.scorer != RAG_PTBR_V2_SCORER_ID:
        raise ValueError("rag ptbr v2 requires its versioned deterministic scorer")

    facts = _validated_string_list(case.expected, "rag ptbr v2 expected facts")
    metadata = case.metadata
    if set(metadata) != _REQUIRED_METADATA_KEYS:
        raise ValueError("rag ptbr v2 metadata keys must match the reviewed contract exactly")
    if metadata.get("contract_version") != RAG_PTBR_V2_CONTRACT_VERSION:
        raise ValueError("rag ptbr v2 contract_version must be 2.0")
    if metadata.get("language") != "pt-BR":
        raise ValueError("rag ptbr v2 language must be pt-BR")
    if metadata.get("synthetic") is not True:
        raise ValueError("rag ptbr v2 cases must be explicitly synthetic")

    context_value = metadata.get("context")
    if not isinstance(context_value, str) or not _is_normalized_text(context_value):
        raise ValueError("rag ptbr v2 context must be normalized non-empty NFC text")
    if context_value not in case.prompt:
        raise ValueError("rag ptbr v2 prompt must contain the reviewed context verbatim")
    if "português do brasil" not in _normalize_for_match(case.prompt):
        raise ValueError("rag ptbr v2 prompt must explicitly request português do Brasil")

    context = _normalize_for_match(context_value)
    for fact in facts:
        if not _contains_phrase(context, fact):
            raise ValueError("rag ptbr v2 expected facts must be supported by the reviewed context")

    forbidden = _validated_string_list(
        metadata.get("forbidden_claims"),
        "rag ptbr v2 forbidden_claims",
        allow_empty=True,
    )
    for claim in forbidden:
        if _contains_phrase(context, claim):
            raise ValueError("rag ptbr v2 forbidden claims must not appear in the reviewed context")

    rules = _validated_quality_rules(metadata.get("pt_br_quality_rules"))
    if len(rules) < 2:
        raise ValueError("rag ptbr v2 requires at least two independent PT-BR quality rules")

    seen_terms: set[str] = set()
    for rule in rules:
        preferred = {_normalize_for_match(item) for item in rule.preferred}
        rejected = {_normalize_for_match(item) for item in rule.rejected}
        if preferred & rejected:
            raise ValueError("rag ptbr v2 preferred and rejected terms must be disjoint")
        if seen_terms & (preferred | rejected):
            raise ValueError("rag ptbr v2 quality terms must not be reused across rules")
        seen_terms.update(preferred | rejected)
        if not any(_contains_phrase(context, term) for term in rule.preferred):
            raise ValueError("rag ptbr v2 each quality rule must be supported by the reviewed context")
        if any(_contains_phrase(context, term) for term in rule.rejected):
            raise ValueError("rag ptbr v2 rejected locale terms must not appear in reviewed context")


def assess_rag_ptbr_v2(case: BenchmarkCase, output: JsonValue) -> RagPtBrV2Assessment:
    """Score grounded facts and reviewed PT-BR locale terminology independently."""
    validate_rag_ptbr_v2_case(case)
    if not isinstance(output, str):
        return RagPtBrV2Assessment(
            score=Decimal("0"),
            grounding_score=Decimal("0"),
            pt_br_quality_score=Decimal("0"),
            unsupported_claim=False,
        )

    normalized = _normalize_for_match(output)
    facts = _validated_string_list(case.expected, "rag ptbr v2 expected facts")
    forbidden = _validated_string_list(
        case.metadata.get("forbidden_claims"),
        "rag ptbr v2 forbidden_claims",
        allow_empty=True,
    )
    rules = _validated_quality_rules(case.metadata.get("pt_br_quality_rules"))

    unsupported = any(_contains_phrase(normalized, claim) for claim in forbidden)
    fact_matches = sum(1 for fact in facts if _contains_phrase(normalized, fact))
    grounding = Decimal("0") if unsupported else Decimal(fact_matches) / Decimal(len(facts))

    rule_matches = sum(1 for rule in rules if _quality_rule_matches(normalized, rule))
    pt_br_quality = Decimal(rule_matches) / Decimal(len(rules))
    score = Decimal("0") if unsupported else (grounding + pt_br_quality) / Decimal("2")

    return RagPtBrV2Assessment(
        score=score,
        grounding_score=grounding,
        pt_br_quality_score=pt_br_quality,
        unsupported_claim=unsupported,
    )


def score_rag_ptbr_v2(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Return the historical scalar-compatible score for a PT-BR RAG v2 case."""
    return assess_rag_ptbr_v2(case, output).score


def _validated_quality_rules(value: JsonValue | None) -> tuple[PtBrQualityRule, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("rag ptbr v2 pt_br_quality_rules must be a non-empty list")
    rules: list[PtBrQualityRule] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != _REQUIRED_RULE_KEYS:
            raise ValueError("rag ptbr v2 quality rules must contain only preferred and rejected")
        preferred = _validated_string_list(
            item.get("preferred"),
            "rag ptbr v2 preferred quality terms",
        )
        rejected = _validated_string_list(
            item.get("rejected"),
            "rag ptbr v2 rejected quality terms",
        )
        rules.append(PtBrQualityRule(preferred=preferred, rejected=rejected))
    return tuple(rules)


def _validated_string_list(
    value: JsonValue | None,
    label: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"{label} must be a {'normalized ' if allow_empty else 'non-empty normalized '}string list")
    items: list[str] = []
    normalized_items: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not _is_normalized_text(item):
            raise ValueError(f"{label} must contain normalized non-empty NFC strings")
        normalized = _normalize_for_match(item)
        if normalized in normalized_items:
            raise ValueError(f"{label} must not contain duplicates")
        normalized_items.add(normalized)
        items.append(item)
    return tuple(items)


def _quality_rule_matches(output: str, rule: PtBrQualityRule) -> bool:
    has_preferred = any(_contains_phrase(output, term) for term in rule.preferred)
    has_rejected = any(_contains_phrase(output, term) for term in rule.rejected)
    return has_preferred and not has_rejected


def _is_normalized_text(value: str) -> bool:
    return bool(value) and value.strip() == value and unicodedata.normalize("NFC", value) == value


def _normalize_for_match(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def _contains_phrase(normalized_text: str, phrase: str) -> bool:
    normalized_phrase = _normalize_for_match(phrase)
    pattern = rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)"
    return re.search(pattern, normalized_text, flags=re.UNICODE) is not None
