import unittest
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from governed_llm_gateway_contracts import DataClassification, RiskLevel
from governed_llm_gateway_core.adapters import PolicyRouterHttpAdapter
from governed_llm_gateway_core.adapters.policy_router import PolicyHttpResponse
from governed_llm_gateway_core.application import (
    PolicyDecisionError,
    PolicyDecisionErrorCode,
    PolicyRequestMetadata,
)

REQUEST_ID = UUID("11111111-1111-4111-8111-111111111111")


class FakePolicyTransport:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self.payload = payload

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> PolicyHttpResponse:
        del url, headers, payload, timeout_seconds
        return PolicyHttpResponse(status_code=422, retry_after=None, payload=self.payload)


def request_metadata() -> PolicyRequestMetadata:
    return PolicyRequestMetadata(
        request_id=REQUEST_ID,
        client_id="trusted-client",
        environment="development",
        workload="rag.answer",
        risk_level=RiskLevel.HIGH,
        data_classification=DataClassification.CONFIDENTIAL,
        context_tokens_estimated=1024,
        max_output_tokens_estimated=256,
        structured_output_required=False,
        max_latency_ms=5000,
        max_cost_usd=Decimal("0.05"),
    )


def rejection_payload() -> dict[str, object]:
    request_id = str(REQUEST_ID)
    return {
        "error": {"code": "no_viable_model_group", "message": "denied"},
        "decision": {
            "schema_version": "1.0",
            "routing_decision_id": "rejection-1",
            "decided_at": "2026-08-31T16:00:00Z",
            "workflow_id": request_id,
            "task_id": request_id,
            "workload": "rag.answer",
            "rejected_model_group": "balanced",
            "reason": "denied",
            "reason_code": "risk_level_not_authorized",
            "observed_value": "high",
            "required_value": "low, medium",
            "policy_id": "gateway-generic-routing",
            "policy_version": "1.0.0",
            "policy_digest": "sha256:" + ("a" * 64),
            "service_version": "1.0.0",
            "environment": "development",
        },
    }


class PolicyRejectionBindingTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejection_must_bind_to_request_and_environment(self) -> None:
        cases = {
            "workflow_id": "other-workflow",
            "task_id": "other-task",
            "workload": "security.analysis",
            "environment": "production",
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                payload = rejection_payload()
                decision = payload["decision"]
                assert isinstance(decision, dict)
                decision[field] = value
                adapter = PolicyRouterHttpAdapter(
                    endpoint="https://policy.example/route",
                    api_keys_by_client={"trusted-client": "policy-secret"},
                    transport=FakePolicyTransport(payload),
                    now=lambda: datetime(2026, 8, 31, 16, 0, tzinfo=UTC),
                )
                with self.assertRaises(PolicyDecisionError) as caught:
                    await adapter.authorize(request_metadata())
                self.assertEqual(caught.exception.code, PolicyDecisionErrorCode.INVALID_RESPONSE)
