"""Fail-closed regressions for the PT-BR RAG v1 benchmark contract."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from benchmarks.contracts import BenchmarkCase, BenchmarkWorkload
from benchmarks.workloads.rag_ptbr import load_rag_ptbr_dataset, validate_rag_ptbr_case

_DATASET = Path("benchmarks/datasets/rag-ptbr-v1.json")


def _first_case() -> BenchmarkCase:
    return load_rag_ptbr_dataset(_DATASET).cases[0]


def test_rejects_wrong_workload() -> None:
    case = replace(_first_case(), workload=BenchmarkWorkload.CODE_GENERATION)

    with pytest.raises(ValueError, match="different workload"):
        validate_rag_ptbr_case(case)


def test_rejects_wrong_scorer() -> None:
    case = replace(_first_case(), scorer="contains_all")

    with pytest.raises(ValueError, match="versioned deterministic scorer"):
        validate_rag_ptbr_case(case)


def test_rejects_non_ptbr_language() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["language"] = "en"
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="language must be pt-BR"):
        validate_rag_ptbr_case(case)


def test_rejects_non_synthetic_case() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["synthetic"] = False
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="explicitly synthetic"):
        validate_rag_ptbr_case(case)


def test_rejects_empty_context() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["context"] = ""
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="context must be"):
        validate_rag_ptbr_case(case)


def test_rejects_malformed_forbidden_claims() -> None:
    original = _first_case()
    metadata = dict(original.metadata)
    metadata["forbidden_claims"] = [1]
    case = replace(original, metadata=metadata)

    with pytest.raises(ValueError, match="forbidden_claims"):
        validate_rag_ptbr_case(case)
