"""The gateway forwards a verified runtime authorization to the Policy Decision Point.

A Policy Model Router with `RUNTIME_AUTHORIZATION_REQUIRED=true` - mandatory for its own staging
and production environments - answers a bare route body with `403 runtime_authorization_required`.
These tests pin the wrapped body it accepts instead, and pin that the envelope crosses the boundary
byte-equivalently: the PDP verifies the same Ed25519 signature over the same canonical claims, so
anything this gateway re-shaped would be a forgery by accident.
"""

import base64
import json
import unittest
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from governed_llm_gateway_contracts import DataClassification, RiskLevel
from governed_llm_gateway_core.adapters.governance_authorization import (
    StaticGovernanceKeyResolver,
    verify_governance_authorization_envelope,
    verify_governance_authorization_text,
)
from governed_llm_gateway_core.adapters.policy_router import (
    PolicyHttpResponse,
    PolicyRouterHttpAdapter,
)
from governed_llm_gateway_core.application.policy import (
    PolicyDecisionError,
    PolicyDecisionErrorCode,
    PolicyRequestMetadata,
)
from governed_llm_gateway_core.domain.governance import ForwardableGovernanceAuthorization

_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
_PUBLIC_KEY = _PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
)
_KEY_ID = "governance-key-1"
_AUTHORIZATION_ID = "11111111-1111-4111-8111-111111111111"
_REQUEST_ID = UUID("99999999-9999-4999-8999-999999999999")
_ISSUED_AT = "2026-09-04T13:30:00Z"
_NOW = datetime(2026, 9, 4, 13, 31, tzinfo=UTC)
_POLICY_DIGEST = "sha256:" + ("a" * 64)


def _claims() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "authorization_id": _AUTHORIZATION_ID,
        "issuer": "verifiable-ai-governance",
        "audience": ["governed-llm-gateway"],
        "issued_at": _ISSUED_AT,
        "not_before": _ISSUED_AT,
        "expires_at": "2026-09-04T13:35:00Z",
        "subject": {
            "initiative_id": "22222222-2222-4222-8222-222222222222",
            "ai_system_id": "33333333-3333-4333-8333-333333333333",
            "ai_system_version": 2,
            "agent_id": "44444444-4444-4444-8444-444444444444",
            "agent_version": 3,
            "agent_review_digest": "a" * 64,
        },
        "request": {
            "workflow_id": "workflow-1",
            "task_id": "task-1",
            "workload": "rag.answer",
            "context_tokens_estimated": 2048,
            "max_output_tokens_estimated": 512,
            "structured_output_required": False,
            "max_latency_ms": 5000,
            "max_cost_usd_micros": 250_000,
        },
        "scope": {
            "risk_tier": "high",
            "data_classification": "internal",
            "autonomy_level": "a1_recommendation",
            "models": [
                {
                    "model_id": "55555555-5555-4555-8555-555555555555",
                    "entity_version": 4,
                    "model_version": "2026-08-01",
                    "routing_group": "agentic-strong",
                    "review_digest": "b" * 64,
                    "allowed_data_classes": ["internal", "public"],
                }
            ],
            "allowed_tools": [],
            "permissions": [],
            "max_runtime_seconds": 120,
            "human_approval_points": [],
            "kill_switch_enabled": True,
        },
        "scope_digest": "d" * 64,
        "policy": {
            "policy_id": "governance-policy",
            "policy_version": "2.0.0",
            "policy_digest": "e" * 64,
            "control_catalog_id": "enterprise-controls",
            "control_catalog_version": "2.0.0",
            "control_catalog_digest": "f" * 64,
        },
    }


def _protected() -> dict[str, object]:
    return {
        "typ": "application/vnd.verifiable-ai-governance.runtime-authorization+json",
        "alg": "Ed25519",
        "kid": _KEY_ID,
    }


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _signed_text() -> str:
    signature = _PRIVATE_KEY.sign(
        _canonical_bytes({"protected": _protected(), "claims": _claims()})
    )
    return json.dumps(
        {
            "protected": _protected(),
            "claims": _claims(),
            "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _forwardable() -> ForwardableGovernanceAuthorization:
    resolver = StaticGovernanceKeyResolver({_KEY_ID: _PUBLIC_KEY})
    return verify_governance_authorization_envelope(_signed_text(), keys=resolver)


def _metadata(**overrides: object) -> PolicyRequestMetadata:
    values: dict[str, object] = {
        "request_id": _REQUEST_ID,
        "client_id": "trusted-client",
        "environment": "development",
        "workload": "rag.answer",
        "risk_level": RiskLevel.HIGH,
        "data_classification": DataClassification.INTERNAL,
        "context_tokens_estimated": 2048,
        "max_output_tokens_estimated": 512,
        "structured_output_required": False,
        "max_latency_ms": 5000,
        "max_cost_usd": Decimal("0.25"),
    }
    values.update(overrides)
    return PolicyRequestMetadata(**values)  # type: ignore[arg-type]


class _FakeTransport:
    def __init__(self, response: PolicyHttpResponse) -> None:
        self._response = response
        self.bodies: list[Mapping[str, object]] = []

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> PolicyHttpResponse:
        self.bodies.append(dict(payload))
        return self._response


def _success(*, workflow_id: str, task_id: str) -> PolicyHttpResponse:
    return PolicyHttpResponse(
        status_code=200,
        retry_after=None,
        payload={
            "schema_version": "1.0",
            "routing_decision_id": "decision-1",
            "decided_at": "2026-09-04T13:31:00Z",
            "workflow_id": workflow_id,
            "task_id": task_id,
            "selected_model_group": "agentic-strong",
            "reason": "workload is authorized",
            "rejected_candidates": [],
            "policy_id": "gateway-generic-routing",
            "policy_version": "1.0.0",
            "policy_digest": _POLICY_DIGEST,
            "service_version": "1.0.0",
            "environment": "development",
        },
    )


def _adapter(response: PolicyHttpResponse) -> tuple[PolicyRouterHttpAdapter, _FakeTransport]:
    transport = _FakeTransport(response)
    adapter = PolicyRouterHttpAdapter(
        endpoint="https://policy.example/route",
        api_keys_by_client={"trusted-client": "policy-secret"},
        transport=transport,
        now=lambda: _NOW,
    )
    return adapter, transport


class RuntimeAuthorizationForwardingTests(unittest.IsolatedAsyncioTestCase):
    async def test_absent_authorization_keeps_the_flat_route_body(self) -> None:
        """A PDP that does not enforce runtime authorization sees no change at all."""
        identity = str(_REQUEST_ID)
        adapter, transport = _adapter(_success(workflow_id=identity, task_id=identity))

        await adapter.authorize(_metadata())

        body = transport.bodies[0]
        self.assertNotIn("authorization", body)
        self.assertEqual(body["schema_version"], "1.0")
        self.assertEqual(body["workflow_id"], identity)
        self.assertEqual(body["task_id"], identity)
        self.assertEqual(body["requested_at"], "2026-09-04T13:31:00Z")

    async def test_present_authorization_wraps_the_body_and_forwards_the_envelope(self) -> None:
        adapter, transport = _adapter(_success(workflow_id="workflow-1", task_id="task-1"))

        await adapter.authorize(_metadata(runtime_authorization=_forwardable()))

        body = transport.bodies[0]
        self.assertEqual(set(body), {"request", "authorization"})
        self.assertEqual(body["authorization"], json.loads(_signed_text()))
        route = body["request"]
        assert isinstance(route, Mapping)
        self.assertEqual(route["workflow_id"], "workflow-1")
        self.assertEqual(route["task_id"], "task-1")
        self.assertEqual(route["requested_at"], _ISSUED_AT)

    async def test_forwarded_envelope_still_verifies_against_the_same_signature(self) -> None:
        """The property that makes forwarding safe: the PDP verifies what the gateway verified."""
        adapter, transport = _adapter(_success(workflow_id="workflow-1", task_id="task-1"))

        await adapter.authorize(_metadata(runtime_authorization=_forwardable()))

        envelope = transport.bodies[0]["authorization"]
        resolver = StaticGovernanceKeyResolver({_KEY_ID: _PUBLIC_KEY})
        downstream = verify_governance_authorization_text(json.dumps(envelope), keys=resolver)
        self.assertEqual(str(downstream.authorization_id), _AUTHORIZATION_ID)

    async def test_response_correlation_follows_the_identity_actually_sent(self) -> None:
        """The echo check reads the identity the body carried, not the gateway request id."""
        identity = str(_REQUEST_ID)
        adapter, _transport = _adapter(_success(workflow_id=identity, task_id=identity))

        with self.assertRaises(PolicyDecisionError) as caught:
            await adapter.authorize(_metadata(runtime_authorization=_forwardable()))

        self.assertIs(caught.exception.code, PolicyDecisionErrorCode.INVALID_RESPONSE)


class ForwardableAuthorizationBindingTests(unittest.TestCase):
    def test_binding_disagreement_fails_closed_before_any_network_call(self) -> None:
        cases: tuple[tuple[dict[str, object], str], ...] = (
            ({"workload": "agent.orchestration"}, "workload"),
            ({"risk_level": RiskLevel.CRITICAL}, "risk_level"),
            ({"data_classification": DataClassification.PUBLIC}, "data_classification"),
            ({"context_tokens_estimated": 2049}, "context_tokens_estimated"),
            ({"max_output_tokens_estimated": 513}, "max_output_tokens_estimated"),
            ({"structured_output_required": True}, "structured_output_required"),
            ({"max_latency_ms": 4999}, "max_latency_ms"),
            ({"max_cost_usd": Decimal("0.24")}, "max_cost_usd"),
        )
        forwardable = _forwardable()
        for override, expected_field in cases:
            with self.subTest(field=expected_field):
                with self.assertRaises(ValueError) as caught:
                    _metadata(runtime_authorization=forwardable, **override)
                self.assertIn(expected_field, str(caught.exception))

    def test_envelope_must_describe_the_authorization_it_is_paired_with(self) -> None:
        forwardable = _forwardable()
        foreign = json.loads(_signed_text())
        foreign["claims"]["authorization_id"] = "77777777-7777-4777-8777-777777777777"

        with self.assertRaises(ValueError) as caught:
            ForwardableGovernanceAuthorization(
                authorization=forwardable.authorization,
                document=foreign,
            )
        self.assertIn("does not describe the verified authorization", str(caught.exception))

    def test_envelope_must_stay_intact(self) -> None:
        forwardable = _forwardable()
        truncated = json.loads(_signed_text())
        del truncated["signature"]

        with self.assertRaises(ValueError) as caught:
            ForwardableGovernanceAuthorization(
                authorization=forwardable.authorization,
                document=truncated,
            )
        self.assertIn("protected, claims and signature", str(caught.exception))
