"""Deployment health and circuit-breaker port.

Runtime health is operational evidence, never authorization: a healthy deployment is
still only reachable if the Policy Router already authorized its model group, and an
unhealthy one narrows the eligible set rather than widening it.

The port is asynchronous because the only useful implementation beyond a single process
is a network round trip. Blocking the event loop on a socket read to decide whether a
circuit is open would trade one correctness problem for a worse one.
"""

from collections.abc import Sequence
from typing import Protocol

from governed_llm_gateway_core.domain.resilience import DeploymentHealthSnapshot

from .provider import ProviderError


class DeploymentHealthPort(Protocol):
    """Read and record per-deployment runtime health and circuit state."""

    async def snapshot(self, deployment_id: str) -> DeploymentHealthSnapshot:
        """Return current health, moving an expired open circuit to half-open."""
        ...

    async def snapshots(self, deployment_ids: Sequence[str]) -> dict[str, DeploymentHealthSnapshot]:
        """Return deterministic snapshots for all requested deployments."""
        ...

    async def allow_request(self, deployment_id: str) -> bool:
        """Reject while the circuit is open; allow one probe once cooldown has elapsed."""
        ...

    async def record_success(self, deployment_id: str, *, latency_ms: int) -> None:
        """Record success and close a half-open or degraded circuit."""
        ...

    async def record_failure(
        self,
        deployment_id: str,
        error: ProviderError,
        *,
        latency_ms: int,
    ) -> None:
        """Record sanitized failure metadata and open the circuit on bounded transients."""
        ...
