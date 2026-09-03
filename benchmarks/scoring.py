"""Deterministic offline scorers for the initial Phase 10 benchmark workloads."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Protocol

from .contracts import BenchmarkCase, JsonValue


class DeterministicScorer(Protocol):
    """Score normalized provider output without another model or network dependency."""

    def __call__(self, case: BenchmarkCase, output: JsonValue) -> Decimal:
        """Return a deterministic quality score from 0 through 1."""
        ...


def _exact_json(case: BenchmarkCase, output: JsonValue) -> Decimal:
    return Decimal("1") if output == case.expected else Decimal("0")


def _contains_all(case: BenchmarkCase, output: JsonValue) -> Decimal:
    if not isinstance(case.expected, list):
        raise ValueError("contains_all scorer expects a list of required strings")
    required: list[str] = []
    for item in case.expected:
        if not isinstance(item, str):
            raise ValueError("contains_all scorer expects a list of required strings")
        required.append(item.casefold())
    if not isinstance(output, str):
        return Decimal("0")
    if not required:
        return Decimal("1")
    normalized = output.casefold()
    matches = sum(1 for item in required if item in normalized)
    return Decimal(matches) / Decimal(len(required))


def _mapping_fields(case: BenchmarkCase, output: JsonValue) -> Decimal:
    if not isinstance(case.expected, dict):
        raise ValueError("mapping_fields scorer expects an object")
    if not isinstance(output, dict):
        return Decimal("0")
    if not case.expected:
        return Decimal("1")
    matches = sum(1 for key, expected in case.expected.items() if output.get(key) == expected)
    return Decimal(matches) / Decimal(len(case.expected))


def _ordered_sequence(case: BenchmarkCase, output: JsonValue) -> Decimal:
    if not isinstance(case.expected, list):
        raise ValueError("ordered_sequence scorer expects a list")
    if not isinstance(output, list):
        return Decimal("0")
    if not case.expected:
        return Decimal("1")
    matches = sum(
        1
        for index, expected in enumerate(case.expected)
        if index < len(output) and output[index] == expected
    )
    return Decimal(matches) / Decimal(len(case.expected))


def build_default_scorers() -> Mapping[str, DeterministicScorer]:
    """Return the bounded credential-free scorer registry used by Phase 10 datasets."""
    scorers: dict[str, DeterministicScorer] = {
        "exact_json": _exact_json,
        "contains_all": _contains_all,
        "mapping_fields": _mapping_fields,
        "ordered_sequence": _ordered_sequence,
    }
    return scorers


def require_scorer(
    scorers: Mapping[str, DeterministicScorer], scorer_id: str
) -> DeterministicScorer:
    """Resolve a scorer by versioned dataset identifier and fail closed if unknown."""
    scorer = scorers.get(scorer_id)
    if scorer is None:
        raise ValueError(f"unknown deterministic scorer: {scorer_id}")
    return scorer


def ensure_supported_scorers(
    cases: Sequence[BenchmarkCase], scorers: Mapping[str, DeterministicScorer]
) -> None:
    """Validate all dataset scorer references before any provider call is attempted."""
    unknown = sorted({case.scorer for case in cases if case.scorer not in scorers})
    if unknown:
        raise ValueError(f"dataset references unknown deterministic scorers: {', '.join(unknown)}")
