"""The OpenAI-compatible ingress must reduce friction without widening authority."""

import json
import unittest
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from governed_llm_gateway_api.openai_compatible_ingress import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    attach_openai_compatible_route,
)
from governed_llm_gateway_api.stream_generate import (
    GenerateRequestModel,
    PreparedStreamingExecution,
)
from governed_llm_gateway_contracts import (
    Capability,
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
    Usage,
    WorkloadRequirements,
)
from governed_llm_gateway_core.application.ranking import (
    RankedCandidate,
    RankingDecision,
    ScoreBreakdown,
)
from governed_llm_gateway_core.domain.model_registry import ModelDeployment, PricingMetadata

REQUEST_ID = UUID("55555555-5555-4555-8555-555555555555")
TODAY = date(2026, 9, 1)
CREDENTIAL = "gateway-openai-shim-credential"


def _deployment() -> ModelDeployment:
    return ModelDeployment(
        deployment_id="deployment-a",
        provider="provider-a",
        model_id="provider-a/model-a",
        model_group="balanced",
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


def _routing() -> RoutingProvenance:
    return RoutingProvenance(
        routing_decision_id="sha256:" + "b" * 64,
        policy=PolicyProvenance(
            decision_id="policy-decision",
            policy_id="gateway-policy",
            policy_version="1.0.0",
            policy_digest="sha256:" + "a" * 64,
        ),
        authorized_model_group="balanced",
        model_registry_digest="c" * 64,
        ranking_policy_version="ranking-v1",
        ranking_policy_digest="d" * 64,
        score_snapshot_id="static-v1",
        provider="provider-a",
        model="provider-a/model-a",
        deployment="deployment-a",
    )


def _prepared() -> PreparedStreamingExecution:
    deployment = _deployment()
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
    return PreparedStreamingExecution(
        request=GatewayRequest(
            schema_version="1.0",
            request_id=REQUEST_ID,
            workload="rag.answer",
            risk_level=RiskLevel.LOW,
            data_classification=DataClassification.PUBLIC,
            requirements=WorkloadRequirements(streaming=True),
            messages=(Message(role=MessageRole.USER, content="hello"),),
        ),
        decision=RankingDecision(
            routing=_routing(),
            ranking_policy_digest="d" * 64,
            score_snapshot_id="static-v1",
            selected=candidate,
            alternatives=(),
            rejected_candidates=(),
        ),
        max_output_tokens=32,
        provider_timeout_seconds=1.0,
    )


def _execution() -> ProviderExecution:
    return ProviderExecution(
        provider="provider-a",
        model="provider-a/model-a",
        deployment="deployment-a",
        status=ExecutionStatus.SUCCEEDED,
        latency_ms=12,
        attempt_number=2,
        fallback_index=1,
        trace_id="abcdef1234567890abcdef1234567890",
    )


class RecordingCoordinator:
    """Capture the translated native request and replay a scripted governed stream."""

    def __init__(self, events: tuple[GatewayStreamEvent, ...] | None = None) -> None:
        self.seen_payloads: list[GenerateRequestModel] = []
        self.seen_keys: list[str] = []
        self.events = events or _successful_events()

    async def prepare(
        self,
        *,
        api_key: str,
        payload: GenerateRequestModel,
    ) -> PreparedStreamingExecution:
        self.seen_keys.append(api_key)
        self.seen_payloads.append(payload)
        return _prepared()

    async def stream(
        self,
        prepared: PreparedStreamingExecution,
    ) -> AsyncGenerator[GatewayStreamEvent]:
        del prepared
        for event in self.events:
            yield event


def _successful_events() -> tuple[GatewayStreamEvent, ...]:
    return (
        GatewayStreamEvent(
            event_type=StreamEventType.RESPONSE_STARTED,
            request_id=REQUEST_ID,
            sequence_number=1,
            routing=_routing(),
        ),
        GatewayStreamEvent(
            event_type=StreamEventType.CONTENT_DELTA,
            request_id=REQUEST_ID,
            sequence_number=2,
            delta="deterministic ",
        ),
        GatewayStreamEvent(
            event_type=StreamEventType.CONTENT_DELTA,
            request_id=REQUEST_ID,
            sequence_number=3,
            delta="routing",
        ),
        GatewayStreamEvent(
            event_type=StreamEventType.USAGE_COMPLETED,
            request_id=REQUEST_ID,
            sequence_number=4,
            usage=Usage(input_tokens=11, output_tokens=3),
        ),
        GatewayStreamEvent(
            event_type=StreamEventType.RESPONSE_COMPLETED,
            request_id=REQUEST_ID,
            sequence_number=5,
            routing=_routing(),
            execution=_execution(),
            finish_reason="stop",
        ),
    )


def _failed_events() -> tuple[GatewayStreamEvent, ...]:
    return (
        GatewayStreamEvent(
            event_type=StreamEventType.RESPONSE_FAILED,
            request_id=REQUEST_ID,
            sequence_number=1,
            routing=_routing(),
            error=GatewayError(code="rate_limit", message="upstream refused", retryable=True),
        ),
    )


def _client(coordinator: RecordingCoordinator) -> TestClient:
    app = FastAPI()
    attach_openai_compatible_route(app, coordinator)  # type: ignore[arg-type]
    return TestClient(app)


def _body(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": "rag.answer",
        "messages": [{"role": "user", "content": "explain deterministic routing"}],
    }
    payload.update(overrides)
    return payload


class AuthorityBoundaryTests(unittest.TestCase):
    def test_model_names_a_workload_not_a_provider_model(self) -> None:
        coordinator = RecordingCoordinator()

        response = _client(coordinator).post(
            "/v1/chat/completions",
            json=_body(),
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(coordinator.seen_payloads[0].workload, "rag.answer")

    def test_obviously_provider_shaped_names_are_refused_by_shape(self) -> None:
        for rejected in ("openai/gpt-4", "Rag.Answer", "gpt4", "rag.answer.", "-rag.answer"):
            with self.subTest(model=rejected):
                response = _client(RecordingCoordinator()).post(
                    "/v1/chat/completions",
                    json=_body(model=rejected),
                    headers={"Authorization": f"Bearer {CREDENTIAL}"},
                )

                self.assertEqual(response.status_code, 422)

    def test_a_dotted_model_name_is_carried_as_a_workload_not_a_model(self) -> None:
        """`gpt-5.6-luna` is shaped like a workload and passes shape validation.

        That is the honest boundary: syntax cannot tell a workload from a model name, so
        the request is carried as a workload and authorization is what refuses it. The
        property worth asserting is that no provider or model selection reaches the
        governed path at all.
        """
        coordinator = RecordingCoordinator()

        _client(coordinator).post(
            "/v1/chat/completions",
            json=_body(model="gpt-5.6-luna"),
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
        )

        translated = coordinator.seen_payloads[0]
        self.assertEqual(translated.workload, "gpt-5.6-luna")
        self.assertFalse(hasattr(translated, "model"))
        self.assertFalse(hasattr(translated, "provider"))
        self.assertFalse(hasattr(translated, "deployment"))

    def test_sampling_controls_are_rejected_rather_than_silently_dropped(self) -> None:
        """Accepting and ignoring them would let a caller believe it influenced execution."""
        for field, value in (("temperature", 0.7), ("top_p", 0.1), ("n", 2), ("seed", 5)):
            with self.subTest(field=field):
                response = _client(RecordingCoordinator()).post(
                    "/v1/chat/completions",
                    json=_body(**{field: value}),
                    headers={"Authorization": f"Bearer {CREDENTIAL}"},
                )

                self.assertEqual(response.status_code, 422)

    def test_classification_comes_from_the_binding_not_the_caller(self) -> None:
        coordinator = RecordingCoordinator()

        _client(coordinator).post(
            "/v1/chat/completions",
            json=_body(),
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
        )

        translated = coordinator.seen_payloads[0]
        self.assertIs(translated.risk_level, RiskLevel.LOW)
        self.assertIs(translated.data_classification, DataClassification.PUBLIC)

    def test_the_credential_reaches_the_governed_preflight_unchanged(self) -> None:
        coordinator = RecordingCoordinator()

        _client(coordinator).post(
            "/v1/chat/completions",
            json=_body(),
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
        )

        self.assertEqual(coordinator.seen_keys, [CREDENTIAL])


class CredentialTests(unittest.TestCase):
    def test_the_gateway_header_is_accepted_too(self) -> None:
        coordinator = RecordingCoordinator()

        response = _client(coordinator).post(
            "/v1/chat/completions",
            json=_body(),
            headers={"X-Gateway-API-Key": CREDENTIAL},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(coordinator.seen_keys, [CREDENTIAL])

    def test_a_missing_credential_is_refused(self) -> None:
        response = _client(RecordingCoordinator()).post("/v1/chat/completions", json=_body())

        self.assertEqual(response.status_code, 401)

    def test_a_non_bearer_scheme_is_refused(self) -> None:
        response = _client(RecordingCoordinator()).post(
            "/v1/chat/completions",
            json=_body(),
            headers={"Authorization": f"Basic {CREDENTIAL}"},
        )

        self.assertEqual(response.status_code, 401)

    def test_conflicting_credentials_are_refused_rather_than_ranked(self) -> None:
        response = _client(RecordingCoordinator()).post(
            "/v1/chat/completions",
            json=_body(),
            headers={
                "Authorization": f"Bearer {CREDENTIAL}",
                "X-Gateway-API-Key": "a-different-credential",
            },
        )

        self.assertEqual(response.status_code, 400)


class NonStreamingResponseTests(unittest.TestCase):
    def test_the_governed_stream_is_aggregated_into_one_completion(self) -> None:
        response = _client(RecordingCoordinator()).post(
            "/v1/chat/completions",
            json=_body(),
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
        )
        body = response.json()

        self.assertEqual(body["object"], "chat.completion")
        self.assertEqual(body["model"], "rag.answer")
        self.assertEqual(body["choices"][0]["message"]["content"], "deterministic routing")
        self.assertEqual(body["choices"][0]["message"]["role"], "assistant")
        self.assertEqual(body["choices"][0]["finish_reason"], "stop")
        self.assertEqual(
            body["usage"],
            {
                "prompt_tokens": 11,
                "completion_tokens": 3,
                "total_tokens": 14,
            },
        )

    def test_execution_evidence_travels_beside_the_openai_shape(self) -> None:
        response = _client(RecordingCoordinator()).post(
            "/v1/chat/completions",
            json=_body(),
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
        )
        evidence = response.json()["x_gateway"]

        self.assertEqual(evidence["provider"], "provider-a")
        self.assertEqual(evidence["deployment"], "deployment-a")
        self.assertEqual(evidence["attempt_number"], 2)
        self.assertEqual(evidence["fallback_index"], 1)
        self.assertEqual(evidence["trace_id"], "abcdef1234567890abcdef1234567890")
        self.assertEqual(evidence["model_group"], "balanced")

    def test_a_failed_stream_becomes_an_openai_error_envelope(self) -> None:
        response = _client(RecordingCoordinator(_failed_events())).post(
            "/v1/chat/completions",
            json=_body(),
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["error"]["code"], "rate_limit")

    def test_the_documented_default_output_budget_is_applied(self) -> None:
        coordinator = RecordingCoordinator()

        _client(coordinator).post(
            "/v1/chat/completions",
            json=_body(),
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
        )

        self.assertEqual(coordinator.seen_payloads[0].max_output_tokens, DEFAULT_MAX_OUTPUT_TOKENS)

    def test_max_completion_tokens_is_honoured(self) -> None:
        coordinator = RecordingCoordinator()

        _client(coordinator).post(
            "/v1/chat/completions",
            json=_body(max_completion_tokens=128),
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
        )

        self.assertEqual(coordinator.seen_payloads[0].max_output_tokens, 128)

    def test_two_token_budgets_are_ambiguous_and_refused(self) -> None:
        response = _client(RecordingCoordinator()).post(
            "/v1/chat/completions",
            json=_body(max_tokens=64, max_completion_tokens=128),
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
        )

        self.assertEqual(response.status_code, 422)


class StreamingResponseTests(unittest.TestCase):
    def _chunks(self, coordinator: RecordingCoordinator) -> list[Any]:
        response = _client(coordinator).post(
            "/v1/chat/completions",
            json=_body(stream=True),
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
        )
        self.assertEqual(response.status_code, 200)
        chunks: list[Any] = []
        for line in response.text.splitlines():
            if not line.startswith("data: "):
                continue
            body = line.removeprefix("data: ")
            if body == "[DONE]":
                continue
            chunks.append(json.loads(body))
        return chunks

    def test_chunks_use_the_shape_sdks_expect(self) -> None:
        chunks = self._chunks(RecordingCoordinator())

        self.assertTrue(all(chunk["object"] == "chat.completion.chunk" for chunk in chunks))
        deltas = [
            chunk["choices"][0]["delta"].get("content")
            for chunk in chunks
            if chunk["choices"] and chunk["choices"][0]["delta"].get("content")
        ]
        self.assertEqual(deltas, ["deterministic ", "routing"])

    def test_the_stream_terminates_with_the_done_sentinel(self) -> None:
        response = _client(RecordingCoordinator()).post(
            "/v1/chat/completions",
            json=_body(stream=True),
            headers={"Authorization": f"Bearer {CREDENTIAL}"},
        )

        self.assertTrue(response.text.rstrip().endswith("data: [DONE]"))

    def test_a_finish_reason_closes_the_choice(self) -> None:
        chunks = self._chunks(RecordingCoordinator())
        finishes = [
            chunk["choices"][0]["finish_reason"]
            for chunk in chunks
            if chunk["choices"] and chunk["choices"][0]["finish_reason"] is not None
        ]

        self.assertEqual(finishes, ["stop"])

    def test_a_mid_stream_failure_is_reported_in_band(self) -> None:
        """HTTP 200 is already committed, so the caller must learn of failure in the body."""
        chunks = self._chunks(RecordingCoordinator(_failed_events()))

        self.assertEqual(chunks[-1]["x_gateway"]["error"], "rate_limit")
        self.assertEqual(chunks[-1]["choices"][0]["finish_reason"], "error")


if __name__ == "__main__":
    unittest.main()
