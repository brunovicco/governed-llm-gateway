"""Phase 14 contract tests for terminal provider execution evidence."""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from governed_llm_gateway_api.stream_generate import _event_payload
from governed_llm_gateway_client import GatewayClient, GatewayClientConfig
from governed_llm_gateway_client.errors import GatewayProtocolError
from governed_llm_gateway_contracts import (
    Capability,
    DataClassification,
    ExecutionStatus,
    GatewayRequest,
    GatewayResponse,
    GatewayStreamEvent,
    Message,
    MessageRole,
    Modality,
    PolicyProvenance,
    ProviderExecution,
    RiskLevel,
    RoutingProvenance,
    StreamEventType,
    Usage,
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
from governed_llm_gateway_core.domain.model_registry import ModelDeployment, PricingMetadata

REQUEST_ID = UUID("14141414-1414-4414-8414-141414141414")
TODAY = date(2026, 9, 4)
BASE_URL = "https://gateway.example"
API_KEY = "gateway-secret"


class EvidenceStreamingProvider:
    """Deterministic provider that emits measured usage supplied by its runtime boundary."""

    feature_support = ProviderFeatureSupport(native_streaming=True, streaming_usage=True)

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Reject non-streaming use in this contract slice."""
        del request
        raise AssertionError("terminal evidence test requires streaming execution")

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        """Emit one successful provider lifecycle with explicit provider-normalized cost."""
        del request
        yield ProviderResponseStarted(response_id="provider-response")
        yield ProviderContentDelta(delta="ok")
        yield ProviderUsageCompleted(
            usage=ProviderUsage(
                input_tokens=17,
                output_tokens=5,
                total_cost_usd=Decimal("0.0042"),
            )
        )
        yield ProviderResponseCompleted(response_id="provider-response", finish_reason="stop")


class DeterministicClock:
    """Return fixed monotonic readings for start, TTFT, and terminal latency."""

    def __init__(self) -> None:
        self._readings = iter((100.0, 100.25))

    def __call__(self) -> float:
        return next(self._readings)


def _routing() -> RoutingProvenance:
    return RoutingProvenance(
        routing_decision_id="sha256:" + "1" * 64,
        policy=PolicyProvenance(
            decision_id="policy-decision",
            policy_id="gateway-policy",
            policy_version="1.0.0",
            policy_digest="sha256:" + "2" * 64,
        ),
        authorized_model_group="agentic-strong",
        model_registry_digest="sha256:" + "3" * 64,
        ranking_policy_version="ranking-v1",
        ranking_policy_digest="sha256:" + "4" * 64,
        score_snapshot_id="static-v1",
        provider="provider-a",
        model="model/a",
        deployment="deployment-a",
        fallback_sequence=("deployment-a",),
    )


def _deployment() -> ModelDeployment:
    return ModelDeployment(
        deployment_id="deployment-a",
        provider="provider-a",
        model_id="model/a",
        model_group="agentic-strong",
        api_family="openai-compatible",
        capabilities=frozenset({Capability.TEXT, Capability.STREAMING}),
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
            estimated_cost_usd=Decimal("0.01"),
        ),
        alternatives=(),
        rejected_candidates=(),
    )


def _request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="opslens.semantic-query.plan",
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(streaming=True),
        messages=(Message(role=MessageRole.USER, content="plan"),),
    )


def _sse(event: GatewayStreamEvent) -> str:
    payload = _event_payload(event)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"event: {event.event_type.value}\nid: {event.sequence_number}\ndata: {encoded}\n\n"


def test_runtime_terminal_execution_preserves_measured_identity_usage_latency_and_cost() -> None:
    """Build terminal evidence only from the selected deployment and measured provider facts."""
    deployment = _deployment()
    service = StreamingExecutionService(
        health=InMemoryHealthTracker(),
        resolver=StaticProviderResolver(
            {(deployment.provider, deployment.api_family): EvidenceStreamingProvider()}
        ),
        clock=DeterministicClock(),
    )

    async def collect() -> list[GatewayStreamEvent]:
        return [
            event
            async for event in service.stream(
                _request(),
                _decision(deployment),
                max_output_tokens=64,
            )
        ]

    events = asyncio.run(collect())
    usage_event = next(
        event for event in events if event.event_type is StreamEventType.USAGE_COMPLETED
    )
    terminal = events[-1]

    assert usage_event.usage == Usage(
        input_tokens=17,
        output_tokens=5,
        total_cost_usd=Decimal("0.0042"),
    )
    assert terminal.event_type is StreamEventType.RESPONSE_COMPLETED
    assert terminal.routing == _routing()
    assert terminal.execution == ProviderExecution(
        provider="provider-a",
        model="model/a",
        deployment="deployment-a",
        status=ExecutionStatus.SUCCEEDED,
        latency_ms=250,
        usage=usage_event.usage,
        provider_request_id="provider-response",
        finish_reason="stop",
        attempt_number=1,
        fallback_index=0,
        api_family="openai-compatible",
    )


def test_api_payload_preserves_terminal_execution_without_synthesizing_cost() -> None:
    """Serialize known execution facts and leave unavailable cost absent rather than zero."""
    execution = ProviderExecution(
        provider="provider-a",
        model="model/a",
        deployment="deployment-a",
        status=ExecutionStatus.SUCCEEDED,
        latency_ms=41,
        usage=Usage(input_tokens=7, output_tokens=3, total_cost_usd=None),
    )
    payload = _event_payload(
        GatewayStreamEvent(
            event_type=StreamEventType.RESPONSE_COMPLETED,
            request_id=REQUEST_ID,
            sequence_number=1,
            routing=_routing(),
            execution=execution,
            finish_reason="stop",
        )
    )

    assert payload["execution"] == {
        "provider": "provider-a",
        "model": "model/a",
        "deployment": "deployment-a",
        "status": "succeeded",
        "latency_ms": 41,
        "attempt_number": 1,
        "fallback_index": 0,
        "usage": {"input_tokens": 7, "output_tokens": 3},
    }


def test_terminal_contract_rejects_execution_identity_outside_routing_provenance() -> None:
    """Fail closed when terminal execution identity disagrees with routing provenance."""
    with pytest.raises(ValueError, match="does not match routing provenance"):
        GatewayStreamEvent(
            event_type=StreamEventType.RESPONSE_COMPLETED,
            request_id=REQUEST_ID,
            sequence_number=1,
            routing=_routing(),
            execution=ProviderExecution(
                provider="provider-b",
                model="model/a",
                deployment="deployment-a",
                status=ExecutionStatus.SUCCEEDED,
                latency_ms=1,
            ),
        )


def test_gateway_client_generate_preserves_terminal_execution_and_usage_exactly() -> None:
    """Aggregate SSE into GatewayResponse.execution without reconstructing provider evidence."""
    usage = Usage(input_tokens=17, output_tokens=5, total_cost_usd=Decimal("0.0042"))
    execution = ProviderExecution(
        provider="provider-a",
        model="model/a",
        deployment="deployment-a",
        status=ExecutionStatus.SUCCEEDED,
        latency_ms=250,
        usage=usage,
    )
    body = "".join(
        (
            _sse(
                GatewayStreamEvent(
                    event_type=StreamEventType.RESPONSE_STARTED,
                    request_id=REQUEST_ID,
                    sequence_number=1,
                    routing=_routing(),
                )
            ),
            _sse(
                GatewayStreamEvent(
                    event_type=StreamEventType.CONTENT_DELTA,
                    request_id=REQUEST_ID,
                    sequence_number=2,
                    delta="ok",
                )
            ),
            _sse(
                GatewayStreamEvent(
                    event_type=StreamEventType.USAGE_COMPLETED,
                    request_id=REQUEST_ID,
                    sequence_number=3,
                    usage=usage,
                )
            ),
            _sse(
                GatewayStreamEvent(
                    event_type=StreamEventType.RESPONSE_COMPLETED,
                    request_id=REQUEST_ID,
                    sequence_number=4,
                    routing=_routing(),
                    execution=execution,
                    finish_reason="stop",
                )
            ),
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=body,
            request=request,
        )

    async def generate() -> GatewayResponse:
        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await client.generate(
                workload="opslens.semantic-query.plan",
                messages=(Message(role=MessageRole.USER, content="plan"),),
                risk_level=RiskLevel.LOW,
                data_classification=DataClassification.PUBLIC,
                request_id=REQUEST_ID,
            )

    response = asyncio.run(generate())
    assert response.execution == execution
    assert response.routing == _routing()


def test_gateway_client_fails_closed_when_terminal_usage_disagrees_with_stream_usage() -> None:
    """Reject a terminal evidence record that contradicts the stream's final usage event."""
    observed_usage = Usage(input_tokens=17, output_tokens=5, total_cost_usd=Decimal("0.0042"))
    terminal_usage = Usage(input_tokens=18, output_tokens=5, total_cost_usd=Decimal("0.0042"))
    body = "".join(
        (
            _sse(
                GatewayStreamEvent(
                    event_type=StreamEventType.RESPONSE_STARTED,
                    request_id=REQUEST_ID,
                    sequence_number=1,
                    routing=_routing(),
                )
            ),
            _sse(
                GatewayStreamEvent(
                    event_type=StreamEventType.CONTENT_DELTA,
                    request_id=REQUEST_ID,
                    sequence_number=2,
                    delta="ok",
                )
            ),
            _sse(
                GatewayStreamEvent(
                    event_type=StreamEventType.USAGE_COMPLETED,
                    request_id=REQUEST_ID,
                    sequence_number=3,
                    usage=observed_usage,
                )
            ),
            _sse(
                GatewayStreamEvent(
                    event_type=StreamEventType.RESPONSE_COMPLETED,
                    request_id=REQUEST_ID,
                    sequence_number=4,
                    routing=_routing(),
                    execution=ProviderExecution(
                        provider="provider-a",
                        model="model/a",
                        deployment="deployment-a",
                        status=ExecutionStatus.SUCCEEDED,
                        latency_ms=250,
                        usage=terminal_usage,
                    ),
                )
            ),
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=body,
            request=request,
        )

    async def generate() -> None:
        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            with pytest.raises(GatewayProtocolError, match="usage does not match"):
                await client.generate(
                    workload="opslens.semantic-query.plan",
                    messages=(Message(role=MessageRole.USER, content="plan"),),
                    risk_level=RiskLevel.LOW,
                    data_classification=DataClassification.PUBLIC,
                    request_id=REQUEST_ID,
                )

    asyncio.run(generate())
