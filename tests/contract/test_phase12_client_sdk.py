import json
import os
import unittest
from collections.abc import Mapping
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

import httpx
from governed_llm_gateway_api.stream_generate import _event_payload
from governed_llm_gateway_client import GatewayClient, GatewayClientConfig
from governed_llm_gateway_client.errors import (
    GatewayConfigurationError,
    GatewayHTTPError,
    GatewayProtocolError,
    GatewayTransportError,
)
from governed_llm_gateway_contracts import (
    DataClassification,
    ExecutionStatus,
    GatewayStreamEvent,
    Message,
    MessageRole,
    PolicyProvenance,
    ProviderExecution,
    RiskLevel,
    RoutingProvenance,
    StreamEventType,
    Usage,
)

REQUEST_ID = UUID("33333333-3333-4333-8333-333333333333")
API_KEY = "gateway-test-secret"
BASE_URL = "https://gateway.example"


def _routing_contract() -> RoutingProvenance:
    return RoutingProvenance(
        routing_decision_id="sha256:" + "1" * 64,
        policy=PolicyProvenance(
            decision_id="policy-decision-1",
            policy_id="gateway-policy",
            policy_version="2.0.0",
            policy_digest="sha256:" + "2" * 64,
        ),
        authorized_model_group="agentic-strong",
        model_registry_digest="sha256:" + "3" * 64,
        ranking_policy_version="ranking-v2",
        ranking_policy_digest="sha256:" + "4" * 64,
        score_snapshot_id="ranking-input-v2",
        benchmark_snapshot_id="sha256:" + "5" * 64,
        score_provenance_mode="manual_override",
        manual_override_id="sha256:" + "6" * 64,
        provider="provider-a",
        model="model/a",
        deployment="candidate-a",
        fallback_sequence=("candidate-a",),
    )


def _routing_payload() -> dict[str, object]:
    routing = _routing_contract()
    return {
        "routing_decision_id": routing.routing_decision_id,
        "policy": {
            "decision_id": routing.policy.decision_id,
            "policy_id": routing.policy.policy_id,
            "policy_version": routing.policy.policy_version,
            "policy_digest": routing.policy.policy_digest,
        },
        "authorized_model_group": routing.authorized_model_group,
        "model_registry_digest": routing.model_registry_digest,
        "ranking_policy_version": routing.ranking_policy_version,
        "ranking_policy_digest": routing.ranking_policy_digest,
        "score_snapshot_id": routing.score_snapshot_id,
        "benchmark_snapshot_id": routing.benchmark_snapshot_id,
        "score_provenance_mode": routing.score_provenance_mode,
        "manual_override_id": routing.manual_override_id,
        "provider": routing.provider,
        "model": routing.model,
        "deployment": routing.deployment,
        "fallback_sequence": list(routing.fallback_sequence),
    }


def _sse(event_type: StreamEventType, sequence: int, **extra: object) -> str:
    payload: dict[str, object] = {
        "event_type": event_type.value,
        "request_id": str(REQUEST_ID),
        "sequence_number": sequence,
        **extra,
    }
    return (
        f"event: {event_type.value}\n"
        f"id: {sequence}\n"
        f"data: {json.dumps(payload, sort_keys=True, separators=(',', ':'))}\n\n"
    )


def _completed_stream() -> str:
    routing = _routing_payload()
    return "".join(
        (
            _sse(StreamEventType.RESPONSE_STARTED, 1, routing=routing),
            _sse(StreamEventType.CONTENT_DELTA, 2, delta="hello "),
            _sse(StreamEventType.CONTENT_DELTA, 3, delta="world"),
            _sse(
                StreamEventType.USAGE_COMPLETED,
                4,
                usage={"input_tokens": 10, "output_tokens": 2, "total_cost_usd": "0.01"},
            ),
            _sse(
                StreamEventType.RESPONSE_COMPLETED,
                5,
                routing=routing,
                execution={
                    "provider": "provider-a",
                    "model": "model/a",
                    "deployment": "candidate-a",
                    "status": "succeeded",
                    "latency_ms": 37,
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 2,
                        "total_cost_usd": "0.01",
                    },
                },
                finish_reason="stop",
            ),
        )
    )


def _failed_stream() -> str:
    routing = _routing_payload()
    return "".join(
        (
            _sse(StreamEventType.RESPONSE_STARTED, 1, routing=routing),
            _sse(StreamEventType.CONTENT_DELTA, 2, delta="partial"),
            _sse(
                StreamEventType.RESPONSE_FAILED,
                3,
                routing=routing,
                error={
                    "code": "provider_timeout",
                    "message": "provider timed out",
                    "retryable": True,
                },
                partial=True,
            ),
        )
    )


def _messages() -> tuple[Message, ...]:
    return (Message(role=MessageRole.USER, content="hello"),)


class GatewayClientConfigTests(unittest.TestCase):
    def test_config_is_https_normalized_and_repr_hides_key(self) -> None:
        config = GatewayClientConfig(base_url="https://gateway.example/", api_key=API_KEY)
        client = GatewayClient(config)
        self.addCleanup(lambda: None)

        self.assertEqual(config.base_url, BASE_URL)
        self.assertNotIn(API_KEY, repr(config))
        self.assertNotIn(API_KEY, repr(client))
        self.assertNotIn("api_key", vars(client))

    def test_config_rejects_unsafe_gateway_urls(self) -> None:
        invalid = (
            "http://gateway.example",
            "https://user:pass@gateway.example",
            "https://gateway.example?target=other",
            "https://gateway.example#fragment",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(GatewayConfigurationError):
                GatewayClientConfig(base_url=value, api_key=API_KEY)

    def test_from_env_fails_closed_when_connection_values_are_missing(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaises(GatewayConfigurationError),
        ):
            GatewayClient.from_env()


class GatewayClientTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_uses_gateway_only_and_preserves_phase11_provenance(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            self.assertEqual(str(request.url), f"{BASE_URL}/v1/generate")
            self.assertEqual(request.headers["X-Gateway-API-Key"], API_KEY)
            payload = json.loads(request.content)
            self.assertEqual(payload["workload"], "agent.orchestration")
            self.assertEqual(payload["risk_level"], "high")
            self.assertEqual(payload["data_classification"], "internal")
            self.assertTrue(payload["stream"])
            self.assertNotIn("provider", payload)
            self.assertNotIn("model", payload)
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream; charset=utf-8"},
                content=_completed_stream(),
                request=request,
            )

        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            response = await client.generate(
                workload="agent.orchestration",
                messages=_messages(),
                risk_level=RiskLevel.HIGH,
                data_classification=DataClassification.INTERNAL,
                request_id=REQUEST_ID,
            )

        self.assertEqual(calls, 1)
        self.assertEqual(response.status, ExecutionStatus.SUCCEEDED)
        self.assertEqual(response.content, "hello world")
        self.assertEqual(
            response.execution,
            ProviderExecution(
                provider="provider-a",
                model="model/a",
                deployment="candidate-a",
                status=ExecutionStatus.SUCCEEDED,
                latency_ms=37,
                usage=Usage(
                    input_tokens=10,
                    output_tokens=2,
                    total_cost_usd=Decimal("0.01"),
                ),
            ),
        )
        self.assertEqual(response.routing.benchmark_snapshot_id, "sha256:" + "5" * 64)
        self.assertEqual(response.routing.score_provenance_mode, "manual_override")
        self.assertEqual(response.routing.manual_override_id, "sha256:" + "6" * 64)

    async def test_failed_terminal_event_returns_failed_gateway_response(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_failed_stream(),
                request=request,
            )

        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            response = await client.generate(
                workload="agent.orchestration",
                messages=_messages(),
                risk_level=RiskLevel.HIGH,
                data_classification=DataClassification.INTERNAL,
                request_id=REQUEST_ID,
            )

        self.assertEqual(response.status, ExecutionStatus.FAILED)
        self.assertEqual(response.content, "partial")
        self.assertIsNotNone(response.error)
        assert response.error is not None
        self.assertEqual(response.error.code, "provider_timeout")
        self.assertTrue(response.error.retryable)

    async def test_transport_failure_is_not_retried_by_client(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ConnectError("simulated gateway outage", request=request)

        client = GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        )
        async with client:
            with self.assertRaises(GatewayTransportError):
                await client.generate(
                    workload="rag.answer",
                    messages=_messages(),
                    risk_level=RiskLevel.MEDIUM,
                    data_classification=DataClassification.PUBLIC,
                )

        self.assertEqual(calls, 1)

    async def test_http_error_uses_stable_code_without_raw_body_or_credential(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                403,
                json={
                    "detail": {
                        "code": "policy_denied",
                        "debug": API_KEY,
                    }
                },
                request=request,
            )

        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(GatewayHTTPError) as raised:
                await client.generate(
                    workload="rag.answer",
                    messages=_messages(),
                    risk_level=RiskLevel.HIGH,
                    data_classification=DataClassification.INTERNAL,
                )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.code, "policy_denied")
        self.assertNotIn(API_KEY, str(raised.exception))
        self.assertNotIn("debug", str(raised.exception))

    async def test_non_contiguous_sse_sequence_fails_closed(self) -> None:
        routing = _routing_payload()
        body = "".join(
            (
                _sse(StreamEventType.RESPONSE_STARTED, 1, routing=routing),
                _sse(StreamEventType.RESPONSE_COMPLETED, 3, routing=routing),
            )
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=body,
                request=request,
            )

        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(GatewayProtocolError):
                await client.generate(
                    workload="rag.answer",
                    messages=_messages(),
                    risk_level=RiskLevel.HIGH,
                    data_classification=DataClassification.INTERNAL,
                )

    async def test_oversized_sse_event_fails_closed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=b"x" * 65,
                request=request,
            )

        async with GatewayClient(
            GatewayClientConfig(
                base_url=BASE_URL,
                api_key=API_KEY,
                max_sse_event_bytes=64,
            ),
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(GatewayProtocolError):
                await client.generate(
                    workload="rag.answer",
                    messages=_messages(),
                    risk_level=RiskLevel.HIGH,
                    data_classification=DataClassification.INTERNAL,
                )


class Phase12ServerProvenanceTests(unittest.TestCase):
    def test_server_sse_payload_preserves_phase11_provenance(self) -> None:
        payload = _event_payload(
            GatewayStreamEvent(
                event_type=StreamEventType.RESPONSE_COMPLETED,
                request_id=REQUEST_ID,
                sequence_number=1,
                routing=_routing_contract(),
                finish_reason="stop",
            )
        )

        routing = payload["routing"]
        self.assertIsInstance(routing, Mapping)
        assert isinstance(routing, Mapping)
        self.assertEqual(routing["benchmark_snapshot_id"], "sha256:" + "5" * 64)
        self.assertEqual(routing["score_provenance_mode"], "manual_override")
        self.assertEqual(routing["manual_override_id"], "sha256:" + "6" * 64)
