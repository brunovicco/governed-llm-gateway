import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from governed_llm_gateway_contracts import DataClassification, RiskLevel
from governed_llm_gateway_core.application.governance_evidence import (
    GovernanceEvidenceDeliveryError,
    GovernanceEvidenceDeliveryMode,
    GovernanceEvidenceJournal,
    GovernanceEvidenceOutcome,
    GovernanceRuntimeEvidence,
    build_governance_denial_evidence,
    build_governance_execution_evidence,
)
from governed_llm_gateway_core.domain.governance import (
    GovernanceAuthorizationViolation,
    GovernanceDenialReason,
    GovernancePolicyProvenance,
    GovernanceRequestBinding,
    VerifiedGovernanceAuthorization,
    enforce_governance_selected_group,
)

NOW = datetime(2026, 9, 4, 14, 0, tzinfo=UTC)
REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _authorization() -> VerifiedGovernanceAuthorization:
    return VerifiedGovernanceAuthorization(
        authorization_id=UUID("11111111-1111-4111-8111-111111111111"),
        issuer="verifiable-ai-governance",
        audience=("governed-llm-gateway",),
        key_id="governance-key-1",
        signing_digest="a" * 64,
        not_before=NOW - timedelta(seconds=30),
        expires_at=NOW + timedelta(seconds=300),
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
        authorized_model_groups=frozenset({"agentic-strong"}),
        policy=GovernancePolicyProvenance(
            policy_id="governance-policy",
            policy_version="2.0.0",
            policy_digest="d" * 64,
            control_catalog_id="enterprise-controls",
            control_catalog_version="2.0.0",
            control_catalog_digest="e" * 64,
        ),
    )


def test_selected_model_group_is_revalidated_at_execution_boundary() -> None:
    enforce_governance_selected_group(_authorization(), "agentic-strong")

    with pytest.raises(GovernanceAuthorizationViolation) as exc_info:
        enforce_governance_selected_group(_authorization(), "balanced")

    assert exc_info.value.reason is GovernanceDenialReason.SELECTED_MODEL_GROUP_MISMATCH


def test_denial_evidence_preserves_verified_authorization_identity() -> None:
    authorization = _authorization()
    evidence = build_governance_denial_evidence(
        authorization,
        gateway_request_id=REQUEST_ID,
        workload="rag.answer",
        reason=GovernanceDenialReason.SELECTED_MODEL_GROUP_MISMATCH,
        occurred_at=NOW,
        service_version="0.1.0",
        policy_router_decision_id="pdp-1",
        routing_decision_id="route-1",
        model_group="balanced",
    )

    assert evidence.outcome is GovernanceEvidenceOutcome.DENIED
    assert evidence.authorization_id == authorization.authorization_id
    assert evidence.authorization_signing_digest == authorization.signing_digest
    assert evidence.authorization_key_id == authorization.key_id
    assert evidence.policy_router_decision_id == "pdp-1"
    assert evidence.routing_decision_id == "route-1"
    assert evidence.model_group == "balanced"
    assert evidence.provider is None
    assert evidence.deployment_id is None


def test_preverification_denial_does_not_trust_unverified_authorization_claims() -> None:
    evidence = build_governance_denial_evidence(
        None,
        gateway_request_id=REQUEST_ID,
        workload="rag.answer",
        reason=GovernanceDenialReason.AUDIENCE_MISMATCH,
        occurred_at=NOW,
        service_version="0.1.0",
    )

    assert evidence.authorization_id is None
    assert evidence.authorization_signing_digest is None
    assert evidence.authorization_key_id is None


def test_execution_evidence_reconstructs_governance_to_provider_chain() -> None:
    authorization = _authorization()
    evidence = build_governance_execution_evidence(
        authorization,
        gateway_request_id=REQUEST_ID,
        workload="rag.answer",
        occurred_at=NOW,
        service_version="0.1.0",
        policy_router_decision_id="pdp-1",
        routing_decision_id="route-1",
        model_group="agentic-strong",
        provider="provider-a",
        deployment_id="deployment-a",
        succeeded=True,
        attempt_count=2,
    )

    assert evidence.outcome is GovernanceEvidenceOutcome.EXECUTION_SUCCEEDED
    assert evidence.authorization_id == authorization.authorization_id
    assert evidence.policy_router_decision_id == "pdp-1"
    assert evidence.routing_decision_id == "route-1"
    assert evidence.model_group == "agentic-strong"
    assert evidence.provider == "provider-a"
    assert evidence.deployment_id == "deployment-a"
    assert evidence.attempt_count == 2


def test_failed_execution_evidence_carries_sanitized_provider_error_code() -> None:
    evidence = build_governance_execution_evidence(
        _authorization(),
        gateway_request_id=REQUEST_ID,
        workload="rag.answer",
        occurred_at=NOW,
        service_version="0.1.0",
        policy_router_decision_id="pdp-1",
        routing_decision_id="route-1",
        model_group="agentic-strong",
        provider="provider-a",
        deployment_id="deployment-a",
        succeeded=False,
        attempt_count=3,
        provider_error_code="timeout",
    )

    assert evidence.outcome is GovernanceEvidenceOutcome.EXECUTION_FAILED
    assert evidence.provider_error_code == "timeout"


@pytest.mark.parametrize(
    "evidence",
    [
        GovernanceRuntimeEvidence(
            gateway_request_id=REQUEST_ID,
            occurred_at=NOW,
            service_version="0.1.0",
            workload="rag.answer",
            outcome=GovernanceEvidenceOutcome.DENIED,
            denial_reason=GovernanceDenialReason.EXPIRED,
        ),
        GovernanceRuntimeEvidence(
            gateway_request_id=REQUEST_ID,
            occurred_at=NOW,
            service_version="0.1.0",
            workload="rag.answer",
            outcome=GovernanceEvidenceOutcome.EXECUTION_FAILED,
            authorization_id=UUID("11111111-1111-4111-8111-111111111111"),
            policy_router_decision_id="pdp-1",
            routing_decision_id="route-1",
            model_group="agentic-strong",
            provider="provider-a",
            deployment_id="deployment-a",
            provider_error_code="timeout",
            attempt_count=1,
        ),
    ],
)
def test_evidence_shape_contains_only_metadata(evidence: GovernanceRuntimeEvidence) -> None:
    assert not hasattr(evidence, "prompt")
    assert not hasattr(evidence, "completion")
    assert not hasattr(evidence, "provider_payload")
    assert not hasattr(evidence, "private_key")


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list[GovernanceRuntimeEvidence] = []

    async def emit(self, evidence: GovernanceRuntimeEvidence) -> None:
        self.events.append(evidence)


class _FailingSink:
    async def emit(self, evidence: GovernanceRuntimeEvidence) -> None:
        del evidence
        raise RuntimeError("remote sink unavailable")


def test_journal_records_locally_before_successful_remote_delivery() -> None:
    sink = _RecordingSink()
    journal = GovernanceEvidenceJournal(sink=sink)
    evidence = build_governance_denial_evidence(
        _authorization(),
        gateway_request_id=REQUEST_ID,
        workload="rag.answer",
        reason=GovernanceDenialReason.EXPIRED,
        occurred_at=NOW,
        service_version="0.1.0",
    )

    asyncio.run(journal.record(evidence))

    assert journal.records == (evidence,)
    assert sink.events == [evidence]


def test_best_effort_sink_failure_keeps_local_evidence() -> None:
    journal = GovernanceEvidenceJournal(sink=_FailingSink())
    evidence = build_governance_denial_evidence(
        _authorization(),
        gateway_request_id=REQUEST_ID,
        workload="rag.answer",
        reason=GovernanceDenialReason.EXPIRED,
        occurred_at=NOW,
        service_version="0.1.0",
    )

    asyncio.run(journal.record(evidence))

    assert journal.records == (evidence,)


def test_required_sink_failure_raises_after_local_recording() -> None:
    journal = GovernanceEvidenceJournal(
        sink=_FailingSink(),
        delivery_mode=GovernanceEvidenceDeliveryMode.REQUIRED,
    )
    evidence = build_governance_denial_evidence(
        _authorization(),
        gateway_request_id=REQUEST_ID,
        workload="rag.answer",
        reason=GovernanceDenialReason.EXPIRED,
        occurred_at=NOW,
        service_version="0.1.0",
    )

    with pytest.raises(GovernanceEvidenceDeliveryError, match="required governance evidence"):
        asyncio.run(journal.record(evidence))

    assert journal.records == (evidence,)


def test_execution_evidence_requires_full_correlation_chain() -> None:
    with pytest.raises(ValueError, match="correlate PDP and routing decisions"):
        GovernanceRuntimeEvidence(
            gateway_request_id=REQUEST_ID,
            occurred_at=NOW,
            service_version="0.1.0",
            workload="rag.answer",
            outcome=GovernanceEvidenceOutcome.EXECUTION_SUCCEEDED,
            authorization_id=UUID("11111111-1111-4111-8111-111111111111"),
            model_group="agentic-strong",
            provider="provider-a",
            deployment_id="deployment-a",
            attempt_count=1,
        )
