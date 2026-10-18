"""Demo-only signed authorization forwarding for the credential-free execution laboratory.

This module is deliberately outside the serving packages. It stands in for the not-yet-running
Verifiable AI Governance issuer only in the local portfolio demonstration; it is not an issuer,
production integration, or authorization source for normal Gateway startup.
"""

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from governed_llm_gateway_core.adapters import verify_governance_authorization_envelope
from governed_llm_gateway_core.application.policy import (
    PolicyAuthorizationDecision,
    PolicyRequestMetadata,
)

from scripts import composition_fixture


class _PolicyDecisionPort(Protocol):
    async def authorize(self, request: PolicyRequestMetadata) -> PolicyAuthorizationDecision: ...


class DemoAuthorizationAdapter:
    """Attach a fresh fixture signature before delegating to the real Policy Router adapter."""

    def __init__(self, delegate: _PolicyDecisionPort) -> None:
        if not callable(getattr(delegate, "authorize", None)):
            raise TypeError("delegate must implement PolicyDecisionPort")
        self._delegate = delegate

    async def authorize(self, request: PolicyRequestMetadata) -> PolicyAuthorizationDecision:
        """Forward only the request metadata bound into a short-lived test envelope."""
        if not isinstance(request, PolicyRequestMetadata):
            raise TypeError("request must use PolicyRequestMetadata")
        if (
            request.client_id != composition_fixture.CLIENT_ID
            or request.environment != composition_fixture.ENVIRONMENT
            or request.workload != composition_fixture.WORKLOAD
            or request.risk_level.value != composition_fixture.RISK_TIER
            or request.data_classification.value
            not in {composition_fixture.DATA_CLASSIFICATION, "restricted"}
            or request.context_tokens_estimated != composition_fixture.CONTEXT_TOKENS_ESTIMATED
            or request.max_output_tokens_estimated
            != composition_fixture.MAX_OUTPUT_TOKENS_ESTIMATED
            or request.structured_output_required != composition_fixture.STRUCTURED_OUTPUT_REQUIRED
            or request.max_latency_ms != composition_fixture.MAX_LATENCY_MS
            or request.max_cost_usd * 1_000_000 != composition_fixture.MAX_COST_USD_MICROS
        ):
            raise ValueError("request is outside the bounded demo authorization fixture")

        envelope = composition_fixture.mint_envelope(
            now=datetime.now(UTC),
            authorization_id=str(uuid4()),
            data_classification=request.data_classification.value,
        )
        forwardable = verify_governance_authorization_envelope(
            json.dumps(envelope), keys=composition_fixture.gateway_key_resolver()
        )
        return await self._delegate.authorize(replace(request, runtime_authorization=forwardable))
