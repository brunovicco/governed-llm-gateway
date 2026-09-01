import asyncio
from datetime import date
from decimal import Decimal
from uuid import UUID

import pytest
from governed_llm_gateway_contracts import (
    Capability,
    DataClassification,
    GatewayRequest,
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
from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderRequest,
    ProviderResponse,
)
from governed_llm_gateway_core.application.ranking import (
    RankedCandidate,
    RankingDecision,
    ScoreBreakdown,
)
from governed_llm_gateway_core.application.resilience import (
    InMemoryHealthTracker,
    ResilienceExecutionError,
    ResilientExecutionService,
    StaticProviderResolver,
)
from governed_llm_gateway_core.domain.model_registry import ModelDeployment, PricingMetadata
from governed_llm_gateway_core.domain.resilience import RetryPolicy

REQUEST_ID = UUID("77777777-7777-4777-8777-777777777777")
TODAY = date(2026, 9, 1)
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}
TOOL_SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "string"}},
    "required": ["value"],
    "additionalProperties": False,
}


class CapturingProvider:
    def __init__(self, response: ProviderResponse | ProviderError) -> None:
        self.response = response
        self.calls: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        if isinstance(self.response, ProviderError):
            raise self.response
        return self.response


def gateway_request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="agent.tool-use",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(tool_calling=True, structured_output=True),
        messages=(Message(role=MessageRole.USER, content="hello"),),
        tools=(
            ToolDefinition(
                name="echo_value",
                description="Return the supplied value.",
                input_schema=TOOL_SCHEMA,
            ),
        ),
        structured_output=StructuredOutputSchema(name="answer_schema", schema=SCHEMA),
    )


def deployment(deployment_id: str, provider: str) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider=provider,
        model_id=f"model/{deployment_id}",
        model_group="agentic-strong",
        api_family="openai-compatible",
        capabilities=frozenset(
            {Capability.TEXT, Capability.TOOL_CALLING, Capability.STRUCTURED_OUTPUT}
        ),
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


def ranked(candidate: ModelDeployment, score: str) -> RankedCandidate:
    value = Decimal(score)
    return RankedCandidate(
        deployment=candidate,
        score=ScoreBreakdown(
            quality=value,
            reliability=Decimal("0"),
            latency=Decimal("0"),
            cost=Decimal("0"),
            availability=Decimal("0"),
            total=value,
        ),
        estimated_cost_usd=Decimal("0.01"),
    )


def decision(selected: ModelDeployment, *alternatives: ModelDeployment) -> RankingDecision:
    return RankingDecision(
        routing=RoutingProvenance(
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
            provider=selected.provider,
            model=selected.model_id,
            deployment=selected.deployment_id,
        ),
        ranking_policy_digest="d" * 64,
        score_snapshot_id="static-v1",
        selected=ranked(selected, "1"),
        alternatives=tuple(ranked(item, "0.5") for item in alternatives),
        rejected_candidates=(),
    )


def test_resilience_forwards_schema_and_tools_to_selected_provider() -> None:
    selected = deployment("candidate-a", "provider-a")
    provider = CapturingProvider(ProviderResponse(text='{"answer":"ok"}'))
    service = ResilientExecutionService(
        InMemoryHealthTracker(),
        StaticProviderResolver({("provider-a", "openai-compatible"): provider}),
        RetryPolicy(max_attempts_per_deployment=1, max_fallbacks=0),
    )

    asyncio.run(service.execute(gateway_request(), decision(selected), max_output_tokens=100))

    assert len(provider.calls) == 1
    assert provider.calls[0].structured_output == gateway_request().structured_output
    assert provider.calls[0].tools == gateway_request().tools


def test_invalid_structured_output_is_permanent_and_never_falls_back() -> None:
    selected = deployment("candidate-a", "provider-a")
    alternative = deployment("candidate-b", "provider-b")
    provider_a = CapturingProvider(
        ProviderError(
            provider="provider-a",
            code=ProviderErrorCode.INVALID_STRUCTURED_OUTPUT,
            message="provider-a output failed schema validation",
            retryable=False,
        )
    )
    provider_b = CapturingProvider(ProviderResponse(text="must-not-run"))
    service = ResilientExecutionService(
        InMemoryHealthTracker(),
        StaticProviderResolver(
            {
                ("provider-a", "openai-compatible"): provider_a,
                ("provider-b", "openai-compatible"): provider_b,
            }
        ),
        RetryPolicy(max_attempts_per_deployment=3, max_fallbacks=1),
    )

    with pytest.raises(ResilienceExecutionError) as exc_info:
        asyncio.run(
            service.execute(
                gateway_request(),
                decision(selected, alternative),
                max_output_tokens=100,
            )
        )

    assert exc_info.value.last_error_code is ProviderErrorCode.INVALID_STRUCTURED_OUTPUT
    assert len(provider_a.calls) == 1
    assert provider_b.calls == []


def test_invalid_tool_call_is_permanent_and_never_falls_back() -> None:
    selected = deployment("candidate-a", "provider-a")
    alternative = deployment("candidate-b", "provider-b")
    provider_a = CapturingProvider(
        ProviderError(
            provider="provider-a",
            code=ProviderErrorCode.INVALID_TOOL_CALL,
            message="provider-a tool arguments failed schema validation",
            retryable=False,
        )
    )
    provider_b = CapturingProvider(ProviderResponse(text="must-not-run"))
    service = ResilientExecutionService(
        InMemoryHealthTracker(),
        StaticProviderResolver(
            {
                ("provider-a", "openai-compatible"): provider_a,
                ("provider-b", "openai-compatible"): provider_b,
            }
        ),
        RetryPolicy(max_attempts_per_deployment=3, max_fallbacks=1),
    )

    with pytest.raises(ResilienceExecutionError) as exc_info:
        asyncio.run(
            service.execute(
                gateway_request(),
                decision(selected, alternative),
                max_output_tokens=100,
            )
        )

    assert exc_info.value.last_error_code is ProviderErrorCode.INVALID_TOOL_CALL
    assert len(provider_a.calls) == 1
    assert provider_b.calls == []
