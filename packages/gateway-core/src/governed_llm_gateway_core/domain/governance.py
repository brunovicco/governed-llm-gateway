"""Verified governance authorization facts and fail-closed scope enforcement."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from governed_llm_gateway_contracts import DataClassification, RiskLevel

from .authorization import PolicyAuthorization, enforce_allowed_subset
from .model_registry import ModelDeployment


class GovernanceDenialReason(StrEnum):
    """Stable fail-closed reason codes for verified governance authorization denials."""

    INVALID_CLOCK = "invalid_clock"
    INVALID_AUDIENCE_CONFIGURATION = "invalid_audience_configuration"
    AUDIENCE_MISMATCH = "audience_mismatch"
    NOT_ACTIVE = "not_active"
    EXPIRED = "expired"
    WORKLOAD_MISMATCH = "workload_mismatch"
    RISK_LEVEL_MISMATCH = "risk_level_mismatch"
    DATA_CLASSIFICATION_MISMATCH = "data_classification_mismatch"
    CONTEXT_TOKENS_MISMATCH = "context_tokens_mismatch"
    OUTPUT_TOKENS_MISMATCH = "output_tokens_mismatch"
    STRUCTURED_OUTPUT_MISMATCH = "structured_output_mismatch"
    LATENCY_CEILING_MISMATCH = "latency_ceiling_mismatch"
    COST_CEILING_MISMATCH = "cost_ceiling_mismatch"
    NO_MODEL_GROUP_INTERSECTION = "no_model_group_intersection"
    SELECTED_MODEL_GROUP_MISMATCH = "selected_model_group_mismatch"


class GovernanceAuthorizationViolation(ValueError):
    """Raised when verified governance scope does not authorize the runtime request."""

    def __init__(self, message: str, *, reason: GovernanceDenialReason) -> None:
        """Retain a stable denial reason without exposing sensitive request content."""
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class GovernancePolicyProvenance:
    """Governance policy/control artifacts covered by the signed authorization."""

    policy_id: str
    policy_version: str
    policy_digest: str
    control_catalog_id: str
    control_catalog_version: str
    control_catalog_digest: str


@dataclass(frozen=True, slots=True)
class GovernanceRequestBinding:
    """Request facts covered by the upstream signed runtime authorization."""

    workflow_id: str
    task_id: str
    workload: str
    context_tokens_estimated: int
    max_output_tokens_estimated: int
    structured_output_required: bool
    max_latency_ms: int
    max_cost_usd_micros: int


@dataclass(frozen=True, slots=True)
class VerifiedGovernanceAuthorization:
    """Immutable facts produced only after external signature/contract verification."""

    authorization_id: UUID
    issuer: str
    audience: tuple[str, ...]
    key_id: str
    signing_digest: str
    not_before: datetime
    expires_at: datetime
    initiative_id: UUID
    ai_system_id: UUID
    agent_id: UUID
    agent_review_digest: str
    request: GovernanceRequestBinding
    risk_level: RiskLevel
    data_classification: DataClassification
    scope_digest: str
    authorized_model_groups: frozenset[str]
    policy: GovernancePolicyProvenance

    def __post_init__(self) -> None:
        """Require normalized non-empty verified facts before enforcement."""
        if self.authorization_id.int == 0:
            raise ValueError("governance authorization_id must not be nil")
        for name, value in (
            ("issuer", self.issuer),
            ("key_id", self.key_id),
            ("signing_digest", self.signing_digest),
            ("agent_review_digest", self.agent_review_digest),
            ("scope_digest", self.scope_digest),
        ):
            if not value or value.strip() != value:
                raise ValueError(f"{name} must be a normalized non-empty string")
        if not self.audience or any(not item or item.strip() != item for item in self.audience):
            raise ValueError("governance audience must contain normalized non-empty identifiers")
        if self.not_before.tzinfo is None or self.not_before.utcoffset() is None:
            raise ValueError("governance not_before must be timezone-aware")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("governance expires_at must be timezone-aware")
        if self.expires_at <= self.not_before:
            raise ValueError("governance expires_at must follow not_before")
        if not self.authorized_model_groups:
            raise ValueError("governance authorization must include at least one model group")
        if any(not group or group.strip() != group for group in self.authorized_model_groups):
            raise ValueError("governance model groups must be normalized non-empty identifiers")


@dataclass(frozen=True, slots=True)
class GovernanceRuntimeRequest:
    """Trusted request facts available at the gateway enforcement boundary."""

    workload: str
    risk_level: RiskLevel
    data_classification: DataClassification
    context_tokens_estimated: int
    max_output_tokens_estimated: int
    structured_output_required: bool
    max_latency_ms: int
    max_cost_usd: Decimal


def enforce_governance_authorization(
    authorization: VerifiedGovernanceAuthorization,
    runtime_request: GovernanceRuntimeRequest,
    *,
    expected_audience: str,
    now: datetime,
) -> None:
    """Fail closed unless signed governance facts exactly bind the current runtime request."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise GovernanceAuthorizationViolation(
            "governance validation clock must be timezone-aware",
            reason=GovernanceDenialReason.INVALID_CLOCK,
        )
    if not expected_audience or expected_audience.strip() != expected_audience:
        raise GovernanceAuthorizationViolation(
            "expected governance audience is invalid",
            reason=GovernanceDenialReason.INVALID_AUDIENCE_CONFIGURATION,
        )
    if expected_audience not in authorization.audience:
        raise GovernanceAuthorizationViolation(
            "governance authorization audience does not match",
            reason=GovernanceDenialReason.AUDIENCE_MISMATCH,
        )
    if now < authorization.not_before:
        raise GovernanceAuthorizationViolation(
            "governance authorization is not active yet",
            reason=GovernanceDenialReason.NOT_ACTIVE,
        )
    if now >= authorization.expires_at:
        raise GovernanceAuthorizationViolation(
            "governance authorization has expired",
            reason=GovernanceDenialReason.EXPIRED,
        )

    signed = authorization.request
    checks = (
        (
            runtime_request.workload == signed.workload,
            "workload",
            GovernanceDenialReason.WORKLOAD_MISMATCH,
        ),
        (
            runtime_request.risk_level is authorization.risk_level,
            "risk level",
            GovernanceDenialReason.RISK_LEVEL_MISMATCH,
        ),
        (
            runtime_request.data_classification is authorization.data_classification,
            "data classification",
            GovernanceDenialReason.DATA_CLASSIFICATION_MISMATCH,
        ),
        (
            runtime_request.context_tokens_estimated == signed.context_tokens_estimated,
            "context token estimate",
            GovernanceDenialReason.CONTEXT_TOKENS_MISMATCH,
        ),
        (
            runtime_request.max_output_tokens_estimated == signed.max_output_tokens_estimated,
            "max output token estimate",
            GovernanceDenialReason.OUTPUT_TOKENS_MISMATCH,
        ),
        (
            runtime_request.structured_output_required == signed.structured_output_required,
            "structured-output requirement",
            GovernanceDenialReason.STRUCTURED_OUTPUT_MISMATCH,
        ),
        (
            runtime_request.max_latency_ms == signed.max_latency_ms,
            "latency ceiling",
            GovernanceDenialReason.LATENCY_CEILING_MISMATCH,
        ),
        (
            runtime_request.max_cost_usd * Decimal(1_000_000) == signed.max_cost_usd_micros,
            "cost ceiling",
            GovernanceDenialReason.COST_CEILING_MISMATCH,
        ),
    )
    for matches, fact, reason in checks:
        if not matches:
            raise GovernanceAuthorizationViolation(
                f"runtime request does not match governance-authorized {fact}",
                reason=reason,
            )


def governance_authorized_candidates(
    candidates: tuple[ModelDeployment, ...],
    policy_authorization: PolicyAuthorization,
    governance_authorization: VerifiedGovernanceAuthorization,
) -> tuple[ModelDeployment, ...]:
    """Intersect PDP-authorized candidates with signed governance model groups."""
    governance_groups = governance_authorization.authorized_model_groups
    policy_groups = policy_authorization.authorized_model_groups
    effective_groups = governance_groups & policy_groups
    enforce_allowed_subset(effective_groups, policy_groups)
    narrowed = tuple(
        deployment for deployment in candidates if deployment.model_group in effective_groups
    )
    if not narrowed:
        raise GovernanceAuthorizationViolation(
            "governance and Policy Router authorization have no executable "
            "model-group intersection",
            reason=GovernanceDenialReason.NO_MODEL_GROUP_INTERSECTION,
        )
    return narrowed


def enforce_governance_selected_group(
    authorization: VerifiedGovernanceAuthorization,
    model_group: str,
) -> None:
    """Revalidate the final logical model group immediately before provider execution."""
    if not model_group or model_group.strip() != model_group:
        raise GovernanceAuthorizationViolation(
            "selected model group is not a normalized identifier",
            reason=GovernanceDenialReason.SELECTED_MODEL_GROUP_MISMATCH,
        )
    if model_group not in authorization.authorized_model_groups:
        raise GovernanceAuthorizationViolation(
            "selected model group is outside governance authorization",
            reason=GovernanceDenialReason.SELECTED_MODEL_GROUP_MISMATCH,
        )
