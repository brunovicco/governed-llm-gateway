"""Metadata-only governance runtime evidence and delivery boundary."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from governed_llm_gateway_core.domain.governance import (
    GovernanceDenialReason,
    VerifiedGovernanceAuthorization,
)


class GovernanceEvidenceOutcome(StrEnum):
    """Stable governance evidence outcomes."""

    DENIED = "denied"
    EXECUTION_SUCCEEDED = "execution_succeeded"
    EXECUTION_FAILED = "execution_failed"


class GovernanceEvidenceDeliveryMode(StrEnum):
    """Deployment-owned remote delivery policy."""

    BEST_EFFORT = "best_effort"
    REQUIRED = "required"


@dataclass(frozen=True, slots=True)
class GovernanceRuntimeEvidence:
    """Minimized evidence sufficient to correlate governance and gateway execution."""

    gateway_request_id: UUID
    occurred_at: datetime
    service_version: str
    workload: str
    outcome: GovernanceEvidenceOutcome
    authorization_id: UUID | None = None
    authorization_signing_digest: str | None = None
    authorization_key_id: str | None = None
    policy_router_decision_id: str | None = None
    routing_decision_id: str | None = None
    model_group: str | None = None
    provider: str | None = None
    deployment_id: str | None = None
    denial_reason: GovernanceDenialReason | None = None
    provider_error_code: str | None = None
    attempt_count: int | None = None

    def __post_init__(self) -> None:
        """Reject ambiguous or content-bearing evidence shapes."""
        if self.gateway_request_id.int == 0:
            raise ValueError("gateway_request_id must not be nil")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("governance evidence timestamp must be timezone-aware")
        for name, value in (
            ("service_version", self.service_version),
            ("workload", self.workload),
        ):
            if not value or value.strip() != value:
                raise ValueError(f"{name} must be a normalized non-empty string")
        for name, value in (
            ("authorization_signing_digest", self.authorization_signing_digest),
            ("authorization_key_id", self.authorization_key_id),
            ("policy_router_decision_id", self.policy_router_decision_id),
            ("routing_decision_id", self.routing_decision_id),
            ("model_group", self.model_group),
            ("provider", self.provider),
            ("deployment_id", self.deployment_id),
            ("provider_error_code", self.provider_error_code),
        ):
            if value is not None and (not value or value.strip() != value):
                raise ValueError(f"{name} must be normalized when present")
        if self.attempt_count is not None and self.attempt_count < 0:
            raise ValueError("attempt_count must be non-negative when present")

        if self.outcome is GovernanceEvidenceOutcome.DENIED:
            if self.denial_reason is None:
                raise ValueError("denial evidence requires a stable denial reason")
            if self.provider is not None or self.deployment_id is not None:
                raise ValueError("authorization denial evidence cannot claim provider execution")
            if self.provider_error_code is not None or self.attempt_count is not None:
                raise ValueError("authorization denial evidence cannot contain provider attempt data")
            return

        if self.denial_reason is not None:
            raise ValueError("execution evidence must not contain a governance denial reason")
        if self.authorization_id is None:
            raise ValueError("execution evidence must correlate to governance authorization")
        if self.policy_router_decision_id is None or self.routing_decision_id is None:
            raise ValueError("execution evidence must correlate PDP and routing decisions")
        if self.model_group is None or self.provider is None or self.deployment_id is None:
            raise ValueError("execution evidence requires model group, provider, and deployment")
        if self.attempt_count is None or self.attempt_count <= 0:
            raise ValueError("execution evidence requires a positive attempt count")
        if (
            self.outcome is GovernanceEvidenceOutcome.EXECUTION_SUCCEEDED
            and self.provider_error_code is not None
        ):
            raise ValueError("successful execution evidence cannot contain a provider error")


class GovernanceEventSink(Protocol):
    """Asynchronous external evidence sink with no authorization authority."""

    async def emit(self, evidence: GovernanceRuntimeEvidence) -> None:
        """Deliver one normalized evidence record."""
        ...


class GovernanceEvidenceDeliveryError(RuntimeError):
    """Raised only when deployment policy requires successful remote evidence delivery."""


class GovernanceEvidenceJournal:
    """Record locally before optional external evidence delivery."""

    def __init__(
        self,
        *,
        sink: GovernanceEventSink | None = None,
        delivery_mode: GovernanceEvidenceDeliveryMode = GovernanceEvidenceDeliveryMode.BEST_EFFORT,
    ) -> None:
        self._sink = sink
        self._delivery_mode = delivery_mode
        self._records: list[GovernanceRuntimeEvidence] = []

    @property
    def records(self) -> tuple[GovernanceRuntimeEvidence, ...]:
        """Return immutable local evidence in append order."""
        return tuple(self._records)

    async def record(self, evidence: GovernanceRuntimeEvidence) -> None:
        """Persist locally first, then attempt remote delivery under explicit policy."""
        self._records.append(evidence)
        if self._sink is None:
            return
        try:
            await self._sink.emit(evidence)
        except Exception as exc:
            if self._delivery_mode is GovernanceEvidenceDeliveryMode.REQUIRED:
                raise GovernanceEvidenceDeliveryError(
                    "required governance evidence delivery failed"
                ) from exc


def build_governance_denial_evidence(
    authorization: VerifiedGovernanceAuthorization | None,
    *,
    gateway_request_id: UUID,
    workload: str,
    reason: GovernanceDenialReason,
    occurred_at: datetime,
    service_version: str,
    policy_router_decision_id: str | None = None,
    routing_decision_id: str | None = None,
    model_group: str | None = None,
) -> GovernanceRuntimeEvidence:
    """Build a metadata-only denial record from trusted verified facts only."""
    return GovernanceRuntimeEvidence(
        gateway_request_id=gateway_request_id,
        occurred_at=occurred_at,
        service_version=service_version,
        workload=workload,
        outcome=GovernanceEvidenceOutcome.DENIED,
        authorization_id=authorization.authorization_id if authorization is not None else None,
        authorization_signing_digest=(
            authorization.signing_digest if authorization is not None else None
        ),
        authorization_key_id=authorization.key_id if authorization is not None else None,
        policy_router_decision_id=policy_router_decision_id,
        routing_decision_id=routing_decision_id,
        model_group=model_group,
        denial_reason=reason,
    )


def build_governance_execution_evidence(
    authorization: VerifiedGovernanceAuthorization,
    *,
    gateway_request_id: UUID,
    workload: str,
    occurred_at: datetime,
    service_version: str,
    policy_router_decision_id: str,
    routing_decision_id: str,
    model_group: str,
    provider: str,
    deployment_id: str,
    succeeded: bool,
    attempt_count: int,
    provider_error_code: str | None = None,
) -> GovernanceRuntimeEvidence:
    """Build execution evidence correlated to the exact verified authorization."""
    outcome = (
        GovernanceEvidenceOutcome.EXECUTION_SUCCEEDED
        if succeeded
        else GovernanceEvidenceOutcome.EXECUTION_FAILED
    )
    return GovernanceRuntimeEvidence(
        gateway_request_id=gateway_request_id,
        occurred_at=occurred_at,
        service_version=service_version,
        workload=workload,
        outcome=outcome,
        authorization_id=authorization.authorization_id,
        authorization_signing_digest=authorization.signing_digest,
        authorization_key_id=authorization.key_id,
        policy_router_decision_id=policy_router_decision_id,
        routing_decision_id=routing_decision_id,
        model_group=model_group,
        provider=provider,
        deployment_id=deployment_id,
        provider_error_code=provider_error_code,
        attempt_count=attempt_count,
    )
