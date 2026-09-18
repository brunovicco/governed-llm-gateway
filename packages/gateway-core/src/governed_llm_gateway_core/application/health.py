"""Deployment health and circuit-breaker port.

Runtime health is operational evidence, never authorization: a healthy deployment is
still only reachable if the Policy Router already authorized its model group, and an
unhealthy one narrows the eligible set rather than widening it.

The port is asynchronous because the only useful implementation beyond a single process
is a network round trip. Blocking the event loop on a socket read to decide whether a
circuit is open would trade one correctness problem for a worse one.
"""

import asyncio
import sys
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager, suppress
from typing import Protocol
from uuid import uuid4

from governed_llm_gateway_core.domain.resilience import DeploymentHealthSnapshot, HealthAdmission

from .execution_deadline import ExecutionDeadlineExceeded
from .provider import ProviderError


def health_attempt_id(value: str | None) -> str:
    """Generate a fresh internal owner, or validate a bounded explicit recheck ID."""
    if value is None:
        return uuid4().hex
    if not value or value.strip() != value or len(value) > 128:
        raise ValueError(
            "attempt_id must be a non-empty normalized string of at most 128 characters"
        )
    return value


class DeploymentHealthPort(Protocol):
    """Read and record per-deployment runtime health and circuit state."""

    async def snapshot(self, deployment_id: str) -> DeploymentHealthSnapshot:
        """Return current health, moving an expired open circuit to half-open."""
        ...

    async def snapshots(self, deployment_ids: Sequence[str]) -> dict[str, DeploymentHealthSnapshot]:
        """Return deterministic snapshots for all requested deployments."""
        ...

    async def allow_request(
        self, deployment_id: str, *, attempt_id: str | None = None
    ) -> HealthAdmission | None:
        """Admit one attempt; a live probe owner's repeated checks do not renew its lease."""
        ...

    async def release_request(self, admission: HealthAdmission) -> None:
        """Release a matching probe without reporting provider failure."""
        ...

    async def is_admitted(self, admission: HealthAdmission) -> bool:
        """Check an existing handle without acquiring or renewing ownership."""
        ...

    async def record_success(
        self, deployment_id: str, *, latency_ms: int, admission: HealthAdmission | None = None
    ) -> bool:
        """Record success; return false for a retired probe, which must not publish success.

        Uncorrelated reports cannot prove recovery of OPEN/HALF_OPEN circuits.
        """
        ...

    async def record_failure(
        self,
        deployment_id: str,
        error: ProviderError,
        *,
        latency_ms: int,
        admission: HealthAdmission | None = None,
    ) -> None:
        """Record sanitized failure metadata and open the circuit on bounded transients."""
        ...


@asynccontextmanager
async def health_admission_scope(
    health: DeploymentHealthPort,
    admission: HealthAdmission,
    *,
    cleanup_timeout_seconds: float | None = None,
) -> AsyncIterator[None]:
    """Release ownership without allowing a cleanup outage to replace cancellation."""

    async def release() -> None:
        if cleanup_timeout_seconds is None:
            await health.release_request(admission)
        else:
            async with asyncio.timeout(cleanup_timeout_seconds):
                await health.release_request(admission)

    try:
        yield
    finally:
        if isinstance(
            sys.exception(), asyncio.CancelledError | GeneratorExit | ExecutionDeadlineExceeded
        ):
            # Lease expiry recovers ownership on a shared-server cleanup outage.
            # Infrastructure details must not be logged or replace cancellation.
            with suppress(Exception):
                await release()
        else:
            await release()
