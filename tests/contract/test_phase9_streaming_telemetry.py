from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import cast
from uuid import UUID

from a2a_otel_kit import Observability, ObservabilitySettings
from fastapi import FastAPI
from fastapi.testclient import TestClient
from governed_llm_gateway_api import (
    GenerateCoordinator,
    GenerateRequestModel,
    PreparedStreamingExecution,
    attach_generate_route,
)
from governed_llm_gateway_api.stream_generate import _sse_body
from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayError,
    GatewayRequest,
    GatewayStreamEvent,
    Message,
    MessageRole,
    PolicyProvenance,
    RiskLevel,
    RoutingProvenance,
    StreamEventType,
    Usage,
)
from governed_llm_gateway_core.application.ranking import RankingDecision
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace.status import StatusCode

REQUEST_ID = UUID("77777777-7777-4777-8777-777777777777")
PROMPT_SENTINEL = "phase9-prompt-must-not-enter-telemetry"
COMPLETION_SENTINEL = "phase9-completion-must-not-enter-telemetry"
ERROR_SENTINEL = "phase9-remote-error-body-must-not-enter-telemetry"
TRACE_ID_HEX = "1234567890abcdef1234567890abcdef"
TRACEPARENT = f"00-{TRACE_ID_HEX}-1234567890abcdef-01"


def _observability() -> tuple[Observability, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    settings = ObservabilitySettings(
        service_name="governed-gateway-stream-test",
        service_version="0.1.0",
        environment="test",
        enabled=False,
    )
    observability = Observability(
        settings=settings,
        tracer=provider.get_tracer(settings.service_name, settings.service_version),
        lifecycle=None,
    )
    return observability, exporter


def _routing() -> RoutingProvenance:
    return RoutingProvenance(
        routing_decision_id="sha256:" + "b" * 64,
        policy=PolicyProvenance(
            decision_id="policy-decision",
            policy_id="gateway-policy",
            policy_version="1.0.0",
            policy_digest="sha256:" + "a" * 64,
        ),
        authorized_model_group="agentic-strong",
        model_registry_digest="c" * 64,
        ranking_policy_version="ranking-v1",
        ranking_policy_digest="d" * 64,
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
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        messages=(Message(role=MessageRole.USER, content=PROMPT_SENTINEL),),
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
        "workload": "agent.orchestration",
        "risk_level": "medium",
        "data_classification": "public",
        "messages": [{"role": "user", "content": PROMPT_SENTINEL}],
        "context_tokens_estimated": 10,
        "max_output_tokens": 32,
    }


def _success_events() -> tuple[GatewayStreamEvent, ...]:
    routing = _routing()
    return (
        GatewayStreamEvent(
            event_type=StreamEventType.RESPONSE_STARTED,
            request_id=REQUEST_ID,
            sequence_number=1,
            routing=routing,
        ),
        GatewayStreamEvent(
            event_type=StreamEventType.CONTENT_DELTA,
            request_id=REQUEST_ID,
            sequence_number=2,
            delta=COMPLETION_SENTINEL,
        ),
        GatewayStreamEvent(
            event_type=StreamEventType.USAGE_COMPLETED,
            request_id=REQUEST_ID,
            sequence_number=3,
            usage=Usage(input_tokens=11, output_tokens=3),
        ),
        GatewayStreamEvent(
            event_type=StreamEventType.RESPONSE_COMPLETED,
            request_id=REQUEST_ID,
            sequence_number=4,
            routing=routing,
            finish_reason="stop",
        ),
    )


class TelemetryGenerateCoordinator:
    def __init__(
        self,
        prepared: PreparedStreamingExecution,
        events: tuple[GatewayStreamEvent, ...],
    ) -> None:
        self.prepared = prepared
        self.events = events
        self.api_key: str | None = None
        self.closed = False

    async def prepare(
        self,
        *,
        api_key: str,
        payload: GenerateRequestModel,
    ) -> PreparedStreamingExecution:
        del payload
        self.api_key = api_key
        return self.prepared

    async def stream(
        self,
        prepared: PreparedStreamingExecution,
    ) -> AsyncGenerator[GatewayStreamEvent]:
        del prepared
        try:
            for event in self.events:
                yield event
        finally:
            self.closed = True


def _telemetry_repr(exporter: InMemorySpanExporter) -> str:
    material: list[object] = []
    for span in exporter.get_finished_spans():
        material.append(
            (
                span.name,
                dict(span.attributes or {}),
                tuple((event.name, dict(event.attributes or {})) for event in span.events),
            )
        )
    return repr(material)


def test_generate_telemetry_continues_trace_and_exports_metadata_only() -> None:
    observability, exporter = _observability()
    fake = TelemetryGenerateCoordinator(_prepared(), _success_events())
    app = FastAPI()
    attach_generate_route(
        app,
        cast(GenerateCoordinator, fake),
        observability=observability,
    )

    response = TestClient(app).post(
        "/v1/generate",
        headers={
            "X-Gateway-API-Key": "gateway-key",
            "traceparent": TRACEPARENT,
        },
        json=_payload(),
    )

    assert response.status_code == 200
    assert COMPLETION_SENTINEL in response.text
    assert fake.api_key == "gateway-key"
    assert fake.closed is True

    spans = exporter.get_finished_spans()
    request_span = next(span for span in spans if span.name == "llm.gateway.request")
    stream_span = next(span for span in spans if span.name == "llm.gateway.stream")
    expected_trace_id = int(TRACE_ID_HEX, 16)
    assert request_span.context.trace_id == expected_trace_id
    assert stream_span.context.trace_id == expected_trace_id
    assert stream_span.parent is not None
    assert stream_span.parent.span_id == request_span.context.span_id

    request_attributes = dict(request_span.attributes or {})
    stream_attributes = dict(stream_span.attributes or {})
    assert request_attributes["llm.workload"] == "agent.orchestration"
    assert request_attributes["routing.policy_id"] == "gateway-policy"
    assert request_attributes["outcome"] == "success"
    assert stream_attributes["llm.input_tokens"] == 11
    assert stream_attributes["llm.output_tokens"] == 3
    assert stream_attributes["llm.provider"] == "provider-a"
    assert stream_attributes["outcome"] == "success"
    assert stream_span.status.status_code is StatusCode.OK

    serialized = _telemetry_repr(exporter)
    assert PROMPT_SENTINEL not in serialized
    assert COMPLETION_SENTINEL not in serialized


def test_stream_failure_records_category_and_partial_without_remote_message() -> None:
    observability, exporter = _observability()
    routing = _routing()
    failure = GatewayStreamEvent(
        event_type=StreamEventType.RESPONSE_FAILED,
        request_id=REQUEST_ID,
        sequence_number=2,
        routing=routing,
        error=GatewayError(
            code="provider_timeout",
            message=ERROR_SENTINEL,
            retryable=False,
        ),
        partial=True,
    )
    fake = TelemetryGenerateCoordinator(
        _prepared(),
        (
            GatewayStreamEvent(
                event_type=StreamEventType.RESPONSE_STARTED,
                request_id=REQUEST_ID,
                sequence_number=1,
                routing=routing,
            ),
            failure,
        ),
    )

    async def scenario() -> list[str]:
        chunks: list[str] = []
        async for chunk in _sse_body(
            cast(GenerateCoordinator, fake),
            fake.prepared,
            observability=observability,
        ):
            chunks.append(chunk)
        return chunks

    import asyncio

    chunks = asyncio.run(scenario())

    assert any("event: response.failed" in chunk for chunk in chunks)
    stream_span = next(
        span for span in exporter.get_finished_spans() if span.name == "llm.gateway.stream"
    )
    attributes = dict(stream_span.attributes or {})
    assert attributes["llm.partial"] is True
    assert attributes["outcome"] == "failure"
    assert attributes["error.type"] == "provider_timeout"
    assert stream_span.status.status_code is StatusCode.ERROR
    assert ERROR_SENTINEL not in _telemetry_repr(exporter)
