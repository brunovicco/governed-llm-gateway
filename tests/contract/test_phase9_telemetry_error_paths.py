import asyncio
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import cast
from uuid import UUID

from a2a_otel_kit import Observability, ObservabilitySettings
from fastapi import FastAPI, HTTPException
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
    GatewayRequest,
    GatewayStreamEvent,
    Message,
    MessageRole,
    PolicyProvenance,
    RiskLevel,
    RoutingProvenance,
)
from governed_llm_gateway_core.application.ranking import RankingDecision
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace.status import StatusCode

REQUEST_ID = UUID("88888888-8888-4888-8888-888888888888")
ERROR_SENTINEL = "phase9-unexpected-error-must-not-enter-telemetry"


def _observability() -> tuple[Observability, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    settings = ObservabilitySettings(
        service_name="governed-gateway-error-test",
        service_version="0.1.0",
        environment="test",
        enabled=False,
    )
    return (
        Observability(
            settings=settings,
            tracer=provider.get_tracer(settings.service_name, settings.service_version),
            lifecycle=None,
        ),
        exporter,
    )


def _payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": str(REQUEST_ID),
        "workload": "agent.orchestration",
        "risk_level": "medium",
        "data_classification": "public",
        "messages": [{"role": "user", "content": "safe test payload"}],
        "context_tokens_estimated": 10,
        "max_output_tokens": 32,
    }


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


def _prepared() -> PreparedStreamingExecution:
    request = GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        messages=(Message(role=MessageRole.USER, content="safe test payload"),),
    )
    decision = cast(RankingDecision, SimpleNamespace(routing=_routing()))
    return PreparedStreamingExecution(
        request=request,
        decision=decision,
        max_output_tokens=32,
        provider_timeout_seconds=1.0,
    )


def _telemetry_repr(exporter: InMemorySpanExporter) -> str:
    return repr(
        [
            (
                span.name,
                dict(span.attributes or {}),
                tuple((event.name, dict(event.attributes or {})) for event in span.events),
            )
            for span in exporter.get_finished_spans()
        ]
    )


class PreStreamFailureCoordinator:
    async def prepare(
        self,
        *,
        api_key: str,
        payload: GenerateRequestModel,
    ) -> PreparedStreamingExecution:
        del api_key, payload
        raise HTTPException(
            status_code=503,
            detail={"code": "forced_pre_stream_failure"},
        )


class UnexpectedStreamFailureCoordinator:
    async def stream(
        self,
        prepared: PreparedStreamingExecution,
    ) -> AsyncGenerator[GatewayStreamEvent]:
        del prepared
        if False:
            yield cast(GatewayStreamEvent, None)
        raise RuntimeError(ERROR_SENTINEL)


def test_gateway_request_span_records_sanitized_pre_stream_http_failure() -> None:
    observability, exporter = _observability()
    app = FastAPI()
    attach_generate_route(
        app,
        cast(GenerateCoordinator, PreStreamFailureCoordinator()),
        observability=observability,
    )

    response = TestClient(app).post(
        "/v1/generate",
        headers={"X-Gateway-API-Key": "gateway-key"},
        json=_payload(),
    )

    assert response.status_code == 503
    request_span = next(
        span for span in exporter.get_finished_spans() if span.name == "llm.gateway.request"
    )
    attributes = dict(request_span.attributes or {})
    assert attributes["http.status_code"] == 503
    assert attributes["error.type"] == "forced_pre_stream_failure"
    assert attributes["outcome"] == "failure"
    assert request_span.status.status_code is StatusCode.ERROR


def test_stream_span_records_category_without_unexpected_exception_message() -> None:
    observability, exporter = _observability()
    coordinator = cast(GenerateCoordinator, UnexpectedStreamFailureCoordinator())

    async def scenario() -> None:
        async for _ in _sse_body(
            coordinator,
            _prepared(),
            observability=observability,
        ):
            pass

    try:
        asyncio.run(scenario())
    except RuntimeError as exc:
        assert str(exc) == ERROR_SENTINEL
    else:
        raise AssertionError("expected the synthetic stream failure")

    stream_span = next(
        span for span in exporter.get_finished_spans() if span.name == "llm.gateway.stream"
    )
    attributes = dict(stream_span.attributes or {})
    assert attributes["error.type"] == "stream_unexpected_error"
    assert attributes["outcome"] == "failure"
    assert attributes["llm.partial"] is False
    assert stream_span.status.status_code is StatusCode.ERROR
    assert ERROR_SENTINEL not in _telemetry_repr(exporter)
