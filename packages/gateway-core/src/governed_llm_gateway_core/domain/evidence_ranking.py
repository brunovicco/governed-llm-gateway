"""Phase 11 benchmark-derived ranking policy compilation.

The compiler consumes already-promoted runtime evidence. It never imports the
offline benchmark runner and never changes authorization or eligibility rules.
Only empirical quality and availability replace their Phase 5 static values;
reliability, latency score, cost score, and expected latency stay explicit static
inputs until a separately reviewed normalization policy exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from governed_llm_gateway_core.domain.ranking import (
    RankingPolicy,
    StaticDeploymentScore,
    WorkloadRankingPolicy,
)
from governed_llm_gateway_core.domain.ranking_evidence import PromotedRankingEvidence


class EvidenceRankingError(ValueError):
    """Raised when promoted evidence cannot safely compile into ranking inputs."""


class ScoreProvenanceMode(StrEnum):
    """Explicit source of the effective Phase 11 ranking scores."""

    BENCHMARK_HYBRID = "benchmark_hybrid"


@dataclass(frozen=True, slots=True)
class EvidenceDrivenRankingPolicy(RankingPolicy):
    """Ranking policy carrying exact benchmark-promotion provenance."""

    score_provenance_mode: ScoreProvenanceMode
    benchmark_snapshot_id: str
    promotion_evidence_id: str

    def __post_init__(self) -> None:
        """Require content-addressed benchmark and promotion identities."""
        if self.schema_version != "1.1":
            raise EvidenceRankingError(
                "evidence-driven ranking policy schema_version must be '1.1'"
            )
        _require_sha256(self.benchmark_snapshot_id, "benchmark_snapshot_id")
        _require_sha256(self.promotion_evidence_id, "promotion_evidence_id")

    def canonical_payload(self) -> dict[str, object]:
        """Extend the Phase 5 canonical payload with evidence provenance."""
        payload = super().canonical_payload()
        payload["score_provenance_mode"] = self.score_provenance_mode.value
        payload["benchmark_snapshot_id"] = self.benchmark_snapshot_id
        payload["promotion_evidence_id"] = self.promotion_evidence_id
        return payload


def compile_benchmark_hybrid_policy(
    base_policy: RankingPolicy,
    evidence: PromotedRankingEvidence,
    *,
    policy_version: str,
    score_snapshot_id: str,
    source_date: date,
) -> EvidenceDrivenRankingPolicy:
    """Overlay promoted quality/availability onto complete Phase 5 ranking inputs.

    Compilation is deliberately all-or-nothing for every deployment already
    present in the base policy. Missing evidence fails closed instead of silently
    falling back to a mixture that is not visible in provenance.
    """
    if base_policy.schema_version != "1.0":
        raise EvidenceRankingError(
            "benchmark hybrid compilation requires a Phase 5 schema 1.0 base"
        )
    _require_normalized(policy_version, "policy_version")
    _require_normalized(score_snapshot_id, "score_snapshot_id")
    if not base_policy.workloads:
        raise EvidenceRankingError("benchmark hybrid compilation requires configured workloads")

    workloads: list[WorkloadRankingPolicy] = []
    for workload in base_policy.workloads:
        deployments: list[StaticDeploymentScore] = []
        if not workload.deployments:
            raise EvidenceRankingError(
                f"workload {workload.workload!r} has no deployment score inputs to compile"
            )
        for static in workload.deployments:
            empirical = evidence.for_runtime(workload.workload, static.deployment_id)
            if empirical is None:
                raise EvidenceRankingError(
                    f"missing promoted evidence for {workload.workload!r}/{static.deployment_id!r}"
                )
            deployments.append(
                StaticDeploymentScore(
                    deployment_id=static.deployment_id,
                    quality=empirical.quality_score,
                    reliability=static.reliability,
                    latency=static.latency,
                    cost=static.cost,
                    availability=empirical.availability_rate,
                    expected_latency_ms=static.expected_latency_ms,
                )
            )
        workloads.append(
            WorkloadRankingPolicy(
                workload=workload.workload,
                weights=workload.weights,
                deployments=tuple(deployments),
            )
        )

    return EvidenceDrivenRankingPolicy(
        schema_version="1.1",
        policy_version=policy_version,
        score_snapshot_id=score_snapshot_id,
        source_date=source_date,
        workloads=tuple(workloads),
        score_provenance_mode=ScoreProvenanceMode.BENCHMARK_HYBRID,
        benchmark_snapshot_id=evidence.benchmark_snapshot_id,
        promotion_evidence_id=evidence.evidence_id,
    )


def benchmark_snapshot_id(policy: RankingPolicy) -> str | None:
    """Return benchmark provenance only for an explicitly evidence-driven policy."""
    if isinstance(policy, EvidenceDrivenRankingPolicy):
        return policy.benchmark_snapshot_id
    return None


def _require_normalized(value: str, field: str) -> None:
    if not value or value.strip() != value:
        raise EvidenceRankingError(f"{field} must be non-empty and normalized")


def _require_sha256(value: str, field: str) -> None:
    if not value.startswith("sha256:"):
        raise EvidenceRankingError(f"{field} must be a sha256: content identity")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64:
        raise EvidenceRankingError(f"{field} must contain a 64-character SHA-256 digest")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise EvidenceRankingError(f"{field} must contain a hexadecimal SHA-256 digest") from exc
