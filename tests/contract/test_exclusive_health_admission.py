"""Identical ownership/fencing semantics locally and across two RESP clients."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace

import fakeredis.aioredis
import pytest
from governed_llm_gateway_core.adapters.health_redis import (
    RedisDeploymentHealthTracker,
    RedisHealthKeyspace,
)
from governed_llm_gateway_core.application.health import DeploymentHealthPort
from governed_llm_gateway_core.application.provider import ProviderError, ProviderErrorCode
from governed_llm_gateway_core.application.resilience import InMemoryHealthTracker
from governed_llm_gateway_core.domain.resilience import CircuitBreakerPolicy, CircuitState

DEPLOYMENT = "deployment-a"
POLICY = CircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=10, probe_lease_seconds=5)
BACKENDS = pytest.mark.parametrize("backend", ["memory", "redis"])


class Clock:
    now = 1000.0

    def __call__(self) -> float:
        return self.now


def _failure(*, permanent: bool = False) -> ProviderError:
    return ProviderError(
        provider="provider-a",
        code=ProviderErrorCode.AUTHENTICATION if permanent else ProviderErrorCode.UNAVAILABLE,
        message="sanitized",
        status_code=401 if permanent else 503,
        retryable=not permanent,
    )


@asynccontextmanager
async def _replicas(
    backend: str, clock: Clock
) -> AsyncIterator[tuple[DeploymentHealthPort, DeploymentHealthPort]]:
    if backend == "memory":
        tracker = InMemoryHealthTracker(POLICY, clock=clock)
        yield tracker, tracker
        return
    server = fakeredis.FakeServer()
    async with (
        fakeredis.aioredis.FakeRedis(server=server, decode_responses=True) as client_a,
        fakeredis.aioredis.FakeRedis(server=server, decode_responses=False) as client_b,
    ):
        yield (
            RedisDeploymentHealthTracker(client_a, POLICY, clock=clock),
            RedisDeploymentHealthTracker(client_b, POLICY, clock=clock),
        )


async def _open(tracker: DeploymentHealthPort, clock: Clock) -> None:
    admission = await tracker.allow_request(DEPLOYMENT)
    assert admission is not None and not admission.is_probe
    await tracker.record_failure(DEPLOYMENT, _failure(), latency_ms=1, admission=admission)
    assert (await tracker.snapshot(DEPLOYMENT)).circuit_state is CircuitState.OPEN
    clock.now += POLICY.cooldown_seconds


@BACKENDS
def test_concurrent_claims_admit_one_owner_and_snapshots_do_not_claim(backend: str) -> None:
    async def scenario() -> None:
        clock = Clock()
        async with _replicas(backend, clock) as (first, second):
            await _open(first, clock)
            for _ in range(3):
                assert (await second.snapshot(DEPLOYMENT)).circuit_state is CircuitState.HALF_OPEN
            admissions = await asyncio.gather(
                *(
                    replica.allow_request(DEPLOYMENT, attempt_id=f"attempt-{index}")
                    for index, replica in enumerate([first, second] * 16)
                )
            )
            admitted = [item for item in admissions if item is not None]
            assert len(admitted) == 1
            owner = admitted[0]
            clock.now += 1
            recheck = await second.allow_request(DEPLOYMENT, attempt_id=owner.attempt_id)
            assert recheck is not None
            assert recheck.generation == owner.generation
            assert recheck.probe_timeout_seconds == 4
            assert await first.allow_request(DEPLOYMENT, attempt_id="other") is None
            assert await first.record_success(DEPLOYMENT, latency_ms=2, admission=owner)
            assert (await second.snapshot(DEPLOYMENT)).circuit_state is CircuitState.CLOSED
            assert not await second.record_success(DEPLOYMENT, latency_ms=2, admission=owner)
            assert (await first.snapshot(DEPLOYMENT)).success_count == 1

    asyncio.run(scenario())


@BACKENDS
def test_transient_probe_reopens_and_permanent_probe_only_releases(backend: str) -> None:
    async def scenario() -> None:
        clock = Clock()
        async with _replicas(backend, clock) as (first, second):
            await _open(first, clock)
            owner = await second.allow_request(DEPLOYMENT)
            assert owner is not None
            await second.record_failure(DEPLOYMENT, _failure(), latency_ms=2, admission=owner)
            assert (await first.snapshot(DEPLOYMENT)).circuit_state is CircuitState.OPEN
            assert await first.allow_request(DEPLOYMENT) is None
            clock.now += POLICY.cooldown_seconds
            owner = await first.allow_request(DEPLOYMENT)
            assert owner is not None
            await first.record_failure(
                DEPLOYMENT, _failure(permanent=True), latency_ms=2, admission=owner
            )
            snapshot = await second.snapshot(DEPLOYMENT)
            assert snapshot.circuit_state is CircuitState.HALF_OPEN
            assert snapshot.request_count == 3
            assert snapshot.transient_failure_count == 2
            assert not await first.record_success(DEPLOYMENT, latency_ms=2, admission=owner)
            assert await second.allow_request(DEPLOYMENT) is not None

    asyncio.run(scenario())


@BACKENDS
def test_release_is_neutral_and_retired_owner_cannot_release_replacement(backend: str) -> None:
    async def scenario() -> None:
        clock = Clock()
        async with _replicas(backend, clock) as (first, second):
            await _open(first, clock)
            owner = await first.allow_request(DEPLOYMENT)
            assert owner is not None
            before = await first.snapshot(DEPLOYMENT)
            await first.release_request(owner)
            assert await second.snapshot(DEPLOYMENT) == before
            replacement = await second.allow_request(DEPLOYMENT)
            assert replacement is not None and replacement.generation != owner.generation
            await first.release_request(owner)
            await first.record_failure(DEPLOYMENT, _failure(), latency_ms=2, admission=owner)
            assert not await first.record_success(DEPLOYMENT, latency_ms=2, admission=owner)
            assert await first.snapshot(DEPLOYMENT) == before
            assert await first.allow_request(DEPLOYMENT) is None
            assert await second.record_success(DEPLOYMENT, latency_ms=2, admission=replacement)

    asyncio.run(scenario())


@BACKENDS
def test_abandonment_expires_at_boundary_and_late_completion_is_fenced(backend: str) -> None:
    async def scenario() -> None:
        clock = Clock()
        async with _replicas(backend, clock) as (first, second):
            await _open(first, clock)
            owner = await first.allow_request(DEPLOYMENT)
            assert owner is not None
            clock.now += POLICY.probe_lease_seconds - 0.001
            assert await second.allow_request(DEPLOYMENT) is None
            clock.now += 0.001
            # Reading expires ownership without claiming it.
            assert (await second.snapshot(DEPLOYMENT)).circuit_state is CircuitState.HALF_OPEN
            replacement = await second.allow_request(DEPLOYMENT)
            assert replacement is not None and replacement.generation != owner.generation
            assert not await first.record_success(DEPLOYMENT, latency_ms=2, admission=owner)
            await first.record_failure(DEPLOYMENT, _failure(), latency_ms=2, admission=owner)
            await first.release_request(owner)
            assert await first.allow_request(DEPLOYMENT) is None
            assert (await second.snapshot(DEPLOYMENT)).request_count == 1
            assert await second.record_success(DEPLOYMENT, latency_ms=2, admission=replacement)

    asyncio.run(scenario())


@BACKENDS
def test_in_flight_closed_results_do_not_mutate_newer_circuit_generation(backend: str) -> None:
    async def scenario() -> None:
        clock = Clock()
        async with _replicas(backend, clock) as (first, second):
            late_success = await first.allow_request(DEPLOYMENT)
            late_failure = await second.allow_request(DEPLOYMENT)
            assert late_success is not None and late_failure is not None
            await _open(first, clock)
            owner = await second.allow_request(DEPLOYMENT)
            assert owner is not None
            assert await first.record_success(DEPLOYMENT, latency_ms=2, admission=late_success)
            await first.record_failure(DEPLOYMENT, _failure(), latency_ms=2, admission=late_failure)
            assert await first.allow_request(DEPLOYMENT) is None
            assert (await first.snapshot(DEPLOYMENT)).consecutive_transient_failures == 1
            assert await second.record_success(DEPLOYMENT, latency_ms=2, admission=owner)
            await first.record_failure(DEPLOYMENT, _failure(), latency_ms=2, admission=late_failure)
            snapshot = await second.snapshot(DEPLOYMENT)
            assert snapshot.circuit_state is CircuitState.CLOSED
            assert snapshot.consecutive_transient_failures == 0
            assert snapshot.request_count == 5

    asyncio.run(scenario())


@BACKENDS
def test_uncorrelated_recovery_is_rejected_and_deployments_are_isolated(backend: str) -> None:
    async def scenario() -> None:
        clock = Clock()
        async with _replicas(backend, clock) as (first, second):
            await _open(first, clock)
            await first.record_success(DEPLOYMENT, latency_ms=2)
            await first.record_failure(DEPLOYMENT, _failure(), latency_ms=2)
            assert (await second.snapshot(DEPLOYMENT)).circuit_state is CircuitState.HALF_OPEN
            owner = await first.allow_request(DEPLOYMENT)
            assert owner is not None
            assert await second.allow_request("deployment-b") is not None
            with pytest.raises(ValueError, match="another deployment"):
                await first.record_success("deployment-b", latency_ms=2, admission=owner)
            with pytest.raises(ValueError, match="another deployment"):
                await first.record_failure(
                    "deployment-b", _failure(), latency_ms=2, admission=owner
                )
            forged = replace(owner, attempt_id="non-owner")
            assert not await second.record_success(DEPLOYMENT, latency_ms=2, admission=forged)
            await second.release_request(forged)
            assert await second.allow_request(DEPLOYMENT) is None

    asyncio.run(scenario())


@pytest.mark.parametrize("field", ["cooldown_seconds", "probe_lease_seconds"])
@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf")])
def test_circuit_lifetimes_must_be_finite_and_positive(field: str, value: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        if field == "cooldown_seconds":
            replace(POLICY, cooldown_seconds=value)
        else:
            replace(POLICY, probe_lease_seconds=value)


def test_redis_key_ttl_cannot_evict_active_probe_or_cooldown() -> None:
    async def scenario() -> None:
        async with fakeredis.aioredis.FakeRedis() as client:
            with pytest.raises(ValueError, match="outlive"):
                RedisDeploymentHealthTracker(
                    client, POLICY, keyspace=RedisHealthKeyspace(ttl_seconds=5)
                )

    asyncio.run(scenario())


@BACKENDS
def test_ownership_check_never_reacquires_expired_or_released_handle(backend: str) -> None:
    async def scenario() -> None:
        clock = Clock()
        async with _replicas(backend, clock) as (first, second):
            await _open(first, clock)
            owner = await first.allow_request(DEPLOYMENT, attempt_id="owner")
            assert owner is not None and await second.is_admitted(owner)
            clock.now += POLICY.probe_lease_seconds
            assert not await second.is_admitted(owner)
            # It cannot renew, even after the same ID is accidentally used again.
            replacement = await first.allow_request(DEPLOYMENT, attempt_id=owner.attempt_id)
            assert replacement is not None and replacement.generation != owner.generation
            assert not await second.is_admitted(owner)
            assert await second.is_admitted(replacement)
            await first.release_request(replacement)
            assert not await second.is_admitted(replacement)

    asyncio.run(scenario())
