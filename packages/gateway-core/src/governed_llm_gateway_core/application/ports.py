"""Application ports; concrete provider SDKs belong only in adapters in later phases."""

from typing import Protocol

from governed_llm_gateway_contracts import GatewayRequest, PolicyProvenance


class PolicyDecisionPort(Protocol):
    """Boundary to the deterministic Policy Model Router."""

    async def authorize(self, request: GatewayRequest) -> tuple[str, PolicyProvenance]:
        """Return the authorized logical model group and decision provenance."""
        ...
