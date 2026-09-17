"""Bound recovery probes without introducing a total normal-execution deadline."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable

from governed_llm_gateway_core.domain.resilience import HealthAdmission

from .health import DeploymentHealthPort
from .provider import ProviderError, ProviderErrorCode, ProviderStreamEvent


def probe_expired_error(provider: str) -> ProviderError:
    """Return a sanitized local timeout, not raw infrastructure details."""
    return ProviderError(
        provider=provider,
        code=ProviderErrorCode.TIMEOUT,
        message="half-open probe lifetime expired",
        retryable=True,
    )


async def bounded_probe_call[Result](
    admission: HealthAdmission, provider: str, call: Awaitable[Result]
) -> Result:
    """Only HALF_OPEN gets a probe deadline; normal provider timeout is unchanged."""
    if admission.probe_timeout_seconds is None:
        return await call
    try:
        async with asyncio.timeout(admission.probe_timeout_seconds):
            return await call
    except TimeoutError as exc:
        raise probe_expired_error(provider) from exc


async def bounded_probe_events(
    admission: HealthAdmission,
    provider: str,
    events: AsyncGenerator[ProviderStreamEvent],
    health: DeploymentHealthPort,
) -> AsyncGenerator[ProviderStreamEvent]:
    """Time upstream reads, never the caller's task while suspended at a yield.

    The caller owns/explicitly closes the upstream generator. Backpressure consumes
    lifetime, and resuming after expiry accepts no further upstream event.
    """
    loop = asyncio.get_running_loop()
    deadline = (
        None
        if admission.probe_timeout_seconds is None
        else loop.time() + admission.probe_timeout_seconds
    )
    while True:
        try:
            if admission.is_probe and not await health.is_admitted(admission):
                raise probe_expired_error(provider)
            if deadline is None:
                event = await anext(events)
            else:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise probe_expired_error(provider)
                try:
                    async with asyncio.timeout(remaining):
                        event = await anext(events)
                except TimeoutError as exc:
                    raise probe_expired_error(provider) from exc
            if admission.is_probe and not await health.is_admitted(admission):
                raise probe_expired_error(provider)
            yield event
        except StopAsyncIteration:
            return
