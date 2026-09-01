import asyncio
from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from governed_llm_gateway_api import (
    ClientAuthenticationError,
    GenerateCoordinator,
    GenerateRequestModel,
    PreparedStreamingExecution,
    attach_generate_route,
)
from governed_llm_gateway_api.stream_generate import (
    NoEligibleStreamingDeploymentError,
    _sse_body,
)
from governed_llm_gateway_contracts import (
    GatewayError,
    GatewayStreamEvent,
    PolicyProvenance,
    RoutingProvenance,
    StreamEventType,
    ToolCall,
    Usage,
)
from governed_llm_gateway_core.application import (
    PolicyDecisionError,
    PolicyDecisionErrorCode,
    PolicyProjectionError,
)
from governed_llm_gateway_core.application.ranking import RankingInvariantViolation
from governed_llm_gateway_core.domain.ranking import RankingPolicyError

REQUEST_ID = UUID("99999999-9999-4999-8999-999999999999")


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


def _payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": str(REQUEST_ID),
        "workload": "agent.orchestration",
        "risk_level": "medium",
        "data_classification": "public",
        "messages": [{"role": "user", "content": "hello"}],
        "context_tokens_estimated": 10,
        "max_output_tokens": 32,
    }


class FakeGenerateCoordinator:
    def __init__(self, *, prepare_error: Exception | None = None) -> None:
        self.prepare_error = prepare_error
        self.prepared_api_key: str | None = None
        self.stream_calls = 0
        self.closed = False

    async def prepare(
        self,
        *,
        api_key: str,
        payload: GenerateRequestModel,
    ) -> PreparedStreamingExecution:
        del payload
        self.prepared_api_key = api_key
        if self.prepare_error is not None:
            raise self.prepare_error
        return cast(PreparedStreamingExecution, object())

    async def stream(
        self,
        prepared: PreparedStreamingExecution,
    ) -> AsyncGenerator[GatewayStreamEvent]:
        del prepared
        self.stream_calls += 1
        try:
            routing = _routing()
            yield GatewayStreamEvent(
                event_type=StreamEventType.RESPONSE_STARTED,
                request_id=REQUEST_ID,
                sequence_number=1,
                routing=routing,
            )
            yield GatewayStreamEvent(
                event_type=StreamEventType.CONTENT_DELTA,
                request_id=REQUEST_ID,
                sequence_number=2,
                delta="hello",
            )
            yield GatewayStreamEvent(
                event_type=StreamEventType.USAGE_COMPLETED,
                request_id=REQUEST_ID,
                sequence_number=3,
                usage=Usage(input_tokens=10, output_tokens=2),
            )
            yield GatewayStreamEvent(
                event_type=StreamEventType.RESPONSE_COMPLETED,
                request_id=REQUEST_ID,
                sequence_number=4,
                routing=routing,
                finish_reason="stop",
            )
        finally:
            self.closed = True


def _app(fake: FakeGenerateCoordinator) -> FastAPI:
    app = FastAPI()
    attach_generate_route(app, cast(GenerateCoordinator, fake))
    return app


def test_generate_endpoint_returns_normalized_deterministic_sse() -> None:
    fake = FakeGenerateCoordinator()
    response = TestClient(_app(fake)).post(
        "/v1/generate",
        headers={"X-Gateway-API-Key": "gateway-key"},
        json=_payload(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert fake.prepared_api_key == "gateway-key"
    assert fake.stream_calls == 1
    assert fake.closed is True
    assert "event: response.started\nid: 1\ndata:" in response.text
    assert '"authorized_model_group":"agentic-strong"' in response.text
    assert "event: content.delta\nid: 2\ndata:" in response.text
    assert '"delta":"hello"' in response.text
    assert "event: usage.completed\nid: 3\ndata:" in response.text
    assert '"input_tokens":10' in response.text
    assert "event: response.completed\nid: 4\ndata:" in response.text
    assert '"finish_reason":"stop"' in response.text


def test_generate_authentication_failure_happens_before_streaming_response() -> None:
    fake = FakeGenerateCoordinator(prepare_error=ClientAuthenticationError("invalid credential"))
    response = TestClient(_app(fake)).post(
        "/v1/generate",
        headers={"X-Gateway-API-Key": "bad-key"},
        json=_payload(),
    )

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "invalid_gateway_credential"}}
    assert fake.stream_calls == 0


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (
            NoEligibleStreamingDeploymentError("none"),
            503,
            "no_eligible_streaming_deployment",
        ),
        (RankingPolicyError("bad policy"), 503, "ranking_policy_unavailable"),
        (RankingInvariantViolation("bad boundary"), 503, "ranking_invariant_violation"),
        (PolicyProjectionError("bad projection"), 422, "invalid_generation_request"),
        (
            PolicyDecisionError(
                code=PolicyDecisionErrorCode.AUTHORIZATION,
                message="denied",
                retryable=False,
            ),
            403,
            "policy_denied",
        ),
    ],
)
def test_generate_pre_stream_failures_keep_normal_http_semantics(
    error: Exception,
    status: int,
    code: str,
) -> None:
    fake = FakeGenerateCoordinator(prepare_error=error)
    response = TestClient(_app(fake)).post(
        "/v1/generate",
        headers={"X-Gateway-API-Key": "gateway-key"},
        json=_payload(),
    )

    assert response.status_code == status
    assert response.json() == {"detail": {"code": code}}
    assert fake.stream_calls == 0


def test_generate_request_forces_streaming_and_validates_tools_before_execution() -> None:
    payload = GenerateRequestModel.model_validate(
        {
            **_payload(),
            "requirements": {"tool_calling": True},
            "tools": [
                {
                    "name": "lookup_account",
                    "description": "Look up an account.",
                    "input_schema": {
                        "type": "object",
                        "properties": {"account_id": {"type": "string"}},
                        "required": ["account_id"],
                        "additionalProperties": False,
                    },
                }
            ],
        }
    )

    request = payload.to_gateway_request()

    assert request.requirements.streaming is True
    assert request.requirements.tool_calling is True
    assert request.tools[0].name == "lookup_account"


def test_generate_request_rejects_tool_result_continuation_before_sse_begins() -> None:
    payload = GenerateRequestModel.model_validate(
        {
            **_payload(),
            "messages": [{"role": "tool", "content": "opaque result"}],
        }
    )

    with pytest.raises(ValueError, match="tool-result continuation"):
        payload.to_gateway_request()


def test_generate_request_rejects_remote_schema_reference_before_sse_begins() -> None:
    payload = GenerateRequestModel.model_validate(
        {
            **_payload(),
            "requirements": {"structured_output": True},
            "structured_output": {
                "name": "answer",
                "schema": {
                    "type": "object",
                    "properties": {
                        "value": {"$ref": "https://schemas.example/value.json"},
                    },
                },
            },
        }
    )

    with pytest.raises(ValueError):
        payload.to_gateway_request()


def test_generate_sse_serializes_tool_usage_cost_and_partial_failure_metadata() -> None:
    routing = _routing()
    tool_event = GatewayStreamEvent(
        event_type=StreamEventType.TOOL_CALL_COMPLETED,
        request_id=REQUEST_ID,
        sequence_number=1,
        tool_call=ToolCall(
            call_id="call-1",
            name="lookup_account",
            arguments={"account_id": "123"},
        ),
    )
    usage_event = GatewayStreamEvent(
        event_type=StreamEventType.USAGE_COMPLETED,
        request_id=REQUEST_ID,
        sequence_number=2,
        usage=Usage(
            input_tokens=10,
            output_tokens=2,
            total_cost_usd=Decimal("0.000012"),
        ),
    )
    failure_event = GatewayStreamEvent(
        event_type=StreamEventType.RESPONSE_FAILED,
        request_id=REQUEST_ID,
        sequence_number=3,
        routing=routing,
        error=GatewayError(code="timeout", message="stream failed", retryable=False),
        partial=True,
    )

    from governed_llm_gateway_api.stream_generate import _encode_sse

    tool_sse = _encode_sse(tool_event)
    usage_sse = _encode_sse(usage_event)
    failure_sse = _encode_sse(failure_event)

    assert '"call_id":"call-1"' in tool_sse
    assert '"arguments":{"account_id":"123"}' in tool_sse
    assert '"total_cost_usd":"0.000012"' in usage_sse
    assert '"partial":true' in failure_sse
    assert '"retryable":false' in failure_sse


def test_sse_body_close_propagates_to_execution_generator() -> None:
    fake = FakeGenerateCoordinator()

    async def scenario() -> None:
        body = _sse_body(
            cast(GenerateCoordinator, fake),
            cast(PreparedStreamingExecution, object()),
        )
        first = await anext(body)
        assert first.startswith("event: response.started\n")
        await body.aclose()

    asyncio.run(scenario())

    assert fake.stream_calls == 1
    assert fake.closed is True
