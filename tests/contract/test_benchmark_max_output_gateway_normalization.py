"""Integration contract for gateway terminal max-output benchmark evidence."""

from decimal import Decimal
from uuid import UUID

from benchmarks.multimodal_response import normalize_multimodal_gateway_response
from governed_llm_gateway_contracts import (
    ExecutionStatus,
    GatewayResponse,
    PolicyProvenance,
    ProviderExecution,
    RoutingProvenance,
    Usage,
)


def _routing() -> RoutingProvenance:
    return RoutingProvenance(
        routing_decision_id="sha256:" + "1" * 64,
        policy=PolicyProvenance(
            decision_id="policy-decision",
            policy_id="gateway-policy",
            policy_version="1.0.0",
            policy_digest="sha256:" + "2" * 64,
        ),
        authorized_model_group="balanced",
        model_registry_digest="sha256:" + "3" * 64,
        ranking_policy_version="ranking-v1",
        provider="openai",
        model="gpt-control",
        deployment="openai-primary",
    )


def test_gateway_response_normalization_preserves_max_output_attestation_evidence() -> None:
    response = GatewayResponse(
        request_id=UUID("41414141-4141-4414-8414-414141414141"),
        status=ExecutionStatus.SUCCEEDED,
        content='{"value":1}',
        routing=_routing(),
        execution=ProviderExecution(
            provider="openai",
            model="gpt-control",
            deployment="openai-primary",
            status=ExecutionStatus.SUCCEEDED,
            latency_ms=25,
            usage=Usage(
                input_tokens=10,
                output_tokens=2,
                total_cost_usd=Decimal("0.001"),
            ),
            api_family="openai-responses",
            max_output_tokens=4096,
        ),
    )

    call = normalize_multimodal_gateway_response(response)

    assert call.provider == "openai"
    assert call.model == "gpt-control"
    assert call.api_family == "openai-responses"
    assert call.max_output_tokens == 4096
