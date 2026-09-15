"""Agent protocol adapters must preserve compatibility without acquiring routing authority."""

import json
import unittest
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from governed_llm_gateway_api.anthropic_messages_ingress import attach_anthropic_messages_route
from governed_llm_gateway_api.application import create_gateway_app
from governed_llm_gateway_api.openai_responses_ingress import attach_openai_responses_route
from governed_llm_gateway_api.protocol_common import ProtocolGenerationPayload
from governed_llm_gateway_api.route_explain import RouteExplainCoordinator
from governed_llm_gateway_api.stream_generate import GenerateCoordinator, PreparedStreamingExecution
from governed_llm_gateway_contracts import (
    Capability,
    ClientProtocol,
    DataClassification,
    ExecutionStatus,
    GatewayError,
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
    ToolCall,
    ToolResultBlock,
    Usage,
    WorkloadRequirements,
)
from governed_llm_gateway_core.application.ranking import (
    RankedCandidate,
    RankingDecision,
    ScoreBreakdown,
)
from governed_llm_gateway_core.domain.model_registry import ModelDeployment, PricingMetadata

REQUEST_ID = UUID("77777777-7777-4777-8777-777777777777")
CREDENTIAL = "protocol-gateway-credential"


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
        model="provider-a/model-a",
        deployment="deployment-a",
    )


def _prepared() -> PreparedStreamingExecution:
    deployment = ModelDeployment(
        deployment_id="deployment-a",
        provider="provider-a",
        model_id="provider-a/model-a",
        model_group="agentic-strong",
        api_family="openai-responses",
        capabilities=frozenset({Capability.TEXT, Capability.TOOL_CALLING, Capability.STREAMING}),
        context_tokens=128_000,
        modalities=frozenset({Modality.TEXT}),
        pricing=PricingMetadata(
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("2"),
            source_date=date(2026, 9, 15),
            snapshot_version="pricing-v1",
        ),
        max_data_classification=DataClassification.INTERNAL,
        allowed_environments=frozenset({"development"}),
        enabled=True,
        source_date=date(2026, 9, 15),
        catalog_version="catalog-v1",
    )
    candidate = RankedCandidate(
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
    )
    request = GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="agent.tool-use",
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(streaming=True),
        messages=(Message(role=MessageRole.USER, content="hello"),),
    )
    return PreparedStreamingExecution(
        request=request,
        decision=RankingDecision(
            routing=_routing(),
            ranking_policy_digest="d" * 64,
            score_snapshot_id="static-v1",
            selected=candidate,
            alternatives=(),
            rejected_candidates=(),
        ),
        max_output_tokens=64,
        provider_timeout_seconds=1.0,
    )


def _execution() -> ProviderExecution:
    return ProviderExecution(
        provider="provider-a",
        model="provider-a/model-a",
        deployment="deployment-a",
        status=ExecutionStatus.SUCCEEDED,
        latency_ms=5,
    )


def _events(*, tool: bool = False) -> tuple[GatewayStreamEvent, ...]:
    events: list[GatewayStreamEvent] = [
        GatewayStreamEvent(
            event_type=StreamEventType.RESPONSE_STARTED,
            request_id=REQUEST_ID,
            sequence_number=1,
            routing=_routing(),
        )
    ]
    sequence = 2
    if tool:
        call = ToolCall(call_id="call-1", name="lookup", arguments={"id": "42"})
        events.extend(
            [
                GatewayStreamEvent(
                    event_type=StreamEventType.TOOL_CALL_STARTED,
                    request_id=REQUEST_ID,
                    sequence_number=sequence,
                    tool_call_id=call.call_id,
                    tool_name=call.name,
                ),
                GatewayStreamEvent(
                    event_type=StreamEventType.TOOL_CALL_ARGUMENTS_DELTA,
                    request_id=REQUEST_ID,
                    sequence_number=sequence + 1,
                    tool_call_id=call.call_id,
                    delta='{"id":"42"}',
                ),
                GatewayStreamEvent(
                    event_type=StreamEventType.TOOL_CALL_COMPLETED,
                    request_id=REQUEST_ID,
                    sequence_number=sequence + 2,
                    tool_call=call,
                ),
            ]
        )
        sequence += 3
    else:
        events.append(
            GatewayStreamEvent(
                event_type=StreamEventType.CONTENT_DELTA,
                request_id=REQUEST_ID,
                sequence_number=sequence,
                delta="governed response",
            )
        )
        sequence += 1
    events.extend(
        [
            GatewayStreamEvent(
                event_type=StreamEventType.USAGE_COMPLETED,
                request_id=REQUEST_ID,
                sequence_number=sequence,
                usage=Usage(input_tokens=9, output_tokens=3),
            ),
            GatewayStreamEvent(
                event_type=StreamEventType.RESPONSE_COMPLETED,
                request_id=REQUEST_ID,
                sequence_number=sequence + 1,
                routing=_routing(),
                execution=_execution(),
                finish_reason="tool_calls" if tool else "stop",
            ),
        ]
    )
    return tuple(events)


class RecordingCoordinator:
    """Capture the protocol translation and replay a deterministic canonical stream."""

    def __init__(self, events: tuple[GatewayStreamEvent, ...] | None = None) -> None:
        self.payloads: list[ProtocolGenerationPayload] = []
        self.keys: list[str] = []
        self.events = events or _events()

    async def prepare(
        self,
        *,
        api_key: str,
        payload: ProtocolGenerationPayload,
    ) -> PreparedStreamingExecution:
        self.keys.append(api_key)
        self.payloads.append(payload)
        return _prepared()

    async def stream(
        self,
        prepared: PreparedStreamingExecution,
    ) -> AsyncGenerator[GatewayStreamEvent]:
        del prepared
        for event in self.events:
            yield event


def _client(protocol: str, coordinator: RecordingCoordinator) -> TestClient:
    app = FastAPI()
    if protocol == "anthropic":
        attach_anthropic_messages_route(app, coordinator)  # type: ignore[arg-type]
    else:
        attach_openai_responses_route(app, coordinator)  # type: ignore[arg-type]
    return TestClient(app)


def _sse_events(text: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    event_name: str | None = None
    for line in text.splitlines():
        if line.startswith("event: "):
            event_name = line.removeprefix("event: ")
        elif line.startswith("data: ") and event_name is not None:
            events.append((event_name, json.loads(line.removeprefix("data: "))))
            event_name = None
    return events


class AnthropicIngressTests(unittest.TestCase):
    def test_non_streaming_message_uses_alias_and_same_governed_payload(self) -> None:
        coordinator = RecordingCoordinator()
        response = _client("anthropic", coordinator).post(
            "/v1/messages",
            headers={
                "Authorization": f"Bearer {CREDENTIAL}",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-client-alias",
                "max_tokens": 50,
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model"], "claude-client-alias")
        self.assertEqual(response.json()["content"][0]["text"], "governed response")
        self.assertEqual(response.json()["usage"]["input_tokens"], 9)
        self.assertEqual(coordinator.keys, [CREDENTIAL])
        request = coordinator.payloads[0].to_gateway_request()
        self.assertEqual(request.workload, "agent.tool-use")
        self.assertIs(request.client_protocol, ClientProtocol.ANTHROPIC_MESSAGES)
        self.assertFalse(hasattr(request, "model"))
        self.assertIn("request-id", response.headers)
        self.assertEqual(response.headers["x-gateway-model-group"], "agentic-strong")
        self.assertEqual(response.headers["x-gateway-policy-id"], "gateway-policy")
        self.assertNotIn("x_gateway", response.json())

    def test_tool_transcript_is_correlated_and_capability_gated(self) -> None:
        coordinator = RecordingCoordinator(_events(tool=True))
        response = _client("anthropic", coordinator).post(
            "/v1/messages",
            headers={"x-api-key": CREDENTIAL, "anthropic-version": "2023-06-01"},
            json={
                "model": "governed-agent",
                "max_tokens": 50,
                "tools": [
                    {
                        "name": "lookup",
                        "description": "Look up one record",
                        "input_schema": {
                            "type": "object",
                            "properties": {"id": {"type": "string"}},
                            "required": ["id"],
                            "additionalProperties": False,
                        },
                    }
                ],
                "messages": [
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "call-1",
                                "name": "lookup",
                                "input": {"id": "42"},
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "call-1",
                                "content": "found",
                            }
                        ],
                    },
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        request = coordinator.payloads[0].to_gateway_request()
        self.assertTrue(request.requirements.tool_calling)
        self.assertTrue(
            any(
                isinstance(block, ToolResultBlock)
                for message in request.messages
                for block in message.canonical_blocks
            )
        )
        self.assertEqual(response.json()["stop_reason"], "tool_use")

    def test_stream_uses_messages_event_sequence_without_done_sentinel(self) -> None:
        response = _client("anthropic", RecordingCoordinator()).post(
            "/v1/messages",
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
            json={
                "model": "governed-agent",
                "max_tokens": 50,
                "stream": True,
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

        names = [name for name, _ in _sse_events(response.text)]
        self.assertEqual(
            names,
            [
                "message_start",
                "content_block_start",
                "content_block_delta",
                "content_block_stop",
                "message_delta",
                "message_stop",
            ],
        )
        self.assertNotIn("[DONE]", response.text)

    def test_conflicting_credentials_fail_before_governed_prepare(self) -> None:
        coordinator = RecordingCoordinator()
        response = _client("anthropic", coordinator).post(
            "/v1/messages",
            headers={"Authorization": f"Bearer {CREDENTIAL}", "x-api-key": "different"},
            json={
                "model": "governed-agent",
                "max_tokens": 50,
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["type"], "invalid_request_error")
        self.assertFalse(coordinator.payloads)


class OpenAIResponsesIngressTests(unittest.TestCase):
    def test_non_streaming_response_uses_alias_without_gateway_extensions(self) -> None:
        coordinator = RecordingCoordinator()
        response = _client("openai", coordinator).post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
            json={"model": "codex-client-alias", "input": "hello", "store": False},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["object"], "response")
        self.assertEqual(body["model"], "codex-client-alias")
        self.assertEqual(body["output_text"], "governed response")
        self.assertNotIn("x_gateway", body)
        self.assertIn("x-request-id", response.headers)
        self.assertEqual(response.headers["x-gateway-model-group"], "agentic-strong")
        self.assertEqual(coordinator.payloads[0].workload, "agent.tool-use")
        self.assertIs(
            coordinator.payloads[0].request.client_protocol,
            ClientProtocol.OPENAI_RESPONSES,
        )

    def test_workload_header_is_policy_input_but_model_is_not(self) -> None:
        coordinator = RecordingCoordinator()
        _client("openai", coordinator).post(
            "/v1/responses",
            headers={
                "Authorization": f"Bearer {CREDENTIAL}",
                "X-Gateway-Workload": "code.generate",
            },
            json={"model": "gpt-provider-looking-alias", "input": "hello"},
        )

        request = coordinator.payloads[0].to_gateway_request()
        self.assertEqual(request.workload, "code.generate")
        self.assertFalse(hasattr(request, "model"))

    def test_stream_uses_responses_events_and_sequence_numbers(self) -> None:
        response = _client("openai", RecordingCoordinator()).post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
            json={"model": "governed-agent", "input": "hello", "stream": True},
        )

        events = _sse_events(response.text)
        names = [name for name, _ in events]
        self.assertEqual(names[0], "response.created")
        self.assertIn("response.output_text.delta", names)
        self.assertIn("response.content_part.done", names)
        self.assertIn("response.output_item.done", names)
        self.assertEqual(names[-1], "response.completed")
        added = next(payload for name, payload in events if name == "response.output_item.added")
        done = next(payload for name, payload in events if name == "response.output_item.done")
        self.assertEqual(added["item"]["id"], done["item"]["id"])
        self.assertEqual(
            [payload["sequence_number"] for _, payload in events],
            list(range(1, len(events) + 1)),
        )

    def test_stream_tool_call_finishes_item_before_response(self) -> None:
        response = _client("openai", RecordingCoordinator(_events(tool=True))).post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
            json={
                "model": "governed-agent",
                "input": "look up the record",
                "stream": True,
                "tools": [
                    {
                        "type": "function",
                        "name": "lookup",
                        "description": "Look up one record",
                        "parameters": {
                            "type": "object",
                            "properties": {"id": {"type": "string"}},
                            "required": ["id"],
                            "additionalProperties": False,
                        },
                        "strict": True,
                    }
                ],
            },
        )

        events = _sse_events(response.text)
        names = [name for name, _ in events]
        self.assertLess(
            names.index("response.function_call_arguments.done"),
            names.index("response.output_item.done"),
        )
        completed = events[-1][1]["response"]
        done_item = next(payload["item"] for name, payload in events if name.endswith("item.done"))
        self.assertEqual(completed["output"], [done_item])

    def test_audio_is_represented_and_requires_explicit_audio_capability(self) -> None:
        coordinator = RecordingCoordinator()
        response = _client("openai", coordinator).post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
            json={
                "model": "governed-agent",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {"format": "wav", "data": "aGVsbG8="},
                            }
                        ],
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        request = coordinator.payloads[0].to_gateway_request()
        self.assertTrue(request.requirements.audio)

    def test_current_codex_request_shape_is_accepted_without_routing_authority(self) -> None:
        coordinator = RecordingCoordinator()
        response = _client("openai", coordinator).post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
            json={
                "model": "codex-client-alias",
                "instructions": "Use the declared tool when needed.",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "look up 42"}],
                    }
                ],
                "tools": [
                    {
                        "type": "function",
                        "name": "lookup",
                        "description": "Look up one record",
                        "parameters": {
                            "type": "object",
                            "properties": {"id": {"type": "string"}},
                        },
                        "strict": False,
                    }
                ],
                "tool_choice": "auto",
                "parallel_tool_calls": True,
                "reasoning": {"effort": "high"},
                "store": False,
                "stream": True,
                "stream_options": {"include_obfuscation": False},
                "include": ["reasoning.encrypted_content"],
                "service_tier": "default",
                "prompt_cache_key": "thread-stable-key",
                "text": {"verbosity": "low"},
                "client_metadata": {"session_id": "session-1", "turn_id": "turn-1"},
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = coordinator.payloads[0]
        request = payload.to_gateway_request()
        self.assertIs(request.client_protocol, ClientProtocol.OPENAI_RESPONSES)
        self.assertTrue(request.requirements.tool_calling)
        self.assertTrue(request.requirements.parallel_tool_calling)
        self.assertFalse(request.tools[0].strict)
        self.assertFalse(hasattr(request, "model"))
        self.assertEqual(
            payload.client_controls,
            ("reasoning", "include", "service_tier", "client_metadata", "text.verbosity"),
        )

    def test_codex_auto_tool_choice_is_valid_when_no_tools_are_available(self) -> None:
        coordinator = RecordingCoordinator()
        response = _client("openai", coordinator).post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
            json={
                "model": "codex-client-alias",
                "input": [{"type": "message", "role": "user", "content": "hello"}],
                "tool_choice": "auto",
                "parallel_tool_calls": False,
                "reasoning": {"effort": "medium"},
                "store": False,
                "stream": True,
                "include": ["reasoning.encrypted_content"],
                "client_metadata": {"session_id": "session-1"},
            },
        )

        self.assertEqual(response.status_code, 200)
        request = coordinator.payloads[0].to_gateway_request()
        self.assertFalse(request.requirements.tool_calling)

    def test_codex_second_turn_replays_output_call_and_text_result(self) -> None:
        coordinator = RecordingCoordinator()
        response = _client("openai", coordinator).post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
            json={
                "model": "codex-client-alias",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "look up 42"}],
                    },
                    {
                        "id": "msg_previous",
                        "type": "message",
                        "role": "assistant",
                        "phase": "commentary",
                        "content": [{"type": "output_text", "text": "I'll check."}],
                    },
                    {
                        "id": "fc_previous",
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "lookup",
                        "arguments": '{"id":"42"}',
                    },
                    {
                        "id": "fco_previous",
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "name": "lookup",
                        "output": [{"type": "input_text", "text": "found"}],
                    },
                ],
                "tools": [
                    {
                        "type": "function",
                        "name": "lookup",
                        "description": "Look up one record",
                        "parameters": {"type": "object"},
                        "strict": False,
                        "defer_loading": False,
                    }
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        request = coordinator.payloads[0].to_gateway_request()
        result = request.messages[-1].canonical_blocks[0]
        self.assertIsInstance(result, ToolResultBlock)
        assert isinstance(result, ToolResultBlock)
        self.assertEqual(result.result.content, "found")

    def test_unknown_controls_are_rejected_not_ignored(self) -> None:
        coordinator = RecordingCoordinator()
        response = _client("openai", coordinator).post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
            json={
                "model": "governed-agent",
                "input": "hello",
                "temperature": 0.7,
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertFalse(coordinator.payloads)

    def test_stream_failure_uses_responses_failed_event(self) -> None:
        failed = (
            GatewayStreamEvent(
                event_type=StreamEventType.RESPONSE_FAILED,
                request_id=REQUEST_ID,
                sequence_number=1,
                routing=_routing(),
                error=GatewayError(code="rate_limit", message="safe", retryable=False),
            ),
        )
        response = _client("openai", RecordingCoordinator(failed)).post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
            json={"model": "governed-agent", "input": "hello", "stream": True},
        )

        events = _sse_events(response.text)
        self.assertEqual(events[0][0], "response.failed")
        self.assertEqual(events[0][1]["response"]["error"]["code"], "rate_limit")


class ProtocolBoundarySecurityTests(unittest.TestCase):
    def _client(self) -> TestClient:
        app = create_gateway_app(
            cast(RouteExplainCoordinator, object()),
            cast(GenerateCoordinator, object()),
        )
        return TestClient(app)

    def test_content_type_failures_use_each_protocol_error_envelope(self) -> None:
        anthropic = self._client().post("/v1/messages", content=b"{}")
        openai = self._client().post("/v1/responses", content=b"{}")

        self.assertEqual(anthropic.status_code, 415)
        self.assertEqual(anthropic.json()["type"], "error")
        self.assertEqual(openai.status_code, 415)
        self.assertEqual(openai.json()["error"]["code"], "unsupported_media_type")
        self.assertEqual(anthropic.headers["cache-control"], "no-store")
        self.assertEqual(openai.headers["cache-control"], "no-store")

    def test_validation_details_are_sanitized_in_protocol_shape(self) -> None:
        response = self._client().post(
            "/v1/responses",
            headers={"Content-Type": "application/json"},
            content=b'{"model":"governed-agent","input":{"secret":"must-not-echo"}}',
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")
        self.assertNotIn("must-not-echo", response.text)

    def test_duplicate_authorization_headers_are_rejected_before_body_parsing(self) -> None:
        response = self._client().post(
            "/v1/responses",
            headers=[
                ("Authorization", "Bearer first-secret"),
                ("Authorization", "Bearer second-secret"),
                ("Content-Type", "application/json"),
            ],
            content=b"not-json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "ambiguous_gateway_credential")
        self.assertNotIn("first-secret", response.text)
        self.assertNotIn("second-secret", response.text)
