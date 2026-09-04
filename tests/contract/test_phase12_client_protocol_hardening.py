import json
import os
import unittest
from collections.abc import AsyncIterator
from unittest.mock import patch
from uuid import UUID

import httpx
from governed_llm_gateway_client import GatewayClient, GatewayClientConfig
from governed_llm_gateway_client.errors import (
    GatewayHTTPError,
    GatewayProtocolError,
)
from governed_llm_gateway_contracts import (
    DataClassification,
    Message,
    MessageRole,
    RiskLevel,
    StreamEventType,
)

BASE_URL = "https://gateway.example"
API_KEY = "gateway-test-secret"
REQUEST_ID = UUID("44444444-4444-4444-8444-444444444444")
OTHER_REQUEST_ID = UUID("55555555-5555-4555-8555-555555555555")


class _ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


def _messages() -> tuple[Message, ...]:
    return (Message(role=MessageRole.USER, content="hello"),)


def _routing_payload() -> dict[str, object]:
    return {
        "routing_decision_id": "sha256:" + "1" * 64,
        "policy": {
            "decision_id": "policy-decision-1",
            "policy_id": "gateway-policy",
            "policy_version": "2.0.0",
            "policy_digest": "sha256:" + "2" * 64,
        },
        "authorized_model_group": "agentic-strong",
        "model_registry_digest": "sha256:" + "3" * 64,
        "ranking_policy_version": "ranking-v2",
        "ranking_policy_digest": "sha256:" + "4" * 64,
        "score_snapshot_id": "ranking-input-v2",
        "benchmark_snapshot_id": "sha256:" + "5" * 64,
        "score_provenance_mode": "benchmark_hybrid",
        "provider": "provider-a",
        "model": "model/a",
        "deployment": "candidate-a",
        "rejected_candidates": [],
        "fallback_sequence": ["candidate-a"],
    }


def _sse(
    event_type: StreamEventType,
    sequence: int,
    *,
    request_id: UUID = REQUEST_ID,
    **extra: object,
) -> str:
    payload: dict[str, object] = {
        "event_type": event_type.value,
        "request_id": str(request_id),
        "sequence_number": sequence,
        **extra,
    }
    return (
        f"event: {event_type.value}\n"
        f"id: {sequence}\n"
        f"data: {json.dumps(payload, sort_keys=True, separators=(',', ':'))}\n\n"
    )


def _response(
    request: httpx.Request,
    body: str,
    *,
    content_type: str = "text/event-stream",
) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": content_type},
        content=body,
        request=request,
    )


async def _generate(client: GatewayClient) -> None:
    await client.generate(
        workload="rag.answer",
        messages=_messages(),
        risk_level=RiskLevel.HIGH,
        data_classification=DataClassification.INTERNAL,
        request_id=REQUEST_ID,
    )


class GatewayClientProtocolHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_event_request_id_must_match_sent_request(self) -> None:
        routing = _routing_payload()
        body = "".join(
            (
                _sse(
                    StreamEventType.RESPONSE_STARTED,
                    1,
                    request_id=OTHER_REQUEST_ID,
                    routing=routing,
                ),
                _sse(
                    StreamEventType.RESPONSE_COMPLETED,
                    2,
                    request_id=OTHER_REQUEST_ID,
                    routing=routing,
                ),
            )
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return _response(request, body)

        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(GatewayProtocolError):
                await _generate(client)

    async def test_mixed_request_ids_fail_closed(self) -> None:
        routing = _routing_payload()
        body = "".join(
            (
                _sse(StreamEventType.RESPONSE_STARTED, 1, routing=routing),
                _sse(
                    StreamEventType.RESPONSE_COMPLETED,
                    2,
                    request_id=OTHER_REQUEST_ID,
                    routing=routing,
                ),
            )
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return _response(request, body)

        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(GatewayProtocolError):
                await _generate(client)

    async def test_eof_before_terminal_event_fails_closed(self) -> None:
        body = _sse(StreamEventType.RESPONSE_STARTED, 1, routing=_routing_payload())

        def handler(request: httpx.Request) -> httpx.Response:
            return _response(request, body)

        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(GatewayProtocolError):
                await _generate(client)

    async def test_event_after_terminal_event_fails_closed(self) -> None:
        routing = _routing_payload()
        body = "".join(
            (
                _sse(StreamEventType.RESPONSE_STARTED, 1, routing=routing),
                _sse(StreamEventType.RESPONSE_COMPLETED, 2, routing=routing),
                _sse(StreamEventType.CONTENT_DELTA, 3, delta="unexpected"),
            )
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return _response(request, body)

        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(GatewayProtocolError):
                await _generate(client)

    async def test_duplicate_json_key_fails_closed(self) -> None:
        body = (
            "event: response.started\n"
            "id: 1\n"
            'data: {"event_type":"response.started","event_type":"response.completed",'
            f'"request_id":"{REQUEST_ID}","sequence_number":1}}\n\n'
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return _response(request, body)

        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(GatewayProtocolError):
                await _generate(client)

    async def test_non_sse_content_type_fails_closed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _response(request, "{}", content_type="application/json")

        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(GatewayProtocolError):
                await _generate(client)

    async def test_encoded_sse_response_fails_before_body_decode(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["Accept-Encoding"], "identity")
            return httpx.Response(
                200,
                headers={
                    "content-type": "text/event-stream",
                    "content-encoding": "gzip",
                },
                content=_sse(
                    StreamEventType.RESPONSE_COMPLETED,
                    1,
                    routing=_routing_payload(),
                ),
                request=request,
            )

        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(GatewayProtocolError):
                await _generate(client)

    async def test_total_stream_size_limit_applies_without_content_length(self) -> None:
        routing = _routing_payload()
        events = [_sse(StreamEventType.RESPONSE_STARTED, 1, routing=routing)]
        for sequence in range(2, 8):
            events.append(
                _sse(
                    StreamEventType.CONTENT_DELTA,
                    sequence,
                    delta="x" * 450,
                )
            )
        events.append(_sse(StreamEventType.RESPONSE_COMPLETED, 8, routing=routing))
        body = "".join(events).encode()
        self.assertGreater(len(body), 2500)
        chunks = tuple(body[index : index + 256] for index in range(0, len(body), 256))

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=_ChunkedStream(chunks),
                request=request,
            )

        async with GatewayClient(
            GatewayClientConfig(
                base_url=BASE_URL,
                api_key=API_KEY,
                max_sse_event_bytes=2048,
                max_sse_stream_bytes=2500,
            ),
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(GatewayProtocolError):
                await _generate(client)

    async def test_redirect_is_not_followed_and_gateway_key_is_not_exposed(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(
                307,
                headers={"location": "https://attacker.example/collect"},
                request=request,
            )

        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(GatewayHTTPError) as raised:
                await _generate(client)

        self.assertEqual(calls, [f"{BASE_URL}/v1/generate"])
        self.assertEqual(raised.exception.status_code, 307)
        self.assertNotIn(API_KEY, str(raised.exception))
        self.assertNotIn("attacker.example", str(raised.exception))

    async def test_oversized_http_error_body_is_not_exposed(self) -> None:
        sensitive_code = "sensitive-provider-detail"
        oversized_body = json.dumps(
            {
                "detail": {"code": sensitive_code},
                "padding": "x" * (70 * 1024),
            }
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(502, content=oversized_body, request=request)

        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(GatewayHTTPError) as raised:
                await _generate(client)

        self.assertEqual(raised.exception.code, "http_status_502")
        self.assertNotIn(sensitive_code, str(raised.exception))

    async def test_encoded_http_error_body_is_not_decoded_or_exposed(self) -> None:
        sensitive_code = "compressed-sensitive-detail"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                502,
                headers={"content-encoding": "gzip"},
                json={"detail": {"code": sensitive_code}},
                request=request,
            )

        async with GatewayClient(
            GatewayClientConfig(base_url=BASE_URL, api_key=API_KEY),
            transport=httpx.MockTransport(handler),
        ) as client:
            with self.assertRaises(GatewayHTTPError) as raised:
                await _generate(client)

        self.assertEqual(raised.exception.code, "http_status_502")
        self.assertNotIn(sensitive_code, str(raised.exception))

    async def test_from_env_builds_gateway_only_configuration(self) -> None:
        with patch.dict(
            os.environ,
            {
                "GOVERNED_LLM_GATEWAY_URL": BASE_URL,
                "GOVERNED_LLM_GATEWAY_API_KEY": API_KEY,
            },
            clear=True,
        ):
            transport = httpx.MockTransport(lambda request: httpx.Response(500, request=request))
            client = GatewayClient.from_env(transport=transport)

        try:
            self.assertEqual(client.base_url, BASE_URL)
            self.assertNotIn(API_KEY, repr(client))
        finally:
            await client.aclose()
