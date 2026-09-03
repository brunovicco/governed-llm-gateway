"""Explicit Phase 11 manual override and rollback contracts.

Overrides are content-addressed, operator-approved configuration. They may replace
only quality and availability values already present in an evidence-driven policy.
Rollback selects a previously approved immutable ranking artifact by identity.
Neither operation changes PDP authorization or gateway eligibility.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from governed_llm_gateway_core.domain.evidence_ranking import (
    EvidenceDrivenRankingPolicy,
    ScoreProvenanceMode,
    benchmark_snapshot_id,
    manual_override_id,
)
from governed_llm_gateway_core.domain.ranking import (
    RankingPolicy,
    StaticDeploymentScore,
    WorkloadRankingPolicy,
)


class RankingOverrideError(ValueError):
    """Raised when an override or rollback selection is unsafe or ambiguous."""


@dataclass(frozen=True, slots=True)
class ManualScoreOverride:
    """Operator-supplied replacement for promoted empirical score inputs."""

    workload: str
    deployment_id: str
    quality: Decimal | None = None
    availability: Decimal | None = None

    def __post_init__(self) -> None:
        """Require an exact existing target and at least one bounded replacement."""
        _require_normalized(self.workload, "workload")
        _require_normalized(self.deployment_id, "deployment_id")
        if self.quality is None and self.availability is None:
            raise RankingOverrideError("manual score override must replace at least one score")
        if self.quality is not None:
            _require_unit_decimal(self.quality, "quality")
        if self.availability is not None:
            _require_unit_decimal(self.availability, "availability")


@dataclass(frozen=True, slots=True)
class ManualOverrideBundle:
    """Versioned, attributable, content-addressed set of manual score overrides."""

    schema_version: str
    override_version: str
    approval_date: date
    approved_by: str
    reason: str
    overrides: tuple[ManualScoreOverride, ...]

    def __post_init__(self) -> None:
        """Reject empty bundles and duplicate workload/deployment targets."""
        if self.schema_version != "1.0":
            raise RankingOverrideError("manual override schema_version must be '1.0'")
        _require_normalized(self.override_version, "override_version")
        _require_normalized(self.approved_by, "approved_by")
        _require_normalized(self.reason, "reason")
        if not self.overrides:
            raise RankingOverrideError("manual override bundle must contain at least one override")
        keys = [(item.workload, item.deployment_id) for item in self.overrides]
        if len(set(keys)) != len(keys):
            raise RankingOverrideError("manual override bundle contains duplicate targets")

    @property
    def override_id(self) -> str:
        """Return the SHA-256 identity of the complete approved override bundle."""
        canonical = json.dumps(
            self.canonical_payload(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def canonical_payload(self) -> dict[str, object]:
        """Return deterministic content used for override identity."""
        return {
            "schema_version": self.schema_version,
            "override_version": self.override_version,
            "approval_date": self.approval_date.isoformat(),
            "approved_by": self.approved_by,
            "reason": self.reason,
            "overrides": [
                {
                    "workload": item.workload,
                    "deployment_id": item.deployment_id,
                    "quality": _decimal_text(item.quality),
                    "availability": _decimal_text(item.availability),
                }
                for item in sorted(
                    self.overrides,
                    key=lambda value: (value.workload, value.deployment_id),
                )
            ],
        }


@dataclass(frozen=True, slots=True)
class ApprovedRankingArtifact:
    """Operator-approved immutable ranking policy eligible for explicit rollback."""

    policy: RankingPolicy
    approval_version: str
    approval_date: date
    approved_by: str

    def __post_init__(self) -> None:
        """Require attributable approval metadata."""
        _require_normalized(self.approval_version, "approval_version")
        _require_normalized(self.approved_by, "approved_by")

    @property
    def artifact_id(self) -> str:
        """Bind approval metadata to the exact immutable ranking policy identity."""
        payload = {
            "approval_version": self.approval_version,
            "approval_date": self.approval_date.isoformat(),
            "approved_by": self.approved_by,
            "ranking_policy_digest": self.policy.digest,
            "benchmark_snapshot_id": benchmark_snapshot_id(self.policy),
            "manual_override_id": manual_override_id(self.policy),
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def apply_manual_override(
    policy: EvidenceDrivenRankingPolicy,
    bundle: ManualOverrideBundle,
    *,
    policy_version: str,
    score_snapshot_id: str,
    source_date: date,
) -> EvidenceDrivenRankingPolicy:
    """Apply one explicit override bundle without changing the policy candidate universe."""
    if policy.score_provenance_mode is not ScoreProvenanceMode.BENCHMARK_HYBRID:
        raise RankingOverrideError(
            "manual override must be applied to the approved benchmark-hybrid baseline"
        )
    _require_normalized(policy_version, "policy_version")
    _require_normalized(score_snapshot_id, "score_snapshot_id")

    override_by_target = {(item.workload, item.deployment_id): item for item in bundle.overrides}
    known_targets = {
        (workload.workload, score.deployment_id)
        for workload in policy.workloads
        for score in workload.deployments
    }
    unknown = sorted(set(override_by_target) - known_targets)
    if unknown:
        unknown_workload, unknown_deployment_id = unknown[0]
        raise RankingOverrideError(
            f"manual override target does not exist: {unknown_workload!r}/{unknown_deployment_id!r}"
        )

    workloads: list[WorkloadRankingPolicy] = []
    for workload in policy.workloads:
        deployments: list[StaticDeploymentScore] = []
        for score in workload.deployments:
            override = override_by_target.get((workload.workload, score.deployment_id))
            deployments.append(_apply_score_override(score, override))
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
        score_provenance_mode=ScoreProvenanceMode.MANUAL_OVERRIDE,
        benchmark_snapshot_id=policy.benchmark_snapshot_id,
        promotion_evidence_id=policy.promotion_evidence_id,
        manual_override_id=bundle.override_id,
    )


def select_rollback_policy(
    approved_artifacts: tuple[ApprovedRankingArtifact, ...],
    *,
    target_artifact_id: str,
) -> RankingPolicy:
    """Select one previously approved immutable policy by exact artifact identity."""
    _require_sha256(target_artifact_id, "target_artifact_id")
    matches = [item for item in approved_artifacts if item.artifact_id == target_artifact_id]
    if len(matches) != 1:
        raise RankingOverrideError("rollback target must identify exactly one approved artifact")
    return matches[0].policy


def _apply_score_override(
    score: StaticDeploymentScore,
    override: ManualScoreOverride | None,
) -> StaticDeploymentScore:
    if override is None:
        return score
    return StaticDeploymentScore(
        deployment_id=score.deployment_id,
        quality=override.quality if override.quality is not None else score.quality,
        reliability=score.reliability,
        latency=score.latency,
        cost=score.cost,
        availability=(
            override.availability if override.availability is not None else score.availability
        ),
        expected_latency_ms=score.expected_latency_ms,
    )


def _require_normalized(value: str, field: str) -> None:
    if not value or value.strip() != value:
        raise RankingOverrideError(f"{field} must be non-empty and normalized")


def _require_unit_decimal(value: Decimal, field: str) -> None:
    if not value.is_finite() or value < 0 or value > 1:
        raise RankingOverrideError(f"{field} must be between 0 and 1")


def _require_sha256(value: str, field: str) -> None:
    if not value.startswith("sha256:"):
        raise RankingOverrideError(f"{field} must be a sha256: content identity")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64:
        raise RankingOverrideError(f"{field} must contain a 64-character SHA-256 digest")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise RankingOverrideError(f"{field} must contain a hexadecimal SHA-256 digest") from exc


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")
