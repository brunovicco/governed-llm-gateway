"""Contract tests for terminal provider API-family provenance."""

import asyncio
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from governed_llm_gateway_api.stream_generate import _event_payload
from governed_llm_gateway_client._codec import _decode_event
from governed_llm_gateway_contracts import (
    Capability,
    DataClassification,
    ExecutionStatus,
    GatewayRequest,
    GatewayStreamEvent,
    Message,
    MessageRole,
    Modality,
    PolicyProvenance,
    ProviderExecution,
    RiskLevel,
    RoutingProvenance,
    StreamEventType,
    WorkloadRequirements,
)
from governed_llm_gateway_core.application.provider import (
    ProviderContentDelta,
    ProviderFeatureSupport,
    ProviderRequest,
    ProviderResponse,
    ProviderResponseCompleted,
    ProviderResponseStarted,
    ProviderStreamEvent,
    ProviderUsage,
    ProviderUsageCompleted,
)
from governed_llm_gateway_core.application.ranking import (
    RankedCandidate,
    RankingDecision,
    ScoreBreakdown,
)
from governed_llm_gateway_core.application.resilience import (
    InMemoryHealthTracker,
    StaticProviderResolver,
)
from governed_llm_gateway_core.application.streaming import StreamingExecutionService
from governed_llm_gateway_core.domain.model_registry import ModelDeployment

_REQUEST_ID = UUID("37373737-3737-4737-8737-373737373737")
_TODAY = date(2026, 9, 5)


class _StreamingProvider:
    feature_support = ProviderFeatureSupport(native_streaming=True, streaming_usage=True)

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        del request
        raise AssertionError("test requires streaming execution")

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        del request
        yield ProviderResponseStarted(response_id="provider-response")
        yield ProviderContentDelta(delta="ok")
        yield ProviderUsageCompleted(usage=ProviderUsage(input_tokens=4, output_tokens=2))
        yield ProviderResponseCompleted(response_id="provider-response", finish_reason="stop")


class _Clock:
    def __init__(self) -> None:
        self._values = iter((100.0, 100.25))

    def __call__(self) -> float:
        return next(self._values)


def _deployment() -> ModelDeployment:
    return ModelDeployment(
        deployment_id="deployment-a",
        provider="provider-a",
        model_id="model/a",
        model_group="balanced",
        api_family="openai-compatible",
        capabilities=frozenset({Capability.TEXT, Capability.STREAMING}),
        context_tokens=128_000,
        modalities=frozenset({Modality.TEXT}),
        pricing=None,
        max_data_classification=DataClassification.INTERNAL,
        allowed_environments=frozenset({"development"}),
        enabled=True,
        source_date=_TODAY,
        catalog_version="catalog-v1",
    )


def _routing() -> RoutingProvenance:
    return RoutingProvenance(
        routing_decision_id="sha256:" + "1" * 64,
        policy=PolicyProvenance(
            decision_id="policy-decision",
            policy_id="gateway-policy",
            policy_version="1.0.0",
            policy_digest="sha256:" + "2" * 64,
        ),
        authorized_model_group="balanced",
        model_registry_digest="sha256:" + "3" * 64,
        ranking_policy_version="ranking-v1",
        ranking_policy_digest="sha256:" + "4" * 64,
        score_snapshot_id="static-v1",
        provider="provider-a",
        model="model/a",
        deployment="deployment-a",
        fallback_sequence=("deployment-a",),
    )


def _decision(deployment: ModelDeployment) -> RankingDecision:
    return RankingDecision(
        routing=_routing(),
        ranking_policy_digest="sha256:" + "4" * 64,
        score_snapshot_id="static-v1",
        selected=RankedCandidate(
            deployment=deployment,
            score=ScoreBreakdown(
                quality=Decimal("1"),
                reliability=Decimal("0"),
                latency=Decimal("0"),
                cost=Decimal("0"),
                availability=Decimal("0"),
                total=Decimal("1"),
            ),
            estimated_cost_usd=None,
        ),
        alternatives=(),
        rejected_candidates=(),
    )


def _request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=_REQUEST_ID,
        workload="benchmark.multimodal-analysis",
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(streaming=True),
        messages=(Message(role=MessageRole.USER, content="analyze"),),
    )


def test_runtime_terminal_execution_preserves_selected_api_family() -> None:
    deployment = _deployment()
    service = StreamingExecutionService(
        health=InMemoryHealthTracker(),
        resolver=StaticProviderResolver(
            {(deployment.provider, deployment.api_family): _StreamingProvider()}
        ),
        clock=_Clock(),
    )

    async def collect() -> tuple[GatewayStreamEvent, ...]:
        return tuple(
            [
                event
                async for event in service.stream(
                    _request(),
                    _decision(deployment),
                    max_output_tokens=64,
                )
            ]
        )

    terminal = asyncio.run(collect())[-1]

    assert terminal.event_type is StreamEventType.RESPONSE_COMPLETED
    assert terminal.execution is not None
    assert terminal.execution.api_family == "openai-compatible"


def test_api_payload_and_client_codec_round_trip_api_family() -> None:
    execution = ProviderExecution(
        provider="provider-a",
        model="model/a",
        deployment="deployment-a",
        status=ExecutionStatus.SUCCEEDED,
        latency_ms=25,
        api_family="openai-compatible",
    )
    event = GatewayStreamEvent(
        event_type=StreamEventType.RESPONSE_COMPLETED,
        request_id=_REQUEST_ID,
        sequence_number=1,
        routing=_routing(),
        execution=execution,
    )

    payload = _event_payload(event)
    execution_payload = payload["execution"]
    assert isinstance(execution_payload, dict)
    assert execution_payload["api_family"] == "openai-compatible"
    assert _decode_event(payload).execution == execution


def test_legacy_terminal_payload_omits_absent_api_family() -> None:
    event = GatewayStreamEvent(
        event_type=StreamEventType.RESPONSE_COMPLETED,
        request_id=_REQUEST_ID,
        sequence_number=1,
        routing=_routing(),
        execution=ProviderExecution(
            provider="provider-a",
            model="model/a",
            deployment="deployment-a",
            status=ExecutionStatus.SUCCEEDED,
            latency_ms=25,
        ),
    )

    payload = _event_payload(event)
    execution_payload = payload["execution"]
    assert isinstance(execution_payload, dict)
    assert "api_family" not in execution_payload
    assert _decode_event(payload).execution == event.execution


@pytest.mark.parametrize("api_family", ["", " openai-compatible", "openai-compatible "])
def test_provider_execution_rejects_non_normalized_api_family(api_family: str) -> None:
    with pytest.raises(ValueError, match="api_family must be normalized"):
        ProviderExecution(
            provider="provider-a",
            model="model/a",
            deployment="deployment-a",
            status=ExecutionStatus.SUCCEEDED,
            latency_ms=1,
            api_family=api_family,
        )
