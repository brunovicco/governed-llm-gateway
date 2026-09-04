import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from governed_llm_gateway_contracts import (
    Capability,
    DataClassification,
    GatewayRequest,
    Message,
    MessageRole,
    Modality,
    PolicyProvenance,
    RiskLevel,
    RoutingProvenance,
    WorkloadRequirements,
)
from governed_llm_gateway_core.application.governance_evidence import (
    GovernanceEvidenceJournal,
    GovernanceEvidenceOutcome,
)
from governed_llm_gateway_core.application.governance_execution import GovernanceExecutionService
from governed_llm_gateway_core.application.provider import ProviderErrorCode, ProviderResponse
from governed_llm_gateway_core.application.ranking import (
    RankedCandidate,
    RankingDecision,
    ScoreBreakdown,
)
from governed_llm_gateway_core.application.resilience import (
    ExecutionAttempt,
    ExecutionAttemptOutcome,
    ResilienceExecutionError,
    ResilientExecutionResult,
)
from governed_llm_gateway_core.domain.governance import (
    GovernanceAuthorizationViolation,
    GovernanceDenialReason,
    GovernancePolicyProvenance,
    GovernanceRequestBinding,
    GovernanceRuntimeRequest,
    VerifiedGovernanceAuthorization,
)
from governed_llm_gateway_core.domain.model_registry import ModelDeployment, PricingMetadata
from governed_llm_gateway_core.domain.resilience import FallbackSafetyState

NOW = datetime(2026, 9, 4, 14, 0, tzinfo=UTC)
TODAY = date(2026, 9, 4)
REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


def _request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="rag.answer",
        risk_level=RiskLevel.HIGH,
        data_classification=DataClassification.INTERNAL,
        requirements=WorkloadRequirements(),
        messages=(Message(role=MessageRole.USER, content="hello"),),
    )


def _runtime_request(*, workload: str = "rag.answer") -> GovernanceRuntimeRequest:
    return GovernanceRuntimeRequest(
        workload=workload,
        risk_level=RiskLevel.HIGH,
        data_classification=DataClassification.INTERNAL,
        context_tokens_estimated=2048,
        max_output_tokens_estimated=512,
        structured_output_required=False,
        max_latency_ms=5000,
        max_cost_usd=Decimal("0.25"),
    )


def _authorization(*, model_group: str = "agentic-strong") -> VerifiedGovernanceAuthorization:
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
        authorized_model_groups=frozenset({model_group}),
        policy=GovernancePolicyProvenance(
            policy_id="governance-policy",
            policy_version="2.0.0",
            policy_digest="d" * 64,
            control_catalog_id="enterprise-controls",
            control_catalog_version="2.0.0",
            control_catalog_digest="e" * 64,
        ),
    )


def _deployment(deployment_id: str, provider: str) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider=provider,
        model_id=f"model/{deployment_id}",
        model_group="agentic-strong",
        api_family="openai-compatible",
        capabilities=frozenset({Capability.TEXT}),
        context_tokens=128_000,
        modalities=frozenset({Modality.TEXT}),
        pricing=PricingMetadata(
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("2"),
            source_date=TODAY,
            snapshot_version="pricing-v1",
        ),
        max_data_classification=DataClassification.INTERNAL,
        allowed_environments=frozenset({"development"}),
        enabled=True,
        source_date=TODAY,
        catalog_version="catalog-v1",
    )


def _ranked(deployment: ModelDeployment, total: str) -> RankedCandidate:
    score = Decimal(total)
    return RankedCandidate(
        deployment=deployment,
        score=ScoreBreakdown(
            quality=score,
            reliability=Decimal("0"),
            latency=Decimal("0"),
            cost=Decimal("0"),
            availability=Decimal("0"),
            total=score,
        ),
        estimated_cost_usd=Decimal("0.01"),
    )


def _decision(
    selected: ModelDeployment,
    *alternatives: ModelDeployment,
    authorized_model_group: str = "agentic-strong",
) -> RankingDecision:
    routing = RoutingProvenance(
        routing_decision_id="sha256:" + "b" * 64,
        policy=PolicyProvenance(
            decision_id="policy-decision",
            policy_id="gateway-policy",
            policy_version="1.0.0",
            policy_digest="sha256:" + "a" * 64,
        ),
        authorized_model_group=authorized_model_group,
        model_registry_digest="c" * 64,
        ranking_policy_version="ranking-v1",
        ranking_policy_digest="d" * 64,
        score_snapshot_id="static-v1",
        provider=selected.provider,
        model=selected.model_id,
        deployment=selected.deployment_id,
    )
    return RankingDecision(
        routing=routing,
        ranking_policy_digest="d" * 64,
        score_snapshot_id="static-v1",
        selected=_ranked(selected, "1"),
        alternatives=tuple(_ranked(item, "0.5") for item in alternatives),
        rejected_candidates=(),
    )


class _FakeExecutor:
    def __init__(
        self,
        outcome: ResilientExecutionResult | ResilienceExecutionError,
    ) -> None:
        self._outcome = outcome
        self.calls = 0

    async def execute(
        self,
        request: GatewayRequest,
        decision: RankingDecision,
        *,
        max_output_tokens: int,
        provider_timeout_seconds: float = 30.0,
        safety: FallbackSafetyState | None = None,
    ) -> ResilientExecutionResult:
        del request, decision, max_output_tokens, provider_timeout_seconds, safety
        self.calls += 1
        if isinstance(self._outcome, ResilienceExecutionError):
            raise self._outcome
        return self._outcome


def _service(
    executor: _FakeExecutor,
    journal: GovernanceEvidenceJournal,
) -> GovernanceExecutionService:
    return GovernanceExecutionService(
        executor,
        journal,
        expected_audience="governed-llm-gateway",
        service_version="0.1.0",
        clock=lambda: NOW,
    )


def test_invalid_governance_scope_blocks_executor_and_records_denial() -> None:
    selected = _deployment("deployment-a", "provider-a")
    decision = _decision(selected)
    result = ResilientExecutionResult(
        deployment=selected,
        response=ProviderResponse(text="ok"),
        routing=decision.routing,
        attempts=(
            ExecutionAttempt(
                deployment_id=selected.deployment_id,
                attempt_number=1,
                outcome=ExecutionAttemptOutcome.SUCCEEDED,
            ),
        ),
    )
    executor = _FakeExecutor(result)
    journal = GovernanceEvidenceJournal()

    with pytest.raises(GovernanceAuthorizationViolation) as exc_info:
        asyncio.run(
            _service(executor, journal).execute(
                _request(),
                decision,
                _authorization(),
                _runtime_request(workload="rag.other"),
                max_output_tokens=512,
            )
        )

    assert exc_info.value.reason is GovernanceDenialReason.WORKLOAD_MISMATCH
    assert executor.calls == 0
    assert len(journal.records) == 1
    assert journal.records[0].outcome is GovernanceEvidenceOutcome.DENIED
    assert journal.records[0].denial_reason is GovernanceDenialReason.WORKLOAD_MISMATCH


def test_selected_group_outside_signed_scope_blocks_executor() -> None:
    selected = _deployment("deployment-a", "provider-a")
    decision = _decision(selected, authorized_model_group="balanced")
    result = ResilientExecutionResult(
        deployment=selected,
        response=ProviderResponse(text="ok"),
        routing=decision.routing,
        attempts=(
            ExecutionAttempt(
                deployment_id=selected.deployment_id,
                attempt_number=1,
                outcome=ExecutionAttemptOutcome.SUCCEEDED,
            ),
        ),
    )
    executor = _FakeExecutor(result)
    journal = GovernanceEvidenceJournal()

    with pytest.raises(GovernanceAuthorizationViolation) as exc_info:
        asyncio.run(
            _service(executor, journal).execute(
                _request(),
                decision,
                _authorization(),
                _runtime_request(),
                max_output_tokens=512,
            )
        )

    assert exc_info.value.reason is GovernanceDenialReason.SELECTED_MODEL_GROUP_MISMATCH
    assert executor.calls == 0
    assert journal.records[0].policy_router_decision_id == "policy-decision"
    assert journal.records[0].routing_decision_id == decision.routing.routing_decision_id


def test_fallback_success_evidence_uses_actual_deployment_and_real_attempt_count() -> None:
    selected = _deployment("deployment-a", "provider-a")
    fallback = _deployment("deployment-b", "provider-b")
    decision = _decision(selected, fallback)
    fallback_routing = replace(
        decision.routing,
        provider=fallback.provider,
        model=fallback.model_id,
        deployment=fallback.deployment_id,
    )
    result = ResilientExecutionResult(
        deployment=fallback,
        response=ProviderResponse(text="ok"),
        routing=fallback_routing,
        attempts=(
            ExecutionAttempt(
                deployment_id=selected.deployment_id,
                attempt_number=0,
                outcome=ExecutionAttemptOutcome.CIRCUIT_OPEN,
            ),
            ExecutionAttempt(
                deployment_id=fallback.deployment_id,
                attempt_number=1,
                outcome=ExecutionAttemptOutcome.SUCCEEDED,
            ),
        ),
    )
    executor = _FakeExecutor(result)
    journal = GovernanceEvidenceJournal()

    returned = asyncio.run(
        _service(executor, journal).execute(
            _request(),
            decision,
            _authorization(),
            _runtime_request(),
            max_output_tokens=512,
        )
    )

    assert returned is result
    assert executor.calls == 1
    assert len(journal.records) == 1
    evidence = journal.records[0]
    assert evidence.outcome is GovernanceEvidenceOutcome.EXECUTION_SUCCEEDED
    assert evidence.authorization_id == _authorization().authorization_id
    assert evidence.provider == "provider-b"
    assert evidence.deployment_id == "deployment-b"
    assert evidence.attempt_count == 1


def test_terminal_provider_failure_records_last_real_attempt_not_circuit_skip() -> None:
    selected = _deployment("deployment-a", "provider-a")
    fallback = _deployment("deployment-b", "provider-b")
    decision = _decision(selected, fallback)
    terminal = ResilienceExecutionError(
        "all eligible providers failed",
        attempts=(
            ExecutionAttempt(
                deployment_id=selected.deployment_id,
                attempt_number=0,
                outcome=ExecutionAttemptOutcome.CIRCUIT_OPEN,
            ),
            ExecutionAttempt(
                deployment_id=fallback.deployment_id,
                attempt_number=1,
                outcome=ExecutionAttemptOutcome.TRANSIENT_FAILURE,
                error_code=ProviderErrorCode.TIMEOUT,
            ),
            ExecutionAttempt(
                deployment_id=fallback.deployment_id,
                attempt_number=2,
                outcome=ExecutionAttemptOutcome.PERMANENT_FAILURE,
                error_code=ProviderErrorCode.UNAVAILABLE,
            ),
        ),
        last_error_code=ProviderErrorCode.UNAVAILABLE,
    )
    executor = _FakeExecutor(terminal)
    journal = GovernanceEvidenceJournal()

    with pytest.raises(ResilienceExecutionError):
        asyncio.run(
            _service(executor, journal).execute(
                _request(),
                decision,
                _authorization(),
                _runtime_request(),
                max_output_tokens=512,
            )
        )

    assert executor.calls == 1
    assert len(journal.records) == 1
    evidence = journal.records[0]
    assert evidence.outcome is GovernanceEvidenceOutcome.EXECUTION_FAILED
    assert evidence.provider == "provider-b"
    assert evidence.deployment_id == "deployment-b"
    assert evidence.attempt_count == 2
    assert evidence.provider_error_code == ProviderErrorCode.UNAVAILABLE.value


def test_no_provider_attempt_does_not_emit_false_execution_evidence() -> None:
    selected = _deployment("deployment-a", "provider-a")
    decision = _decision(selected)
    terminal = ResilienceExecutionError(
        "execution blocked before provider call",
        attempts=(
            ExecutionAttempt(
                deployment_id=selected.deployment_id,
                attempt_number=0,
                outcome=ExecutionAttemptOutcome.CIRCUIT_OPEN,
            ),
        ),
        last_error_code=None,
    )
    executor = _FakeExecutor(terminal)
    journal = GovernanceEvidenceJournal()

    with pytest.raises(ResilienceExecutionError):
        asyncio.run(
            _service(executor, journal).execute(
                _request(),
                decision,
                _authorization(),
                _runtime_request(),
                max_output_tokens=512,
            )
        )

    assert executor.calls == 1
    assert journal.records == ()
