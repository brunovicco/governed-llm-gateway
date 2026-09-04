"""Verified governance authorization facts and fail-closed scope enforcement."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from governed_llm_gateway_contracts import DataClassification, RiskLevel

from .authorization import PolicyAuthorization, enforce_allowed_subset
from .model_registry import ModelDeployment


class GovernanceAuthorizationViolation(ValueError):
    """Raised when verified governance scope does not authorize the runtime request."""


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
        raise GovernanceAuthorizationViolation("governance validation clock must be timezone-aware")
    if not expected_audience or expected_audience.strip() != expected_audience:
        raise GovernanceAuthorizationViolation("expected governance audience is invalid")
    if expected_audience not in authorization.audience:
        raise GovernanceAuthorizationViolation("governance authorization audience does not match")
    if now < authorization.not_before:
        raise GovernanceAuthorizationViolation("governance authorization is not active yet")
    if now >= authorization.expires_at:
        raise GovernanceAuthorizationViolation("governance authorization has expired")

    signed = authorization.request
    checks = (
        (runtime_request.workload == signed.workload, "workload"),
        (runtime_request.risk_level is authorization.risk_level, "risk level"),
        (
            runtime_request.data_classification is authorization.data_classification,
            "data classification",
        ),
        (
            runtime_request.context_tokens_estimated == signed.context_tokens_estimated,
            "context token estimate",
        ),
        (
            runtime_request.max_output_tokens_estimated == signed.max_output_tokens_estimated,
            "max output token estimate",
        ),
        (
            runtime_request.structured_output_required == signed.structured_output_required,
            "structured-output requirement",
        ),
        (runtime_request.max_latency_ms == signed.max_latency_ms, "latency ceiling"),
        (
            runtime_request.max_cost_usd * Decimal(1_000_000) == signed.max_cost_usd_micros,
            "cost ceiling",
        ),
    )
    for matches, fact in checks:
        if not matches:
            raise GovernanceAuthorizationViolation(
                f"runtime request does not match governance-authorized {fact}"
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
            "governance and Policy Router authorization have no executable model-group intersection"
        )
    return narrowed
