from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from governed_llm_gateway_contracts import (
    ExecutionStatus,
    GatewayError,
    GatewayResponse,
    PolicyProvenance,
    ProviderExecution,
    RoutingProvenance,
    Usage,
)

from benchmarks.multimodal_response import normalize_multimodal_gateway_response
from benchmarks.runner import BenchmarkProviderFailure

_REQUEST_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _routing() -> RoutingProvenance:
    return RoutingProvenance(
        routing_decision_id="route-1",
        policy=PolicyProvenance(
            decision_id="decision-1",
            policy_id="policy-1",
            policy_version="1.0",
            policy_digest="sha256:policy",
        ),
        authorized_model_group="vision-approved",
        model_registry_digest="sha256:registry",
        ranking_policy_version="1.0",
        provider="openai",
        model="gpt-test",
        deployment="openai-gpt-test",
    )


def _execution(
    *,
    status: ExecutionStatus = ExecutionStatus.SUCCEEDED,
    latency_ms: int = 125,
) -> ProviderExecution:
    return ProviderExecution(
        provider="openai",
        model="gpt-test",
        deployment="openai-gpt-test",
        status=status,
        latency_ms=latency_ms,
        usage=Usage(
            input_tokens=10,
            output_tokens=4,
            total_tokens=14,
            total_cost_usd=Decimal("0.0123"),
        ),
        provider_request_id="provider-request-1",
        fallback_index=1,
    )


def test_successful_json_content_becomes_provider_call_evidence() -> None:
    response = GatewayResponse(
        request_id=_REQUEST_ID,
        status=ExecutionStatus.SUCCEEDED,
        content=(
            '{"top_left":"red","top_right":"green","bottom_left":"blue","bottom_right":"yellow"}'
        ),
        routing=_routing(),
        execution=_execution(),
    )

    call = normalize_multimodal_gateway_response(response)

    assert call.output == {
        "top_left": "red",
        "top_right": "green",
        "bottom_left": "blue",
        "bottom_right": "yellow",
    }
    assert call.latency_ms == 125
    assert call.ttft_ms is None
    assert call.input_units == 10
    assert call.output_units == 4
    assert call.cost_usd == Decimal("0.0123")
    assert call.fallback_count == 1


def test_non_json_success_remains_quality_output_not_provider_failure() -> None:
    response = GatewayResponse(
        request_id=_REQUEST_ID,
        status=ExecutionStatus.SUCCEEDED,
        content="I cannot identify the image.",
        routing=_routing(),
        execution=_execution(),
    )

    call = normalize_multimodal_gateway_response(response)

    assert call.output == "I cannot identify the image."


def test_structured_output_is_preferred_when_present() -> None:
    response = GatewayResponse(
        request_id=_REQUEST_ID,
        status=ExecutionStatus.SUCCEEDED,
        content="ignored",
        routing=_routing(),
        execution=_execution(),
        structured_output={"top_left": "red"},
    )

    call = normalize_multimodal_gateway_response(response)

    assert call.output == {"top_left": "red"}


def test_failed_gateway_response_becomes_availability_failure() -> None:
    response = GatewayResponse(
        request_id=_REQUEST_ID,
        status=ExecutionStatus.FAILED,
        content=None,
        routing=_routing(),
        execution=_execution(status=ExecutionStatus.FAILED, latency_ms=80),
        error=GatewayError(code="provider_timeout", message="provider timed out", retryable=True),
    )

    with pytest.raises(BenchmarkProviderFailure) as captured:
        normalize_multimodal_gateway_response(response)

    assert captured.value.code == "provider_timeout"
    assert captured.value.latency_ms == 80


def test_success_requires_terminal_execution_evidence() -> None:
    response = GatewayResponse(
        request_id=_REQUEST_ID,
        status=ExecutionStatus.SUCCEEDED,
        content="{}",
        routing=_routing(),
        execution=None,
    )

    with pytest.raises(ValueError, match="requires execution evidence"):
        normalize_multimodal_gateway_response(response)


def test_failed_response_requires_gateway_error_evidence() -> None:
    response = GatewayResponse(
        request_id=_REQUEST_ID,
        status=ExecutionStatus.FAILED,
        content=None,
        routing=_routing(),
        execution=None,
        error=None,
    )

    with pytest.raises(ValueError, match="requires gateway error evidence"):
        normalize_multimodal_gateway_response(response)
