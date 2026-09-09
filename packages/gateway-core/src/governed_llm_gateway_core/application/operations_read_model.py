"""Read-only operations projections over already-validated Gateway runtime state."""

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from governed_llm_gateway_core.domain.evidence_ranking import EvidenceDrivenRankingPolicy
from governed_llm_gateway_core.domain.model_registry import ModelRegistry
from governed_llm_gateway_core.domain.operational_evidence import OperationalEvidenceSnapshot
from governed_llm_gateway_core.domain.ranking import RankingPolicy
from governed_llm_gateway_core.domain.resilience import DeploymentHealthSnapshot

from .resilience import InMemoryHealthTracker


class OperationsHealthScope(StrEnum):
    """Completeness scope for runtime health presented by the operations model."""

    PROCESS_LOCAL = "process_local"


class OperationalEvidenceState(StrEnum):
    """Explicit availability state for reviewed operational evidence."""

    NOT_SUPPLIED = "not_supplied"
    AVAILABLE = "available"


@dataclass(frozen=True, slots=True)
class OperationsRegistrySummary:
    """Stable provenance for the active validated model registry."""

    schema_version: str
    catalog_version: str
    source_date: date
    digest: str
    deployment_count: int


@dataclass(frozen=True, slots=True)
class OperationsRankingSummary:
    """Stable provenance for the active deterministic ranking policy."""

    schema_version: str
    policy_version: str
    source_date: date
    digest: str
    score_snapshot_id: str
    score_provenance_mode: str | None
    benchmark_snapshot_id: str | None
    promotion_evidence_id: str | None
    manual_override_id: str | None


@dataclass(frozen=True, slots=True)
class OperationsDeploymentSummary:
    """Registry metadata plus process-local health for one deployment."""

    deployment_id: str
    provider: str
    model_id: str
    model_group: str
    api_family: str
    enabled: bool
    capabilities: tuple[str, ...]
    modalities: tuple[str, ...]
    context_tokens: int
    max_data_classification: str
    allowed_environments: tuple[str, ...]
    pricing_snapshot_version: str | None
    health: DeploymentHealthSnapshot


@dataclass(frozen=True, slots=True)
class OperationalEvidenceNotSupplied:
    """Represent evidence absence explicitly instead of fabricating zero measurements."""

    state: OperationalEvidenceState = field(
        default=OperationalEvidenceState.NOT_SUPPLIED,
        init=False,
    )


@dataclass(frozen=True, slots=True)
class OperationalEvidenceAvailable:
    """Bounded provenance for one verified reviewed operational-evidence snapshot."""

    evidence_id: str
    snapshot_version: str
    collector_id: str
    collector_version: str
    window_start: datetime
    window_end: datetime
    captured_at: datetime
    record_count: int
    state: OperationalEvidenceState = field(
        default=OperationalEvidenceState.AVAILABLE,
        init=False,
    )


OperationsOperationalEvidence = OperationalEvidenceNotSupplied | OperationalEvidenceAvailable


@dataclass(frozen=True, slots=True)
class OperationsSnapshot:
    """Deterministic read-only projection for later API and Console surfaces."""

    registry: OperationsRegistrySummary
    ranking: OperationsRankingSummary
    deployments: tuple[OperationsDeploymentSummary, ...]
    operational_evidence: OperationsOperationalEvidence
    health_scope: OperationsHealthScope = field(
        default=OperationsHealthScope.PROCESS_LOCAL,
        init=False,
    )


@runtime_checkable
class DeploymentHealthInspectionPort(Protocol):
    """Read deployment health without mutating the live resilience state."""

    def inspect(
        self,
        deployment_ids: tuple[str, ...],
    ) -> tuple[DeploymentHealthSnapshot, ...]:
        """Return health views in the same deterministic order as the requested IDs."""
        ...


class InMemoryHealthInspectionAdapter:
    """Inspect an in-memory tracker through an isolated replica of its current state."""

    def __init__(self, tracker: InMemoryHealthTracker) -> None:
        """Bind the process-local tracker without reading or mutating it."""
        if not isinstance(tracker, InMemoryHealthTracker):
            raise TypeError("tracker must use InMemoryHealthTracker")
        self._tracker = tracker

    def inspect(
        self,
        deployment_ids: tuple[str, ...],
    ) -> tuple[DeploymentHealthSnapshot, ...]:
        """Evaluate effective health on a replica so the live tracker remains untouched."""
        if not isinstance(deployment_ids, tuple):
            raise TypeError("deployment_ids must be a tuple")
        if len(deployment_ids) != len(set(deployment_ids)):
            raise ValueError("deployment_ids must not contain duplicates")
        for deployment_id in deployment_ids:
            if (
                not isinstance(deployment_id, str)
                or not deployment_id
                or deployment_id.strip() != deployment_id
            ):
                raise ValueError("deployment_ids must contain normalized non-empty strings")

        replica = deepcopy(self._tracker)
        snapshots = replica.snapshots(deployment_ids)
        return tuple(snapshots[deployment_id] for deployment_id in deployment_ids)


class OperationsReadModelService:
    """Project typed descriptive operations state without acquiring new runtime authority."""

    def __init__(
        self,
        *,
        registry: ModelRegistry,
        ranking_policy: RankingPolicy,
        health: DeploymentHealthInspectionPort,
    ) -> None:
        """Bind already-validated immutable sources and one read-only health port."""
        if not isinstance(registry, ModelRegistry):
            raise TypeError("registry must use ModelRegistry")
        if not isinstance(ranking_policy, RankingPolicy):
            raise TypeError("ranking_policy must use RankingPolicy")
        if not isinstance(health, DeploymentHealthInspectionPort):
            raise TypeError("health must implement DeploymentHealthInspectionPort")
        self._registry = registry
        self._ranking_policy = ranking_policy
        self._health = health

    def snapshot(
        self,
        *,
        operational_evidence: OperationalEvidenceSnapshot | None = None,
    ) -> OperationsSnapshot:
        """Build one deterministic snapshot without I/O, policy calls, or runtime mutation."""
        if operational_evidence is not None and not isinstance(
            operational_evidence,
            OperationalEvidenceSnapshot,
        ):
            raise TypeError("operational_evidence must use OperationalEvidenceSnapshot or None")

        ordered_deployments = tuple(
            sorted(self._registry.deployments, key=lambda item: item.deployment_id)
        )
        deployment_ids = tuple(item.deployment_id for item in ordered_deployments)
        health_snapshots = self._health.inspect(deployment_ids)
        if len(health_snapshots) != len(ordered_deployments):
            raise RuntimeError("health inspection returned an incomplete deployment set")

        deployments: list[OperationsDeploymentSummary] = []
        for deployment, health in zip(ordered_deployments, health_snapshots, strict=True):
            if health.deployment_id != deployment.deployment_id:
                raise RuntimeError("health inspection returned deployment identities out of order")
            deployments.append(
                OperationsDeploymentSummary(
                    deployment_id=deployment.deployment_id,
                    provider=deployment.provider,
                    model_id=deployment.model_id,
                    model_group=deployment.model_group,
                    api_family=deployment.api_family,
                    enabled=deployment.enabled,
                    capabilities=tuple(sorted(item.value for item in deployment.capabilities)),
                    modalities=tuple(sorted(item.value for item in deployment.modalities)),
                    context_tokens=deployment.context_tokens,
                    max_data_classification=deployment.max_data_classification.value,
                    allowed_environments=tuple(sorted(deployment.allowed_environments)),
                    pricing_snapshot_version=(
                        None if deployment.pricing is None else deployment.pricing.snapshot_version
                    ),
                    health=health,
                )
            )

        return OperationsSnapshot(
            registry=_registry_summary(self._registry),
            ranking=_ranking_summary(self._ranking_policy),
            deployments=tuple(deployments),
            operational_evidence=_operational_evidence_summary(operational_evidence),
        )


def _registry_summary(registry: ModelRegistry) -> OperationsRegistrySummary:
    return OperationsRegistrySummary(
        schema_version=registry.schema_version,
        catalog_version=registry.catalog_version,
        source_date=registry.source_date,
        digest=registry.digest,
        deployment_count=len(registry.deployments),
    )


def _ranking_summary(policy: RankingPolicy) -> OperationsRankingSummary:
    if isinstance(policy, EvidenceDrivenRankingPolicy):
        score_provenance_mode: str | None = policy.score_provenance_mode.value
        benchmark_snapshot_id = policy.benchmark_snapshot_id
        promotion_evidence_id = policy.promotion_evidence_id
        manual_override_id = policy.manual_override_id
    else:
        score_provenance_mode = None
        benchmark_snapshot_id = None
        promotion_evidence_id = None
        manual_override_id = None

    return OperationsRankingSummary(
        schema_version=policy.schema_version,
        policy_version=policy.policy_version,
        source_date=policy.source_date,
        digest=policy.digest,
        score_snapshot_id=policy.score_snapshot_id,
        score_provenance_mode=score_provenance_mode,
        benchmark_snapshot_id=benchmark_snapshot_id,
        promotion_evidence_id=promotion_evidence_id,
        manual_override_id=manual_override_id,
    )


def _operational_evidence_summary(
    evidence: OperationalEvidenceSnapshot | None,
) -> OperationsOperationalEvidence:
    if evidence is None:
        return OperationalEvidenceNotSupplied()
    return OperationalEvidenceAvailable(
        evidence_id=evidence.evidence_id,
        snapshot_version=evidence.snapshot_version,
        collector_id=evidence.collector_id,
        collector_version=evidence.collector_version,
        window_start=evidence.window_start,
        window_end=evidence.window_end,
        captured_at=evidence.captured_at,
        record_count=len(evidence.records),
    )
