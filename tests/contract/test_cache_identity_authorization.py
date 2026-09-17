"""The coordinator decides what may be cached, using the effective context."""

import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID

from governed_llm_gateway_api.stream_generate import _cache_identity
from governed_llm_gateway_contracts import (
    Capability,
    DataClassification,
    GatewayRequest,
    ImageInput,
    ImageMediaType,
    Message,
    MessageRole,
    Modality,
    PolicyProvenance,
    RiskLevel,
    RoutingProvenance,
    StructuredOutputSchema,
    ToolDefinition,
    WorkloadRequirements,
)
from governed_llm_gateway_core.application.ranking import (
    RankedCandidate,
    RankingDecision,
    ScoreBreakdown,
)
from governed_llm_gateway_core.domain.model_registry import ModelDeployment, PricingMetadata
from governed_llm_gateway_core.domain.response_cache import (
    ResponseCacheIdentity,
    ResponseCachePolicy,
)
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext

REQUEST_ID = UUID("22222222-2222-4222-8222-222222222222")
TODAY = date(2026, 9, 1)
POLICY = ResponseCachePolicy(
    enabled=True, allowed_workloads=frozenset({"rag.answer"}), ttl_seconds=300
)


def _context(
    *,
    client_id: str = "client-a",
    workload: str = "rag.answer",
    classification: DataClassification = DataClassification.PUBLIC,
) -> EffectivePolicyContext:
    return EffectivePolicyContext(
        client_id=client_id,
        environment="development",
        workload=workload,
        risk_level=RiskLevel.LOW,
        data_classification=classification,
    )


def _request(**overrides: object) -> GatewayRequest:
    fields: dict[str, object] = {
        "schema_version": "1.0",
        "request_id": REQUEST_ID,
        "workload": "rag.answer",
        "risk_level": RiskLevel.LOW,
        # The caller declares public; only the effective context decides.
        "data_classification": DataClassification.PUBLIC,
        "requirements": WorkloadRequirements(streaming=True),
        "messages": (Message(role=MessageRole.USER, content="explain routing"),),
    }
    fields.update(overrides)
    return GatewayRequest(**fields)  # type: ignore[arg-type]


def _decision() -> RankingDecision:
    deployment = ModelDeployment(
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
        max_data_classification=DataClassification.RESTRICTED,
        allowed_environments=frozenset({"development"}),
        enabled=True,
        source_date=TODAY,
        catalog_version="catalog-v1",
    )
    value = Decimal("1")
    return RankingDecision(
        routing=RoutingProvenance(
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
        ),
        ranking_policy_digest="d" * 64,
        score_snapshot_id="static-v1",
        selected=RankedCandidate(
            deployment=deployment,
            score=ScoreBreakdown(
                quality=value,
                reliability=Decimal("0"),
                latency=Decimal("0"),
                cost=Decimal("0"),
                availability=Decimal("0"),
                total=value,
            ),
            estimated_cost_usd=Decimal("0.01"),
        ),
        alternatives=(),
        rejected_candidates=(),
    )


def _identity_for(
    *,
    policy: ResponseCachePolicy = POLICY,
    request: GatewayRequest | None = None,
    context: EffectivePolicyContext | None = None,
    decision: RankingDecision | None = None,
) -> ResponseCacheIdentity | None:
    return _cache_identity(
        policy,
        request=request or _request(),
        effective_context=context or _context(),
        decision=decision or _decision(),
        max_output_tokens=2000,
    )


class EffectiveClassificationTests(unittest.TestCase):
    def test_a_permitted_request_gets_an_identity(self) -> None:
        self.assertIsNotNone(_identity_for())

    def test_the_binding_raised_classification_is_what_decides(self) -> None:
        """The caller declares public; the binding raised it. Caching must obey the binding."""
        raised = _context(classification=DataClassification.CONFIDENTIAL)

        self.assertIsNone(_identity_for(context=raised))

    def test_the_identity_records_the_effective_classification(self) -> None:
        identity = _identity_for()

        assert identity is not None
        self.assertIs(identity.data_classification, DataClassification.PUBLIC)

    def test_authenticated_clients_have_separate_identities(self) -> None:
        first = _identity_for()
        second = _identity_for(context=_context(client_id="client-b"))
        assert first is not None and second is not None
        self.assertNotEqual(first.digest, second.digest)

    def test_caller_identity_cannot_select_another_clients_cache(self) -> None:
        first = _identity_for(request=_request(agent_identity="client-b"))
        unchanged = _identity_for(request=_request(agent_identity="anything-else"))
        other = _identity_for(context=_context(client_id="client-b"))
        assert first is not None and unchanged is not None and other is not None
        self.assertEqual(first.client_id, "client-a")
        self.assertEqual(first.digest, unchanged.digest)
        self.assertNotEqual(first.digest, other.digest)

    def test_a_pdp_policy_change_invalidates_the_identity(self) -> None:
        decision = _decision()
        changed = replace(
            decision,
            routing=replace(
                decision.routing,
                policy=replace(decision.routing.policy, policy_digest="sha256:" + "f" * 64),
            ),
        )
        first = _identity_for(decision=decision)
        second = _identity_for(decision=changed)
        assert first is not None and second is not None
        self.assertEqual(first.policy_digest, decision.routing.policy.policy_digest)
        self.assertNotEqual(first.digest, second.digest)

    def test_a_workload_outside_the_allowlist_is_not_cached(self) -> None:
        self.assertIsNone(_identity_for(context=_context(workload="reasoning.complex")))

    def test_a_disabled_policy_never_produces_an_identity(self) -> None:
        self.assertIsNone(_identity_for(policy=ResponseCachePolicy()))


class RequestShapeTests(unittest.TestCase):
    def test_business_tool_definitions_are_not_cached(self) -> None:
        request = _request(
            requirements=WorkloadRequirements(streaming=True, tool_calling=True),
            tools=(
                ToolDefinition(
                    name="synthetic_lookup",
                    description="synthetic tool; never executed",
                    input_schema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                ),
            ),
        )
        self.assertIsNone(_identity_for(request=request))

    def test_structured_output_is_not_cached(self) -> None:
        request = _request(
            requirements=WorkloadRequirements(streaming=True, structured_output=True),
            structured_output=StructuredOutputSchema(
                name="answer",
                schema={"type": "object", "properties": {}, "additionalProperties": False},
            ),
        )

        self.assertIsNone(_identity_for(request=request))

    def test_image_input_is_not_cached(self) -> None:
        request = _request(
            requirements=WorkloadRequirements(streaming=True, vision=True),
            messages=(
                Message(
                    role=MessageRole.USER,
                    content="describe this",
                    images=(
                        ImageInput(media_type=ImageMediaType.PNG, url="https://example.test/a.png"),
                    ),
                ),
            ),
        )

        self.assertIsNone(_identity_for(request=request))


if __name__ == "__main__":
    unittest.main()
