"""The shared-health adapter against a real RESP server.

Skipped unless GATEWAY_SHARED_HEALTH_URL points at one, so the default credential-free
gate is unaffected. The `redis-health` workflow supplies both Valkey and Redis Open
Source, which is the point: the adapter uses only core data types and Lua, so if the two
ever disagree the defect is here rather than in a server.
"""

import asyncio
import os
import unittest

import pytest
import redis.asyncio as aioredis
from governed_llm_gateway_core.adapters.health_redis import (
    RedisDeploymentHealthTracker,
    RedisHealthKeyspace,
)
from governed_llm_gateway_core.application.provider import ProviderError, ProviderErrorCode
from governed_llm_gateway_core.domain.resilience import CircuitBreakerPolicy, CircuitState

SERVER_URL = os.environ.get("GATEWAY_SHARED_HEALTH_URL")
DEPLOYMENT = "deployment-a"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not SERVER_URL, reason="GATEWAY_SHARED_HEALTH_URL is not configured"),
]


def _rate_limit() -> ProviderError:
    return ProviderError(
        provider="provider-a",
        code=ProviderErrorCode.RATE_LIMIT,
        message="sanitized",
        retryable=True,
        status_code=429,
    )


class SharedHealthServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        assert SERVER_URL is not None
        self.client = aioredis.from_url(SERVER_URL, decode_responses=True)
        await self.client.flushdb()
        self.now = 1_000_000.0
        self.keyspace = RedisHealthKeyspace(prefix="integration")
        policy = CircuitBreakerPolicy(failure_threshold=2, cooldown_seconds=30)
        self.replica_a = RedisDeploymentHealthTracker(
            self.client, policy, keyspace=self.keyspace, clock=lambda: self.now
        )
        self.replica_b = RedisDeploymentHealthTracker(
            self.client, policy, keyspace=self.keyspace, clock=lambda: self.now
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_replicas_converge_on_one_circuit_decision(self) -> None:
        await self.replica_a.record_failure(DEPLOYMENT, _rate_limit(), latency_ms=10)
        admission = await self.replica_b.allow_request(DEPLOYMENT)
        self.assertIsNotNone(admission)

        await self.replica_b.record_failure(
            DEPLOYMENT, _rate_limit(), latency_ms=10, admission=admission
        )

        self.assertFalse(await self.replica_a.allow_request(DEPLOYMENT))
        self.assertFalse(await self.replica_b.allow_request(DEPLOYMENT))

    async def test_the_full_open_half_open_closed_cycle_is_shared(self) -> None:
        for replica in (self.replica_a, self.replica_b):
            await replica.record_failure(DEPLOYMENT, _rate_limit(), latency_ms=10)
        self.assertIs((await self.replica_a.snapshot(DEPLOYMENT)).circuit_state, CircuitState.OPEN)

        self.now += 31
        admission = await self.replica_b.allow_request(DEPLOYMENT)
        self.assertIsNotNone(admission)
        self.assertIsNone(await self.replica_a.allow_request(DEPLOYMENT))
        self.assertIs(
            (await self.replica_a.snapshot(DEPLOYMENT)).circuit_state, CircuitState.HALF_OPEN
        )

        await self.replica_b.record_failure(
            DEPLOYMENT, _rate_limit(), latency_ms=10, admission=admission
        )
        self.assertIs((await self.replica_a.snapshot(DEPLOYMENT)).circuit_state, CircuitState.OPEN)

        self.now += 31
        admission = await self.replica_a.allow_request(DEPLOYMENT)
        self.assertIsNotNone(admission)
        await self.replica_a.record_success(DEPLOYMENT, latency_ms=12, admission=admission)
        self.assertIs(
            (await self.replica_b.snapshot(DEPLOYMENT)).circuit_state, CircuitState.CLOSED
        )

    async def test_concurrent_failures_are_not_lost_to_a_read_modify_write_race(self) -> None:
        """Every transition is one server-side script, so counters cannot interleave."""
        import asyncio

        replicas = [
            RedisDeploymentHealthTracker(
                self.client,
                CircuitBreakerPolicy(failure_threshold=100, cooldown_seconds=30),
                keyspace=self.keyspace,
                clock=lambda: self.now,
            )
            for _ in range(10)
        ]

        await asyncio.gather(
            *(
                replica.record_failure(DEPLOYMENT, _rate_limit(), latency_ms=1)
                for replica in replicas
            )
        )

        snapshot = await self.replica_a.snapshot(DEPLOYMENT)
        self.assertEqual(snapshot.request_count, 10)
        self.assertEqual(snapshot.transient_failure_count, 10)
        self.assertEqual(snapshot.rate_limit_count, 10)

    async def test_state_expires_so_a_retired_deployment_leaves_nothing_behind(self) -> None:
        await self.replica_a.record_success(DEPLOYMENT, latency_ms=1)

        ttl = await self.client.ttl(self.keyspace.health_key(DEPLOYMENT))

        self.assertGreater(ttl, 0)

    async def test_concurrent_probe_claims_across_clients_admit_one_owner(self) -> None:
        for replica in (self.replica_a, self.replica_b):
            await replica.record_failure(DEPLOYMENT, _rate_limit(), latency_ms=1)
        self.now += 30
        assert SERVER_URL is not None
        other_client = aioredis.from_url(SERVER_URL, decode_responses=False)
        self.addAsyncCleanup(other_client.aclose)
        other = RedisDeploymentHealthTracker(
            other_client,
            CircuitBreakerPolicy(failure_threshold=2),
            keyspace=self.keyspace,
            clock=lambda: self.now,
        )
        results = await asyncio.gather(
            *(
                replica.allow_request(DEPLOYMENT, attempt_id=f"attempt-{index}")
                for index, replica in enumerate([self.replica_a, other] * 8)
            )
        )
        owners = [result for result in results if result is not None]
        self.assertEqual(len(owners), 1)
        owner = owners[0]
        self.assertTrue(await other.is_admitted(owner))
        recheck = await other.allow_request(DEPLOYMENT, attempt_id=owner.attempt_id)
        self.assertEqual(recheck, owner)
        await self.replica_a.release_request(owner)
        replacement = await other.allow_request(DEPLOYMENT)
        assert replacement is not None
        self.assertNotEqual(owner.generation, replacement.generation)
        await self.replica_a.release_request(owner)
        self.assertFalse(
            await self.replica_a.record_success(DEPLOYMENT, latency_ms=1, admission=owner)
        )
        self.assertTrue(await other.record_success(DEPLOYMENT, latency_ms=1, admission=replacement))

    async def test_abandoned_probe_recovers_without_accepting_old_outcome(self) -> None:
        for replica in (self.replica_a, self.replica_b):
            await replica.record_failure(DEPLOYMENT, _rate_limit(), latency_ms=1)
        self.now += 30
        owner = await self.replica_a.allow_request(DEPLOYMENT)
        assert owner is not None
        self.now += 60
        self.assertFalse(await self.replica_b.is_admitted(owner))
        replacement = await self.replica_b.allow_request(DEPLOYMENT)
        assert replacement is not None
        await self.replica_a.record_failure(
            DEPLOYMENT, _rate_limit(), latency_ms=1, admission=owner
        )
        self.assertFalse(
            await self.replica_a.record_success(DEPLOYMENT, latency_ms=1, admission=owner)
        )
        self.assertEqual((await self.replica_b.snapshot(DEPLOYMENT)).request_count, 2)
        self.assertTrue(
            await self.replica_b.record_success(DEPLOYMENT, latency_ms=1, admission=replacement)
        )

    async def test_production_default_uses_server_time_for_cooldown_and_lease(self) -> None:
        tracker = RedisDeploymentHealthTracker(
            self.client,
            CircuitBreakerPolicy(failure_threshold=1, cooldown_seconds=0.001),
            keyspace=self.keyspace,
        )
        admission = await tracker.allow_request(DEPLOYMENT)
        assert admission is not None
        await tracker.record_failure(DEPLOYMENT, _rate_limit(), latency_ms=1, admission=admission)
        opened = await self.client.hget(self.keyspace.health_key(DEPLOYMENT), "opened_at_ms")
        assert opened is not None
        server_seconds, _ = await self.client.time()
        self.assertLess(abs(int(opened) - int(server_seconds) * 1000), 2000)
        await asyncio.sleep(0.003)
        probe = await tracker.allow_request(DEPLOYMENT)
        assert probe is not None and probe.is_probe
        self.assertTrue(await tracker.is_admitted(probe))
        self.assertTrue(await tracker.record_success(DEPLOYMENT, latency_ms=1, admission=probe))


if __name__ == "__main__":
    unittest.main()
