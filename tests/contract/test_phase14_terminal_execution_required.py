"""Fail-closed SDK regression for missing terminal provider execution evidence."""

import asyncio
import json
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from governed_llm_gateway_api.stream_generate import _event_payload
from governed_llm_gateway_client import GatewayClient, GatewayClientConfig
from governed_llm_gateway_client.errors import GatewayProtocolError
from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayStreamEvent,
    Message,
    MessageRole,
    PolicyProvenance,
    RiskLevel,
    RoutingProvenance,
    StreamEventType,
    Usage,
)

REQUEST_ID = UUID("15151515-1515-4515-8515-151515151515")


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


def _sse(event: GatewayStreamEvent) -> str:
    payload = _event_payload(event)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"event: {event.event_type.value}\nid: {event.sequence_number}\ndata: {encoded}\n\n"


def test_generate_rejects_success_terminal_without_provider_execution_evidence() -> None:
    """Do not silently recreate execution evidence from routing or usage in the SDK."""
    routing = _routing()
    usage = Usage(
        input_tokens=9,
        output_tokens=4,
        total_cost_usd=Decimal("0.002"),
    )
    body = "".join(
        (
            _sse(
                GatewayStreamEvent(
                    event_type=StreamEventType.RESPONSE_STARTED,
                    request_id=REQUEST_ID,
                    sequence_number=1,
                    routing=routing,
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
                    routing=routing,
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

    async def generate() -> None:
        async with GatewayClient(
            GatewayClientConfig(
                base_url="https://gateway.example",
                api_key="test-secret",
            ),
            transport=httpx.MockTransport(handler),
        ) as client:
            with pytest.raises(GatewayProtocolError, match="missing execution evidence"):
                await client.generate(
                    workload="opslens.semantic-query.plan",
                    messages=(Message(role=MessageRole.USER, content="plan"),),
                    risk_level=RiskLevel.LOW,
                    data_classification=DataClassification.PUBLIC,
                    request_id=REQUEST_ID,
                )

    asyncio.run(generate())
