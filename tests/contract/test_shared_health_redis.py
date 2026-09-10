"""Shared circuit state must behave identically across replicas.

The property the in-process tracker cannot provide: two gateway replicas observing the
same deployment must converge on one circuit decision. These run against a RESP server
emulator so the default gate stays credential-free and serverless; the `redis-health`
workflow re-runs the same expectations against a real Valkey server.
"""

import unittest

import fakeredis.aioredis
from governed_llm_gateway_core.adapters.health_redis import (
    RedisDeploymentHealthTracker,
    RedisHealthKeyspace,
)
from governed_llm_gateway_core.application.provider import ProviderError, ProviderErrorCode
from governed_llm_gateway_core.domain.resilience import (
    CircuitBreakerPolicy,
    CircuitState,
    HealthStatus,
)

DEPLOYMENT = "deployment-a"


def _error(
    code: ProviderErrorCode, *, retryable: bool = True, status: int | None = None
) -> ProviderError:
    return ProviderError(
        provider="provider-a",
        code=code,
        message="sanitized",
        retryable=retryable,
        status_code=status,
    )


class SharedCircuitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        self.now = 1_000_000.0
        self.policy = CircuitBreakerPolicy(failure_threshold=2, cooldown_seconds=30)
        self.keyspace = RedisHealthKeyspace(prefix="test")
        self.replica_a = self._replica()
        self.replica_b = self._replica()
        self.addAsyncCleanup(self.client.aclose)

    def _replica(self) -> RedisDeploymentHealthTracker:
        return RedisDeploymentHealthTracker(
            self.client,
            self.policy,
            keyspace=self.keyspace,
            clock=lambda: self.now,
        )

    async def test_a_fresh_deployment_is_allowed(self) -> None:
        self.assertTrue(await self.replica_a.allow_request(DEPLOYMENT))

    async def test_failures_on_different_replicas_accumulate(self) -> None:
        """One failure per replica must open the circuit for both, not for neither."""
        await self.replica_a.record_failure(
            DEPLOYMENT, _error(ProviderErrorCode.RATE_LIMIT), latency_ms=10
        )
        self.assertTrue(await self.replica_b.allow_request(DEPLOYMENT))

        await self.replica_b.record_failure(
            DEPLOYMENT, _error(ProviderErrorCode.RATE_LIMIT), latency_ms=10
        )

        self.assertFalse(await self.replica_a.allow_request(DEPLOYMENT))
        self.assertFalse(await self.replica_b.allow_request(DEPLOYMENT))

    async def test_cooldown_admits_exactly_one_half_open_probe_view(self) -> None:
        for replica in (self.replica_a, self.replica_b):
            await replica.record_failure(
                DEPLOYMENT, _error(ProviderErrorCode.TIMEOUT), latency_ms=10
            )
        self.assertFalse(await self.replica_a.allow_request(DEPLOYMENT))

        self.now += 31

        self.assertTrue(await self.replica_b.allow_request(DEPLOYMENT))
        self.assertIs(
            (await self.replica_a.snapshot(DEPLOYMENT)).circuit_state,
            CircuitState.HALF_OPEN,
        )

    async def test_a_half_open_failure_reopens_for_every_replica(self) -> None:
        for replica in (self.replica_a, self.replica_b):
            await replica.record_failure(
                DEPLOYMENT, _error(ProviderErrorCode.TIMEOUT), latency_ms=10
            )
        self.now += 31
        await self.replica_b.allow_request(DEPLOYMENT)

        await self.replica_b.record_failure(
            DEPLOYMENT, _error(ProviderErrorCode.TIMEOUT), latency_ms=10
        )

        self.assertIs(
            (await self.replica_a.snapshot(DEPLOYMENT)).circuit_state,
            CircuitState.OPEN,
        )

    async def test_success_closes_the_circuit_for_every_replica(self) -> None:
        for replica in (self.replica_a, self.replica_b):
            await replica.record_failure(
                DEPLOYMENT, _error(ProviderErrorCode.TIMEOUT), latency_ms=10
            )
        self.now += 31
        await self.replica_b.allow_request(DEPLOYMENT)

        await self.replica_b.record_success(DEPLOYMENT, latency_ms=12)

        snapshot = await self.replica_a.snapshot(DEPLOYMENT)
        self.assertIs(snapshot.circuit_state, CircuitState.CLOSED)
        self.assertEqual(snapshot.consecutive_transient_failures, 0)


class FailureClassificationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        self.tracker = RedisDeploymentHealthTracker(
            self.client,
            CircuitBreakerPolicy(failure_threshold=2, cooldown_seconds=30),
            keyspace=RedisHealthKeyspace(prefix="test"),
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_a_permanent_failure_never_opens_the_circuit(self) -> None:
        """Retrying an invalid request would not help, so it is not circuit evidence."""
        for _ in range(5):
            await self.tracker.record_failure(
                DEPLOYMENT,
                _error(ProviderErrorCode.INVALID_REQUEST, retryable=False),
                latency_ms=5,
            )

        snapshot = await self.tracker.snapshot(DEPLOYMENT)
        self.assertIs(snapshot.circuit_state, CircuitState.CLOSED)
        self.assertEqual(snapshot.transient_failure_count, 0)
        self.assertEqual(snapshot.request_count, 5)

    async def test_error_categories_are_counted_separately(self) -> None:
        await self.tracker.record_failure(
            DEPLOYMENT, _error(ProviderErrorCode.TIMEOUT), latency_ms=1
        )
        await self.tracker.record_failure(
            DEPLOYMENT, _error(ProviderErrorCode.UNAVAILABLE, status=503), latency_ms=1
        )

        snapshot = await self.tracker.snapshot(DEPLOYMENT)
        self.assertEqual(snapshot.timeout_count, 1)
        self.assertEqual(snapshot.server_error_count, 1)
        self.assertEqual(snapshot.rate_limit_count, 0)

    async def test_a_transient_run_broken_by_success_does_not_open(self) -> None:
        await self.tracker.record_failure(
            DEPLOYMENT, _error(ProviderErrorCode.TIMEOUT), latency_ms=1
        )
        await self.tracker.record_success(DEPLOYMENT, latency_ms=1)
        await self.tracker.record_failure(
            DEPLOYMENT, _error(ProviderErrorCode.TIMEOUT), latency_ms=1
        )

        self.assertIs((await self.tracker.snapshot(DEPLOYMENT)).circuit_state, CircuitState.CLOSED)

    async def test_an_unseen_deployment_reports_healthy_without_inventing_traffic(self) -> None:
        snapshot = await self.tracker.snapshot("never-called")

        self.assertIs(snapshot.status, HealthStatus.HEALTHY)
        self.assertEqual(snapshot.request_count, 0)
        self.assertIsNone(snapshot.last_latency_ms)


class KeyspaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        self.addAsyncCleanup(self.client.aclose)

    async def test_two_deployments_sharing_one_server_do_not_collide(self) -> None:
        tracker = RedisDeploymentHealthTracker(
            self.client, keyspace=RedisHealthKeyspace(prefix="a")
        )
        other = RedisDeploymentHealthTracker(self.client, keyspace=RedisHealthKeyspace(prefix="b"))

        await tracker.record_failure(DEPLOYMENT, _error(ProviderErrorCode.TIMEOUT), latency_ms=1)

        self.assertEqual((await other.snapshot(DEPLOYMENT)).request_count, 0)

    async def test_state_carries_an_expiry_so_retired_deployments_do_not_linger(self) -> None:
        keyspace = RedisHealthKeyspace(prefix="ttl", ttl_seconds=120)
        tracker = RedisDeploymentHealthTracker(self.client, keyspace=keyspace)

        await tracker.record_success(DEPLOYMENT, latency_ms=1)

        self.assertEqual(await self.client.ttl(keyspace.health_key(DEPLOYMENT)), 120)

    async def test_an_unnormalized_identifier_is_refused(self) -> None:
        tracker = RedisDeploymentHealthTracker(self.client)

        for rejected in ("", " deployment", "deployment "):
            with self.subTest(deployment_id=rejected), self.assertRaises(ValueError):
                await tracker.allow_request(rejected)


if __name__ == "__main__":
    unittest.main()
