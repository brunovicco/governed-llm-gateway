"""Governance-aware provider execution wrapper with correlated runtime evidence."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from governed_llm_gateway_contracts import GatewayRequest

from governed_llm_gateway_core.domain.governance import (
    GovernanceAuthorizationViolation,
    GovernanceRuntimeRequest,
    VerifiedGovernanceAuthorization,
    enforce_governance_authorization,
    enforce_governance_selected_group,
)
from governed_llm_gateway_core.domain.resilience import FallbackSafetyState

from .governance_evidence import (
    GovernanceEvidenceJournal,
    build_governance_denial_evidence,
    build_governance_execution_evidence,
)
from .ranking import RankedCandidate, RankingDecision
from .resilience import (
    ExecutionAttemptOutcome,
    ResilienceExecutionError,
    ResilientExecutionResult,
)

EvidenceClock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class GovernanceExecutor(Protocol):
    """Existing bounded executor shape consumed by governance orchestration."""

    async def execute(
        self,
        request: GatewayRequest,
        decision: RankingDecision,
        *,
        max_output_tokens: int,
        provider_timeout_seconds: float = 30.0,
        safety: FallbackSafetyState | None = None,
    ) -> ResilientExecutionResult:
        """Execute one already-ranked authorized request."""
        ...


class GovernanceExecutionService:
    """Validate signed governance immediately before bounded provider execution."""

    def __init__(
        self,
        executor: GovernanceExecutor,
        evidence: GovernanceEvidenceJournal,
        *,
        expected_audience: str,
        service_version: str,
        clock: EvidenceClock = _utc_now,
    ) -> None:
        """Bind the existing executor to governance enforcement and evidence emission."""
        if not expected_audience or expected_audience.strip() != expected_audience:
            raise ValueError("expected_audience must be a normalized non-empty string")
        if not service_version or service_version.strip() != service_version:
            raise ValueError("service_version must be a normalized non-empty string")
        self._executor = executor
        self._evidence = evidence
        self._expected_audience = expected_audience
        self._service_version = service_version
        self._clock = clock

    async def execute(
        self,
        request: GatewayRequest,
        decision: RankingDecision,
        authorization: VerifiedGovernanceAuthorization,
        runtime_request: GovernanceRuntimeRequest,
        *,
        max_output_tokens: int,
        provider_timeout_seconds: float = 30.0,
        safety: FallbackSafetyState | None = None,
    ) -> ResilientExecutionResult:
        """Enforce signed scope, execute, then emit minimized correlated evidence."""
        now = self._clock()
        try:
            enforce_governance_authorization(
                authorization,
                runtime_request,
                expected_audience=self._expected_audience,
                now=now,
            )
            enforce_governance_selected_group(
                authorization,
                decision.routing.authorized_model_group,
            )
        except GovernanceAuthorizationViolation as exc:
            await self._evidence.record(
                build_governance_denial_evidence(
                    authorization,
                    gateway_request_id=request.request_id,
                    workload=request.workload,
                    reason=exc.reason,
                    occurred_at=now,
                    service_version=self._service_version,
                    policy_router_decision_id=decision.routing.policy.decision_id,
                    routing_decision_id=decision.routing.routing_decision_id,
                    model_group=decision.routing.authorized_model_group,
                )
            )
            raise

        try:
            result = await self._executor.execute(
                request,
                decision,
                max_output_tokens=max_output_tokens,
                provider_timeout_seconds=provider_timeout_seconds,
                safety=safety,
            )
        except ResilienceExecutionError as exc:
            failed_candidate = _last_provider_attempt_candidate(decision, exc)
            if failed_candidate is not None:
                provider_attempt_count = sum(
                    attempt.outcome
                    in {
                        ExecutionAttemptOutcome.TRANSIENT_FAILURE,
                        ExecutionAttemptOutcome.PERMANENT_FAILURE,
                    }
                    for attempt in exc.attempts
                )
                await self._evidence.record(
                    build_governance_execution_evidence(
                        authorization,
                        gateway_request_id=request.request_id,
                        workload=request.workload,
                        occurred_at=self._clock(),
                        service_version=self._service_version,
                        policy_router_decision_id=decision.routing.policy.decision_id,
                        routing_decision_id=decision.routing.routing_decision_id,
                        model_group=failed_candidate.deployment.model_group,
                        provider=failed_candidate.deployment.provider,
                        deployment_id=failed_candidate.deployment.deployment_id,
                        succeeded=False,
                        attempt_count=provider_attempt_count,
                        provider_error_code=(
                            exc.last_error_code.value if exc.last_error_code is not None else None
                        ),
                    )
                )
            raise

        await self._evidence.record(
            build_governance_execution_evidence(
                authorization,
                gateway_request_id=request.request_id,
                workload=request.workload,
                occurred_at=self._clock(),
                service_version=self._service_version,
                policy_router_decision_id=result.routing.policy.decision_id,
                routing_decision_id=result.routing.routing_decision_id,
                model_group=result.routing.authorized_model_group,
                provider=result.deployment.provider,
                deployment_id=result.deployment.deployment_id,
                succeeded=True,
                attempt_count=len(result.attempts),
            )
        )
        return result


def _last_provider_attempt_candidate(
    decision: RankingDecision,
    error: ResilienceExecutionError,
) -> RankedCandidate | None:
    """Resolve the last real provider attempt without treating circuit skips as executions."""
    attempted_ids = [
        attempt.deployment_id
        for attempt in error.attempts
        if attempt.outcome
        in {
            ExecutionAttemptOutcome.TRANSIENT_FAILURE,
            ExecutionAttemptOutcome.PERMANENT_FAILURE,
        }
    ]
    if not attempted_ids:
        return None
    last_deployment_id = attempted_ids[-1]
    candidates: list[RankedCandidate] = list(decision.alternatives)
    if decision.selected is not None:
        candidates.insert(0, decision.selected)
    for candidate in candidates:
        if candidate.deployment.deployment_id == last_deployment_id:
            return candidate
    return None
