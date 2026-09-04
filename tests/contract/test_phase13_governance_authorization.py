from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from governed_llm_gateway_contracts import (
    Capability,
    DataClassification,
    Modality,
    RiskLevel,
)
from governed_llm_gateway_core.domain.authorization import PolicyAuthorization
from governed_llm_gateway_core.domain.governance import (
    GovernanceAuthorizationViolation,
    GovernancePolicyProvenance,
    GovernanceRequestBinding,
    GovernanceRuntimeRequest,
    VerifiedGovernanceAuthorization,
    enforce_governance_authorization,
    governance_authorized_candidates,
)
from governed_llm_gateway_core.domain.model_registry import ModelDeployment

NOW = datetime(2026, 9, 4, 13, 30, tzinfo=UTC)


def _authorization(
    *,
    groups: frozenset[str] = frozenset({"agentic-strong"}),
    audience: tuple[str, ...] = ("governed-llm-gateway",),
    not_before: datetime = NOW - timedelta(seconds=30),
    expires_at: datetime = NOW + timedelta(seconds=300),
) -> VerifiedGovernanceAuthorization:
    return VerifiedGovernanceAuthorization(
        authorization_id=UUID("11111111-1111-4111-8111-111111111111"),
        issuer="verifiable-ai-governance",
        audience=audience,
        key_id="governance-key-1",
        signing_digest="a" * 64,
        not_before=not_before,
        expires_at=expires_at,
        initiative_id=UUID("22222222-2222-4222-8222-222222222222"),
        ai_system_id=UUID("33333333-3333-4333-8333-333333333333"),
        agent_id=UUID("44444444-4444-4444-8444-444444444444"),
        agent_review_digest="b" * 64,
        request=GovernanceRequestBinding(
            workflow_id="workflow-1",
            task_id="task-1",
            workload="rag.answer",
            context_tokens_estimated=2048,
            max_output_tokens_estimated=512,
            structured_output_required=False,
            max_latency_ms=5000,
            max_cost_usd_micros=250_000,
        ),
        risk_level=RiskLevel.HIGH,
        data_classification=DataClassification.INTERNAL,
        scope_digest="c" * 64,
        authorized_model_groups=groups,
        policy=GovernancePolicyProvenance(
            policy_id="governance-policy",
            policy_version="2.0.0",
            policy_digest="d" * 64,
            control_catalog_id="enterprise-controls",
            control_catalog_version="2.0.0",
            control_catalog_digest="e" * 64,
        ),
    )


def _runtime_request(**overrides: object) -> GovernanceRuntimeRequest:
    values: dict[str, object] = {
        "workload": "rag.answer",
        "risk_level": RiskLevel.HIGH,
        "data_classification": DataClassification.INTERNAL,
        "context_tokens_estimated": 2048,
        "max_output_tokens_estimated": 512,
        "structured_output_required": False,
        "max_latency_ms": 5000,
        "max_cost_usd": Decimal("0.25"),
    }
    values.update(overrides)
    return GovernanceRuntimeRequest(**values)  # type: ignore[arg-type]


def _deployment(deployment_id: str, model_group: str) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider="provider-a",
        model_id=f"model/{deployment_id}",
        model_group=model_group,
        api_family="openai-compatible",
        capabilities=frozenset({Capability.TEXT}),
        context_tokens=32_000,
        modalities=frozenset({Modality.TEXT}),
        pricing=None,
        max_data_classification=DataClassification.CONFIDENTIAL,
        allowed_environments=frozenset({"prod"}),
        enabled=True,
        source_date=date(2026, 9, 1),
        catalog_version="registry-v1",
    )


def test_verified_governance_authorization_accepts_exact_runtime_binding() -> None:
    enforce_governance_authorization(
        _authorization(),
        _runtime_request(),
        expected_audience="governed-llm-gateway",
        now=NOW,
    )


@pytest.mark.parametrize(
    ("override", "expected_fragment"),
    [
        ({"workload": "agent.orchestration"}, "workload"),
        ({"risk_level": RiskLevel.CRITICAL}, "risk level"),
        (
            {"data_classification": DataClassification.CONFIDENTIAL},
            "data classification",
        ),
        ({"context_tokens_estimated": 2049}, "context token estimate"),
        ({"max_output_tokens_estimated": 513}, "max output token estimate"),
        ({"structured_output_required": True}, "structured-output requirement"),
        ({"max_latency_ms": 5001}, "latency ceiling"),
        ({"max_cost_usd": Decimal("0.250001")}, "cost ceiling"),
    ],
)
def test_runtime_binding_mismatch_fails_closed(
    override: dict[str, object],
    expected_fragment: str,
) -> None:
    with pytest.raises(GovernanceAuthorizationViolation, match=expected_fragment):
        enforce_governance_authorization(
            _authorization(),
            _runtime_request(**override),
            expected_audience="governed-llm-gateway",
            now=NOW,
        )


def test_wrong_audience_fails_closed() -> None:
    with pytest.raises(GovernanceAuthorizationViolation, match="audience"):
        enforce_governance_authorization(
            _authorization(audience=("other-runtime",)),
            _runtime_request(),
            expected_audience="governed-llm-gateway",
            now=NOW,
        )


def test_not_yet_valid_and_expired_authorizations_fail_closed() -> None:
    with pytest.raises(GovernanceAuthorizationViolation, match="not active yet"):
        enforce_governance_authorization(
            _authorization(not_before=NOW + timedelta(seconds=1)),
            _runtime_request(),
            expected_audience="governed-llm-gateway",
            now=NOW,
        )

    with pytest.raises(GovernanceAuthorizationViolation, match="expired"):
        enforce_governance_authorization(
            _authorization(expires_at=NOW),
            _runtime_request(),
            expected_audience="governed-llm-gateway",
            now=NOW,
        )


def test_governance_intersection_can_only_narrow_policy_authorization() -> None:
    policy = PolicyAuthorization(
        decision_id="policy-decision-1",
        authorized_model_groups=frozenset({"agentic-strong", "balanced"}),
    )
    candidates = (
        _deployment("candidate-a", "agentic-strong"),
        _deployment("candidate-b", "balanced"),
    )

    narrowed = governance_authorized_candidates(
        candidates,
        policy,
        _authorization(groups=frozenset({"agentic-strong", "outside-policy"})),
    )

    assert tuple(item.deployment_id for item in narrowed) == ("candidate-a",)


def test_governance_cannot_resurrect_candidate_outside_policy_set() -> None:
    policy = PolicyAuthorization(
        decision_id="policy-decision-1",
        authorized_model_groups=frozenset({"balanced"}),
    )
    candidates = (_deployment("candidate-b", "balanced"),)

    with pytest.raises(GovernanceAuthorizationViolation, match="no executable model-group"):
        governance_authorized_candidates(
            candidates,
            policy,
            _authorization(groups=frozenset({"agentic-strong"})),
        )
