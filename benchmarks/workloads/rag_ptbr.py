"""Deterministic PT-BR RAG workload contract and scorer."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue

RAG_PTBR_CONTRACT_VERSION = "1.0"
RAG_PTBR_SCORER_ID = "rag_ptbr_v1"


def load_rag_ptbr_dataset(path: Path) -> BenchmarkDataset:
    """Load and validate a dataset containing only PT-BR grounded-answer cases."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(path)
    for case in dataset.cases:
        validate_rag_ptbr_case(case)
    return dataset


def validate_rag_ptbr_case(case: BenchmarkCase) -> None:
    """Fail closed when a PT-BR RAG case drifts from the v1 evidence contract."""
    if case.workload is not BenchmarkWorkload.RAG_PTBR:
        raise ValueError("rag ptbr dataset contains a different workload")
    if case.scorer != RAG_PTBR_SCORER_ID:
        raise ValueError("rag ptbr v1 requires its versioned deterministic scorer")
    if not isinstance(case.expected, list) or not case.expected:
        raise ValueError("rag ptbr expected facts must be a non-empty string list")
    if not all(isinstance(item, str) and item.strip() == item and item for item in case.expected):
        raise ValueError("rag ptbr expected facts must be normalized strings")

    metadata = case.metadata
    if metadata.get("contract_version") != RAG_PTBR_CONTRACT_VERSION:
        raise ValueError("rag ptbr contract_version must be 1.0")
    if metadata.get("language") != "pt-BR":
        raise ValueError("rag ptbr language must be pt-BR")
    if metadata.get("synthetic") is not True:
        raise ValueError("rag ptbr cases must be explicitly synthetic")

    context = metadata.get("context")
    if not isinstance(context, str) or not context or context.strip() != context:
        raise ValueError("rag ptbr context must be a normalized non-empty string")

    forbidden = metadata.get("forbidden_claims", [])
    if not isinstance(forbidden, list) or not all(
        isinstance(item, str) and item and item.strip() == item for item in forbidden
    ):
        raise ValueError("rag ptbr forbidden_claims must be normalized strings")


def score_rag_ptbr(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Score grounded fact coverage and fail quality on explicitly unsupported claims."""
    validate_rag_ptbr_case(case)
    if not isinstance(output, str):
        return Decimal("0")

    expected = case.expected
    if not isinstance(expected, list):
        raise AssertionError("validated rag ptbr expected facts must be a list")
    normalized = output.casefold()

    forbidden = case.metadata.get("forbidden_claims", [])
    if not isinstance(forbidden, list):
        raise AssertionError("validated rag ptbr forbidden_claims must be a list")
    if any(isinstance(item, str) and item.casefold() in normalized for item in forbidden):
        return Decimal("0")

    matches = sum(1 for item in expected if isinstance(item, str) and item.casefold() in normalized)
    return Decimal(matches) / Decimal(len(expected))
