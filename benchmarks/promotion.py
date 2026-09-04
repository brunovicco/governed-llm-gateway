"""Deterministic Phase 11 promotion of approved benchmark evidence.

This module remains in the repository-level offline ``benchmarks`` source root. It
maps immutable Phase 10 scorecards to explicit deployment/workload evidence, but
does not assign runtime ranking weights or mutate active configuration.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

from .contracts import BenchmarkSnapshot, BenchmarkWorkload, Scorecard

_PROMOTION_SCHEMA_VERSION: Final = "1.0"


class PromotionError(ValueError):
    """Raised when benchmark evidence cannot be promoted safely."""


@dataclass(frozen=True, slots=True)
class PromotionMapping:
    """Explicit operator-approved mapping from benchmark target/workload to runtime identity."""

    target_id: str
    benchmark_workload: BenchmarkWorkload
    deployment_id: str
    runtime_workload: str

    def __post_init__(self) -> None:
        """Require explicit normalized identities and dotted runtime workload names."""
        for name in ("target_id", "deployment_id", "runtime_workload"):
            value = getattr(self, name)
            if not value or value.strip() != value:
                raise PromotionError(f"{name} must be non-empty and normalized")
        if "." not in self.runtime_workload:
            raise PromotionError("runtime_workload must be a dotted workload identifier")


@dataclass(frozen=True, slots=True)
class PromotedEvidenceRecord:
    """One immutable benchmark-derived evidence record for a runtime deployment/workload."""

    target_id: str
    deployment_id: str
    benchmark_workload: BenchmarkWorkload
    runtime_workload: str
    total_cases: int
    completed_calls: int
    quality_score: Decimal
    availability_rate: Decimal
    latency_p95_ms: int | None
    cost_per_completed_call_usd: Decimal | None
    fallback_frequency: Decimal


@dataclass(frozen=True, slots=True)
class PromotedBenchmarkEvidence:
    """Content-addressed approved evidence artifact with no direct runtime authority by itself."""

    schema_version: str
    promotion_version: str
    approval_date: date
    approved_by: str
    benchmark_snapshot_id: str
    benchmark_version: str
    dataset_digest: str
    evidence_id: str
    records: tuple[PromotedEvidenceRecord, ...]


def promote_snapshot(
    snapshot: BenchmarkSnapshot,
    *,
    promotion_version: str,
    approval_date: date,
    approved_by: str,
    mappings: tuple[PromotionMapping, ...],
) -> PromotedBenchmarkEvidence:
    """Compile an approved immutable snapshot into deterministic mapped evidence.

    Promotion fails closed when mappings are missing/duplicated or when a mapped
    scorecard has no completed quality evidence. Provider failures therefore do
    not silently become quality score zeroes.
    """
    _require_normalized(promotion_version, "promotion_version")
    _require_normalized(approved_by, "approved_by")
    if not snapshot.snapshot_id.startswith("sha256:"):
        raise PromotionError("benchmark snapshot_id must be content-addressed with sha256:")
    if not snapshot.dataset_digest.startswith("sha256:"):
        raise PromotionError("benchmark dataset_digest must be content-addressed with sha256:")
    if not mappings:
        raise PromotionError("promotion requires at least one explicit target/workload mapping")

    scorecards = {(card.target_id, card.workload): card for card in snapshot.scorecards}
    seen_source: set[tuple[str, BenchmarkWorkload]] = set()
    seen_runtime: set[tuple[str, str]] = set()
    records: list[PromotedEvidenceRecord] = []

    for mapping in sorted(
        mappings,
        key=lambda item: (
            item.runtime_workload,
            item.deployment_id,
            item.target_id,
            item.benchmark_workload.value,
        ),
    ):
        source_key = (mapping.target_id, mapping.benchmark_workload)
        runtime_key = (mapping.runtime_workload, mapping.deployment_id)
        if source_key in seen_source:
            raise PromotionError("duplicate benchmark target/workload promotion mapping")
        if runtime_key in seen_runtime:
            raise PromotionError("duplicate runtime workload/deployment promotion mapping")
        seen_source.add(source_key)
        seen_runtime.add(runtime_key)

        scorecard = scorecards.get(source_key)
        if scorecard is None:
            raise PromotionError(
                "promoted target/workload mapping has no scorecard in benchmark snapshot"
            )
        records.append(_promote_scorecard(mapping, scorecard))

    base_payload = {
        "schema_version": _PROMOTION_SCHEMA_VERSION,
        "promotion_version": promotion_version,
        "approval_date": approval_date.isoformat(),
        "approved_by": approved_by,
        "benchmark_snapshot_id": snapshot.snapshot_id,
        "benchmark_version": snapshot.benchmark_version,
        "dataset_digest": snapshot.dataset_digest,
        "records": [_record_payload(record) for record in records],
    }
    evidence_id = _sha256(base_payload)
    return PromotedBenchmarkEvidence(
        schema_version=_PROMOTION_SCHEMA_VERSION,
        promotion_version=promotion_version,
        approval_date=approval_date,
        approved_by=approved_by,
        benchmark_snapshot_id=snapshot.snapshot_id,
        benchmark_version=snapshot.benchmark_version,
        dataset_digest=snapshot.dataset_digest,
        evidence_id=evidence_id,
        records=tuple(records),
    )


def canonical_promoted_evidence_json(evidence: PromotedBenchmarkEvidence) -> str:
    """Serialize promoted evidence as stable reviewable JSON."""
    payload = {
        "schema_version": evidence.schema_version,
        "promotion_version": evidence.promotion_version,
        "approval_date": evidence.approval_date.isoformat(),
        "approved_by": evidence.approved_by,
        "benchmark_snapshot_id": evidence.benchmark_snapshot_id,
        "benchmark_version": evidence.benchmark_version,
        "dataset_digest": evidence.dataset_digest,
        "evidence_id": evidence.evidence_id,
        "records": [_record_payload(record) for record in evidence.records],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _promote_scorecard(
    mapping: PromotionMapping,
    scorecard: Scorecard,
) -> PromotedEvidenceRecord:
    if scorecard.completed_calls <= 0:
        raise PromotionError("benchmark quality promotion requires at least one completed call")
    if scorecard.mean_quality_score is None:
        raise PromotionError("benchmark quality promotion requires mean_quality_score")
    if scorecard.total_cases <= 0 or scorecard.completed_calls > scorecard.total_cases:
        raise PromotionError("benchmark scorecard case counts are inconsistent")
    if not Decimal("0") <= scorecard.mean_quality_score <= Decimal("1"):
        raise PromotionError("mean_quality_score must be between 0 and 1")
    if not Decimal("0") <= scorecard.availability_rate <= Decimal("1"):
        raise PromotionError("availability_rate must be between 0 and 1")
    if not Decimal("0") <= scorecard.fallback_frequency <= Decimal("1"):
        raise PromotionError("fallback_frequency must be between 0 and 1")
    if scorecard.latency_p95_ms is not None and scorecard.latency_p95_ms < 0:
        raise PromotionError("latency_p95_ms must be non-negative")
    if scorecard.total_cost_usd < 0:
        raise PromotionError("total_cost_usd must be non-negative")

    cost_per_call = scorecard.total_cost_usd / Decimal(scorecard.completed_calls)
    return PromotedEvidenceRecord(
        target_id=mapping.target_id,
        deployment_id=mapping.deployment_id,
        benchmark_workload=mapping.benchmark_workload,
        runtime_workload=mapping.runtime_workload,
        total_cases=scorecard.total_cases,
        completed_calls=scorecard.completed_calls,
        quality_score=scorecard.mean_quality_score,
        availability_rate=scorecard.availability_rate,
        latency_p95_ms=scorecard.latency_p95_ms,
        cost_per_completed_call_usd=cost_per_call,
        fallback_frequency=scorecard.fallback_frequency,
    )


def _record_payload(record: PromotedEvidenceRecord) -> dict[str, object]:
    return {
        "target_id": record.target_id,
        "deployment_id": record.deployment_id,
        "benchmark_workload": record.benchmark_workload.value,
        "runtime_workload": record.runtime_workload,
        "total_cases": record.total_cases,
        "completed_calls": record.completed_calls,
        "quality_score": _decimal(record.quality_score),
        "availability_rate": _decimal(record.availability_rate),
        "latency_p95_ms": record.latency_p95_ms,
        "cost_per_completed_call_usd": _decimal(record.cost_per_completed_call_usd),
        "fallback_frequency": _decimal(record.fallback_frequency),
    }


def _require_normalized(value: str, field: str) -> None:
    if not value or value.strip() != value:
        raise PromotionError(f"{field} must be non-empty and normalized")


def _decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _sha256(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
