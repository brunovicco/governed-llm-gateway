import asyncio
from dataclasses import replace
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from governed_llm_gateway_contracts import DataClassification, RiskLevel
from governed_llm_gateway_core.application.policy import (
    PolicyAuthorizationDecision,
    PolicyRequestMetadata,
)
from governed_llm_gateway_core.domain.governance import ForwardableGovernanceAuthorization

from scripts import composition_fixture
from scripts.demo_authorization import DemoAuthorizationAdapter


class RecordingPolicyAdapter:
    def __init__(self) -> None:
        self.requests: list[PolicyRequestMetadata] = []

    async def authorize(self, request: PolicyRequestMetadata) -> PolicyAuthorizationDecision:
        self.requests.append(request)
        return cast(PolicyAuthorizationDecision, object())


def _request() -> PolicyRequestMetadata:
    return PolicyRequestMetadata(
        request_id=uuid4(),
        client_id=composition_fixture.CLIENT_ID,
        environment=composition_fixture.ENVIRONMENT,
        workload=composition_fixture.WORKLOAD,
        risk_level=RiskLevel.HIGH,
        data_classification=DataClassification.CONFIDENTIAL,
        context_tokens_estimated=composition_fixture.CONTEXT_TOKENS_ESTIMATED,
        max_output_tokens_estimated=composition_fixture.MAX_OUTPUT_TOKENS_ESTIMATED,
        structured_output_required=composition_fixture.STRUCTURED_OUTPUT_REQUIRED,
        max_latency_ms=composition_fixture.MAX_LATENCY_MS,
        max_cost_usd=Decimal(composition_fixture.MAX_COST_USD_MICROS) / Decimal(1_000_000),
    )


def test_demo_adapter_forwards_fresh_signed_request_to_real_policy_port() -> None:
    delegate = RecordingPolicyAdapter()
    adapter = DemoAuthorizationAdapter(delegate)

    asyncio.run(adapter.authorize(_request()))
    asyncio.run(adapter.authorize(_request()))

    assert len(delegate.requests) == 2
    authorizations = [item.runtime_authorization for item in delegate.requests]
    assert all(isinstance(item, ForwardableGovernanceAuthorization) for item in authorizations)
    forwarded = [cast(ForwardableGovernanceAuthorization, item) for item in authorizations]
    assert forwarded[0] is not forwarded[1]
    assert (
        forwarded[0].authorization.authorization_id != forwarded[1].authorization.authorization_id
    )
    assert all(
        item.authorization.request.workload == composition_fixture.WORKLOAD for item in forwarded
    )


def test_demo_adapter_rejects_out_of_fixture_request_before_pdp_call() -> None:
    delegate = RecordingPolicyAdapter()
    adapter = DemoAuthorizationAdapter(delegate)
    request = replace(_request(), workload="credit.other-workload")

    with pytest.raises(ValueError, match="outside the bounded demo authorization fixture"):
        asyncio.run(adapter.authorize(request))

    assert delegate.requests == []


def test_demo_adapter_can_forward_a_policy_denial_candidate_without_widening_scope() -> None:
    delegate = RecordingPolicyAdapter()
    adapter = DemoAuthorizationAdapter(delegate)
    restricted = replace(_request(), data_classification=DataClassification.RESTRICTED)

    asyncio.run(adapter.authorize(restricted))

    forwarded = delegate.requests[0].runtime_authorization
    assert forwarded is not None
    assert forwarded.authorization.data_classification is DataClassification.RESTRICTED
