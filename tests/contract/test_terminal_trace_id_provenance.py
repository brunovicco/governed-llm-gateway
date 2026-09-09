"""Contract tests for terminal provider execution trace-ID provenance."""

import json
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from a2a_otel_kit import Observability, ObservabilitySettings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from governed_llm_gateway_api import (
    GenerateCoordinator,
    GenerateRequestModel,
    PreparedStreamingExecution,
    attach_generate_route,
)
from governed_llm_gateway_api.stream_generate import _event_payload
from governed_llm_gateway_client._codec import _decode_event
from governed_llm_gateway_contracts import (
    DataClassification,
    ExecutionStatus,
    GatewayRequest,
    GatewayStreamEvent,
    Message,
    MessageRole,
    PolicyProvenance,
    ProviderExecution,
    RiskLevel,
    RoutingProvenance,
    StreamEventType,
)
from governed_llm_gateway_core.application.ranking import RankingDecision
from governed_llm_gateway_core.application.telemetry import current_trace_id
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import INVALID_SPAN

REQUEST_ID = UUID("88888888-8888-4888-8888-888888888888")
TRACE_ID_HEX = "abcdef1234567890abcdef1234567890"
TRACEPARENT = f"00-{TRACE_ID_HEX}-1234567890abcdef-01"


def _observability() -> Observability:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(InMemorySpanExporter()))
    settings = ObservabilitySettings(
        service_name="governed-gateway-trace-id-test",
        service_version="0.1.0",
        environment="test",
        enabled=False,
    )
    return Observability(
        settings=settings,
        tracer=provider.get_tracer(settings.service_name, settings.service_version),
        lifecycle=None,
    )


def _routing() -> RoutingProvenance:
    return RoutingProvenance(
        routing_decision_id="sha256:" + "e" * 64,
        policy=PolicyProvenance(
            decision_id="policy-decision",
            policy_id="gateway-policy",
            policy_version="1.0.0",
            policy_digest="sha256:" + "f" * 64,
        ),
        authorized_model_group="balanced",
        model_registry_digest="a" * 64,
        ranking_policy_version="ranking-v1",
        ranking_policy_digest="b" * 64,
        score_snapshot_id="static-v1",
        provider="provider-a",
        model="model-a",
        deployment="deployment-a",
        fallback_sequence=("deployment-a",),
    )


def _request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="rag.answer",
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.PUBLIC,
        messages=(Message(role=MessageRole.USER, content="trace-id-provenance"),),
    )


def _prepared() -> PreparedStreamingExecution:
    decision = cast(RankingDecision, SimpleNamespace(routing=_routing()))
    return PreparedStreamingExecution(
        request=_request(),
        decision=decision,
        max_output_tokens=32,
        provider_timeout_seconds=1.0,
    )


def _payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": str(REQUEST_ID),
        "workload": "rag.answer",
        "risk_level": "low",
        "data_classification": "public",
        "messages": [{"role": "user", "content": "trace-id-provenance"}],
        "context_tokens_estimated": 10,
        "max_output_tokens": 32,
    }


def _terminal_execution() -> ProviderExecution:
    return ProviderExecution(
        provider="provider-a",
        model="model-a",
        deployment="deployment-a",
        status=ExecutionStatus.SUCCEEDED,
        latency_ms=12,
    )


class _TraceIdGenerateCoordinator:
    def __init__(self, prepared: PreparedStreamingExecution) -> None:
        self._prepared = prepared

    async def prepare(
        self,
        *,
        api_key: str,
        payload: GenerateRequestModel,
    ) -> PreparedStreamingExecution:
        del api_key, payload
        return self._prepared

    async def stream(
        self,
        prepared: PreparedStreamingExecution,
    ) -> AsyncGenerator[GatewayStreamEvent]:
        del prepared
        yield GatewayStreamEvent(
            event_type=StreamEventType.RESPONSE_COMPLETED,
            request_id=REQUEST_ID,
            sequence_number=1,
            routing=_routing(),
            execution=_terminal_execution(),
            finish_reason="stop",
        )


def test_generate_route_stamps_terminal_execution_with_continued_trace_id() -> None:
    observability = _observability()
    fake = _TraceIdGenerateCoordinator(_prepared())
    app = FastAPI()
    attach_generate_route(app, cast(GenerateCoordinator, fake), observability=observability)

    response = TestClient(app).post(
        "/v1/generate",
        headers={"X-Gateway-API-Key": "gateway-key", "traceparent": TRACEPARENT},
        json=_payload(),
    )

    assert response.status_code == 200
    terminal_line = next(line for line in response.text.splitlines() if line.startswith("data: "))
    decoded = _decode_event(cast(dict[str, object], json.loads(terminal_line[6:])))
    assert decoded.execution is not None
    assert decoded.execution.trace_id == TRACE_ID_HEX


def test_generate_route_leaves_trace_id_absent_when_observability_disabled() -> None:
    fake = _TraceIdGenerateCoordinator(_prepared())
    app = FastAPI()
    attach_generate_route(app, cast(GenerateCoordinator, fake), observability=None)

    response = TestClient(app).post(
        "/v1/generate",
        headers={"X-Gateway-API-Key": "gateway-key"},
        json=_payload(),
    )

    assert response.status_code == 200
    terminal_line = next(line for line in response.text.splitlines() if line.startswith("data: "))
    decoded = _decode_event(cast(dict[str, object], json.loads(terminal_line[6:])))
    assert decoded.execution is not None
    assert decoded.execution.trace_id is None


def test_current_trace_id_returns_none_for_an_invalid_span_context() -> None:
    assert current_trace_id(INVALID_SPAN) is None


def test_api_payload_and_client_codec_round_trip_trace_id() -> None:
    execution = ProviderExecution(
        provider="provider-a",
        model="model-a",
        deployment="deployment-a",
        status=ExecutionStatus.SUCCEEDED,
        latency_ms=25,
        trace_id=TRACE_ID_HEX,
    )
    event = GatewayStreamEvent(
        event_type=StreamEventType.RESPONSE_COMPLETED,
        request_id=REQUEST_ID,
        sequence_number=1,
        routing=_routing(),
        execution=execution,
    )

    payload = _event_payload(event)
    execution_payload = payload["execution"]
    assert isinstance(execution_payload, dict)
    assert execution_payload["trace_id"] == TRACE_ID_HEX
    assert _decode_event(payload).execution == execution


def test_legacy_terminal_payload_omits_absent_trace_id() -> None:
    event = GatewayStreamEvent(
        event_type=StreamEventType.RESPONSE_COMPLETED,
        request_id=REQUEST_ID,
        sequence_number=1,
        routing=_routing(),
        execution=_terminal_execution(),
    )

    payload = _event_payload(event)
    execution_payload = payload["execution"]
    assert isinstance(execution_payload, dict)
    assert "trace_id" not in execution_payload
    assert _decode_event(payload).execution == event.execution


@pytest.mark.parametrize(
    "trace_id",
    ["", "short", "A" * 32, "g" * 32, "1" * 31, "1" * 33],
)
def test_provider_execution_rejects_malformed_trace_id(trace_id: str) -> None:
    with pytest.raises(ValueError, match="trace_id must be a 32-character lowercase hex string"):
        ProviderExecution(
            provider="provider-a",
            model="model-a",
            deployment="deployment-a",
            status=ExecutionStatus.SUCCEEDED,
            latency_ms=1,
            trace_id=trace_id,
        )
