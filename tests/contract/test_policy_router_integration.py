import json
import unittest
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayRequest,
    Message,
    MessageRole,
    RequestLimits,
    RiskLevel,
    WorkloadRequirements,
)
from governed_llm_gateway_core.adapters import PolicyRouterHttpAdapter, load_model_registry_text
from governed_llm_gateway_core.adapters.policy_router import (
    PolicyHttpResponse,
    PolicyTransportFailure,
    PolicyTransportFailureKind,
)
from governed_llm_gateway_core.application import (
    PolicyDecisionError,
    PolicyDecisionErrorCode,
    PolicyEnforcementService,
    PolicyProjectionDefaults,
    ProviderRequest,
    ProviderResponse,
    project_policy_request,
)
from governed_llm_gateway_core.domain import (
    AuthorizationBoundaryViolation,
    EffectivePolicyContext,
)

REQUEST_ID = UUID("11111111-1111-4111-8111-111111111111")
POLICY_DIGEST = "sha256:" + ("a" * 64)
NOW = datetime(2026, 8, 31, 16, 0, tzinfo=UTC)


def gateway_request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="rag.answer",
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(
            tool_calling=True,
            structured_output=True,
            min_context_tokens=128000,
        ),
        limits=RequestLimits(
            max_latency_ms=5000,
            max_cost_usd=Decimal("0.05"),
        ),
        messages=(Message(role=MessageRole.USER, content="TOP-SECRET-PROMPT"),),
        agent_identity="spoofed-client",
    )


def effective_context() -> EffectivePolicyContext:
    return EffectivePolicyContext(
        client_id="trusted-client",
        environment="development",
        workload="rag.answer",
        risk_level=RiskLevel.HIGH,
        data_classification=DataClassification.CONFIDENTIAL,
    )


def defaults() -> PolicyProjectionDefaults:
    return PolicyProjectionDefaults(
        max_latency_ms=10000,
        max_cost_usd=Decimal("0.10"),
    )


def success_payload(
    *, model_group: str = "balanced", environment: str = "development"
) -> dict[str, object]:
    request_id = str(REQUEST_ID)
    return {
        "schema_version": "1.0",
        "routing_decision_id": "decision-1",
        "decided_at": "2026-08-31T16:00:00Z",
        "workflow_id": request_id,
        "task_id": request_id,
        "selected_model_group": model_group,
        "reason": "workload is authorized",
        "rejected_candidates": [],
        "policy_id": "gateway-generic-routing",
        "policy_version": "1.0.0",
        "policy_digest": POLICY_DIGEST,
        "service_version": "1.0.0",
        "environment": environment,
    }


def rejection_payload() -> dict[str, object]:
    request_id = str(REQUEST_ID)
    return {
        "error": {
            "code": "no_viable_model_group",
            "message": "request rejected",
        },
        "decision": {
            "schema_version": "1.0",
            "routing_decision_id": "rejection-1",
            "decided_at": "2026-08-31T16:00:00Z",
            "workflow_id": request_id,
            "task_id": request_id,
            "workload": "rag.answer",
            "rejected_model_group": "balanced",
            "reason": "risk level not authorized",
            "reason_code": "risk_level_not_authorized",
            "observed_value": "high",
            "required_value": "low, medium",
            "policy_id": "gateway-generic-routing",
            "policy_version": "1.0.0",
            "policy_digest": POLICY_DIGEST,
            "service_version": "1.0.0",
            "environment": "development",
        },
    }


def registry_text() -> str:
    return """schema_version: "1.0"
catalog_version: "phase4"
source_date: "2026-08-31"
deployments:
  balanced-a:
    provider: provider-a
    model_id: vendor/model-a
    model_group: balanced
    api_family: openai-compatible
    capabilities:
      text: true
      vision: false
      tool_calling: true
      structured_output: true
      streaming: false
    context_tokens: 128000
    modalities: [text]
    pricing: null
    max_data_classification: confidential
    allowed_environments: [development]
    enabled: true
    source_date: "2026-08-31"
    catalog_version: "phase4"
  reasoning-b:
    provider: provider-b
    model_id: vendor/model-b
    model_group: reasoning-strong
    api_family: anthropic-messages
    capabilities:
      text: true
      vision: false
      tool_calling: true
      structured_output: true
      streaming: false
    context_tokens: 256000
    modalities: [text]
    pricing: null
    max_data_classification: restricted
    allowed_environments: [development]
    enabled: true
    source_date: "2026-08-31"
    catalog_version: "phase4"
"""


class FakePolicyTransport:
    def __init__(
        self,
        response: PolicyHttpResponse | None = None,
        failure: PolicyTransportFailure | None = None,
    ) -> None:
        self.response = response
        self.failure = failure
        self.calls: list[dict[str, object]] = []

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> PolicyHttpResponse:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": dict(payload),
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.failure is not None:
            raise self.failure
        if self.response is None:
            raise AssertionError("fake policy transport requires a response or failure")
        return self.response


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        return ProviderResponse(text="provider response")


def adapter_for(
    response: PolicyHttpResponse,
) -> tuple[PolicyRouterHttpAdapter, FakePolicyTransport]:
    transport = FakePolicyTransport(response=response)
    adapter = PolicyRouterHttpAdapter(
        endpoint="https://policy.example/route",
        api_keys_by_client={"trusted-client": "policy-secret"},
        transport=transport,
        now=lambda: NOW,
    )
    return adapter, transport


class PolicyProjectionTests(unittest.TestCase):
    def test_projection_uses_trusted_context_and_only_tightens_limits(self) -> None:
        projected = project_policy_request(
            gateway_request(),
            effective_context(),
            context_tokens_estimated=4096,
            max_output_tokens_estimated=512,
            defaults=defaults(),
        )
        self.assertEqual(projected.client_id, "trusted-client")
        self.assertEqual(projected.environment, "development")
        self.assertEqual(projected.risk_level, RiskLevel.HIGH)
        self.assertEqual(projected.data_classification, DataClassification.CONFIDENTIAL)
        self.assertEqual(projected.context_tokens_estimated, 4096)
        self.assertEqual(projected.max_latency_ms, 5000)
        self.assertEqual(projected.max_cost_usd, Decimal("0.05"))

    def test_min_context_requirement_is_not_fabricated_into_token_estimate(self) -> None:
        projected = project_policy_request(
            gateway_request(),
            effective_context(),
            context_tokens_estimated=2048,
            max_output_tokens_estimated=256,
            defaults=defaults(),
        )
        self.assertEqual(projected.context_tokens_estimated, 2048)
        self.assertEqual(gateway_request().requirements.min_context_tokens, 128000)

    def test_trusted_workload_mismatch_fails_closed(self) -> None:
        context = EffectivePolicyContext(
            client_id="trusted-client",
            environment="development",
            workload="security.analysis",
            risk_level=RiskLevel.HIGH,
            data_classification=DataClassification.CONFIDENTIAL,
        )
        with self.assertRaisesRegex(ValueError, "trusted workload"):
            project_policy_request(
                gateway_request(),
                context,
                context_tokens_estimated=100,
                max_output_tokens_estimated=100,
                defaults=defaults(),
            )

    def test_zero_cost_ceiling_fails_closed_instead_of_being_relaxed(self) -> None:
        request = GatewayRequest(
            schema_version="1.0",
            request_id=REQUEST_ID,
            workload="rag.answer",
            risk_level=RiskLevel.LOW,
            data_classification=DataClassification.PUBLIC,
            limits=RequestLimits(max_cost_usd=Decimal("0")),
            messages=(Message(role=MessageRole.USER, content="hello"),),
        )
        with self.assertRaisesRegex(ValueError, "non-positive cost ceiling"):
            project_policy_request(
                request,
                effective_context(),
                context_tokens_estimated=100,
                max_output_tokens_estimated=100,
                defaults=defaults(),
            )


class PolicyRouterAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_wire_request_contains_no_prompt_and_uses_trusted_identity(self) -> None:
        adapter, transport = adapter_for(
            PolicyHttpResponse(status_code=200, retry_after=None, payload=success_payload())
        )
        projected = project_policy_request(
            gateway_request(),
            effective_context(),
            context_tokens_estimated=4096,
            max_output_tokens_estimated=512,
            defaults=defaults(),
        )

        decision = await adapter.authorize(projected)

        self.assertEqual(decision.authorization.authorized_model_groups, frozenset({"balanced"}))
        self.assertEqual(decision.provenance.policy_digest, POLICY_DIGEST)
        call = transport.calls[0]
        payload = call["payload"]
        headers = call["headers"]
        assert isinstance(payload, dict)
        assert isinstance(headers, dict)
        self.assertEqual(payload["agent_name"], "trusted-client")
        self.assertEqual(payload["risk_level"], "high")
        self.assertEqual(payload["data_classification"], "confidential")
        self.assertNotIn("environment", payload)
        self.assertNotIn("messages", payload)
        self.assertNotIn("agent_identity", payload)
        self.assertNotIn("TOP-SECRET-PROMPT", json.dumps(payload))
        self.assertEqual(headers["x-api-key"], "policy-secret")

    async def test_success_environment_must_match_trusted_context(self) -> None:
        adapter, _ = adapter_for(
            PolicyHttpResponse(
                status_code=200,
                retry_after=None,
                payload=success_payload(environment="production"),
            )
        )
        projected = project_policy_request(
            gateway_request(),
            effective_context(),
            context_tokens_estimated=100,
            max_output_tokens_estimated=100,
            defaults=defaults(),
        )
        with self.assertRaises(PolicyDecisionError) as caught:
            await adapter.authorize(projected)
        self.assertEqual(caught.exception.code, PolicyDecisionErrorCode.INVALID_RESPONSE)

    async def test_schema_drift_fails_closed(self) -> None:
        payload = success_payload()
        payload["unexpected"] = True
        adapter, _ = adapter_for(
            PolicyHttpResponse(status_code=200, retry_after=None, payload=payload)
        )
        projected = project_policy_request(
            gateway_request(),
            effective_context(),
            context_tokens_estimated=100,
            max_output_tokens_estimated=100,
            defaults=defaults(),
        )
        with self.assertRaises(PolicyDecisionError) as caught:
            await adapter.authorize(projected)
        self.assertEqual(caught.exception.code, PolicyDecisionErrorCode.INVALID_RESPONSE)

    async def test_explicit_rejection_preserves_provenance(self) -> None:
        adapter, _ = adapter_for(
            PolicyHttpResponse(status_code=422, retry_after=None, payload=rejection_payload())
        )
        projected = project_policy_request(
            gateway_request(),
            effective_context(),
            context_tokens_estimated=100,
            max_output_tokens_estimated=100,
            defaults=defaults(),
        )
        with self.assertRaises(PolicyDecisionError) as caught:
            await adapter.authorize(projected)
        error = caught.exception
        self.assertEqual(error.code, PolicyDecisionErrorCode.REJECTED)
        self.assertEqual(error.reason_code, "risk_level_not_authorized")
        assert error.provenance is not None
        self.assertEqual(error.provenance.decision_id, "rejection-1")
        self.assertEqual(error.provenance.policy_digest, POLICY_DIGEST)

    async def test_http_failure_categories_are_fail_closed(self) -> None:
        cases = (
            (401, PolicyDecisionErrorCode.AUTHENTICATION, False),
            (403, PolicyDecisionErrorCode.AUTHORIZATION, False),
            (429, PolicyDecisionErrorCode.RATE_LIMIT, True),
            (500, PolicyDecisionErrorCode.MISCONFIGURED, False),
            (503, PolicyDecisionErrorCode.UNAVAILABLE, True),
        )
        projected = project_policy_request(
            gateway_request(),
            effective_context(),
            context_tokens_estimated=100,
            max_output_tokens_estimated=100,
            defaults=defaults(),
        )
        for status, code, retryable in cases:
            with self.subTest(status=status):
                adapter, _ = adapter_for(
                    PolicyHttpResponse(status_code=status, retry_after="1", payload=None)
                )
                with self.assertRaises(PolicyDecisionError) as caught:
                    await adapter.authorize(projected)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(caught.exception.retryable, retryable)

    async def test_transport_timeout_is_sanitized(self) -> None:
        transport = FakePolicyTransport(
            failure=PolicyTransportFailure(
                PolicyTransportFailureKind.TIMEOUT,
                "internal timeout detail policy-secret",
            )
        )
        adapter = PolicyRouterHttpAdapter(
            endpoint="https://policy.example/route",
            api_keys_by_client={"trusted-client": "policy-secret"},
            transport=transport,
            now=lambda: NOW,
        )
        projected = project_policy_request(
            gateway_request(),
            effective_context(),
            context_tokens_estimated=100,
            max_output_tokens_estimated=100,
            defaults=defaults(),
        )
        with self.assertRaises(PolicyDecisionError) as caught:
            await adapter.authorize(projected)
        self.assertEqual(caught.exception.code, PolicyDecisionErrorCode.TIMEOUT)
        self.assertNotIn("policy-secret", str(caught.exception))
        self.assertNotIn("internal timeout detail", str(caught.exception))


class PolicyEnforcementTests(unittest.IsolatedAsyncioTestCase):
    async def test_authorized_candidate_set_contains_only_pdp_group(self) -> None:
        adapter, _ = adapter_for(
            PolicyHttpResponse(status_code=200, retry_after=None, payload=success_payload())
        )
        service = PolicyEnforcementService(adapter)
        registry = load_model_registry_text(registry_text())

        authorized = await service.authorize_candidates(
            gateway_request(),
            effective_context(),
            registry,
            context_tokens_estimated=4096,
            max_output_tokens_estimated=512,
            defaults=defaults(),
        )

        self.assertEqual(
            tuple(deployment.deployment_id for deployment in authorized.candidates),
            ("balanced-a",),
        )
        self.assertEqual(authorized.policy.provenance.policy_digest, POLICY_DIGEST)
        self.assertEqual(authorized.registry_digest, registry.digest)

    async def test_router_rejection_prevents_provider_call(self) -> None:
        adapter, _ = adapter_for(
            PolicyHttpResponse(status_code=422, retry_after=None, payload=rejection_payload())
        )
        provider = FakeProvider()
        service = PolicyEnforcementService(adapter)

        with self.assertRaises(PolicyDecisionError):
            await service.execute_selected(
                gateway_request(),
                effective_context(),
                load_model_registry_text(registry_text()),
                selected_deployment_id="balanced-a",
                provider=provider,
                context_tokens_estimated=4096,
                max_output_tokens_estimated=512,
                defaults=defaults(),
            )

        self.assertEqual(provider.calls, [])

    async def test_out_of_group_selection_prevents_provider_call(self) -> None:
        adapter, _ = adapter_for(
            PolicyHttpResponse(status_code=200, retry_after=None, payload=success_payload())
        )
        provider = FakeProvider()
        service = PolicyEnforcementService(adapter)

        with self.assertRaises(AuthorizationBoundaryViolation):
            await service.execute_selected(
                gateway_request(),
                effective_context(),
                load_model_registry_text(registry_text()),
                selected_deployment_id="reasoning-b",
                provider=provider,
                context_tokens_estimated=4096,
                max_output_tokens_estimated=512,
                defaults=defaults(),
            )

        self.assertEqual(provider.calls, [])

    async def test_provider_receives_only_execution_fields_after_authorization(self) -> None:
        adapter, _ = adapter_for(
            PolicyHttpResponse(status_code=200, retry_after=None, payload=success_payload())
        )
        provider = FakeProvider()
        result = await PolicyEnforcementService(adapter).execute_selected(
            gateway_request(),
            effective_context(),
            load_model_registry_text(registry_text()),
            selected_deployment_id="balanced-a",
            provider=provider,
            context_tokens_estimated=4096,
            max_output_tokens_estimated=512,
            defaults=defaults(),
            provider_timeout_seconds=4.0,
        )

        self.assertEqual(result.policy.provenance.decision_id, "decision-1")
        self.assertEqual(len(provider.calls), 1)
        provider_request = provider.calls[0]
        self.assertEqual(provider_request.model, "vendor/model-a")
        self.assertEqual(provider_request.messages, gateway_request().messages)
        self.assertEqual(provider_request.max_output_tokens, 512)
        self.assertEqual(provider_request.timeout_seconds, 4.0)
        self.assertFalse(hasattr(provider_request, "risk_level"))
        self.assertFalse(hasattr(provider_request, "data_classification"))
        self.assertFalse(hasattr(provider_request, "policy_digest"))
