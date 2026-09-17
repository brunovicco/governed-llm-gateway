"""Observed-spend component boundaries, not API enforcement or a reservation protocol."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal

import fakeredis.aioredis
import pytest
from governed_llm_gateway_core.adapters.spend_redis import RedisSpendLedger
from governed_llm_gateway_core.application.spend import (
    SpendAttribution,
    SpendGuard,
    SpendLedgerUnavailableError,
)
from governed_llm_gateway_core.domain.spend import (
    SpendDecision,
    SpendLimit,
    SpendPolicy,
    SpendWindow,
)

_TODAY = date(2026, 9, 17)
_CLIENT = SpendAttribution(client_id="client-a", workload="rag.answer")


def _policy(window: SpendWindow = SpendWindow.DAILY, workload: str | None = None) -> SpendPolicy:
    return SpendPolicy(
        enabled=True,
        limits=(SpendLimit("client-a", window, Decimal("1.00"), workload),),
    )


class _Workers:
    """Independent guards/clients sharing an emulator, not actual replica processes."""

    def __init__(self, policy: SpendPolicy) -> None:
        server = fakeredis.FakeServer()
        self.clients = tuple(
            fakeredis.aioredis.FakeRedis(server=server, decode_responses=True) for _ in range(2)
        )
        self.ledgers = tuple(
            RedisSpendLedger(client, prefix="synthetic-spend") for client in self.clients
        )
        self.guards = tuple(SpendGuard(policy, ledger) for ledger in self.ledgers)

    async def observed(self, limit: SpendLimit, *, today: date = _TODAY) -> list[int]:
        return list(
            await asyncio.gather(
                *(
                    ledger.observed_micros(limit.scope, limit.window.key_for(today))
                    for ledger in self.ledgers
                )
            )
        )


@asynccontextmanager
async def _workers(policy: SpendPolicy) -> AsyncIterator[_Workers]:
    workers = _Workers(policy)
    try:
        yield workers
    finally:
        await asyncio.gather(*(client.aclose() for client in workers.clients))


async def _assert_refused(workers: _Workers, limit: SpendLimit, *, observed_usd: Decimal) -> None:
    decisions = await asyncio.gather(
        *(guard.check(_CLIENT, today=_TODAY) for guard in workers.guards)
    )
    for decision in decisions:
        assert not decision.allowed
        assert decision.exceeded is not None
        assert decision.exceeded.scope == limit.scope
        assert decision.exceeded.window is limit.window
        assert decision.exceeded.window_key == limit.window.key_for(_TODAY)
        assert decision.exceeded.observed_usd == observed_usd
        assert decision.exceeded.limit_usd == limit.limit_usd


def test_one_sequential_execution_can_pass_the_observed_ceiling() -> None:
    async def scenario() -> None:
        policy = _policy()
        async with _workers(policy) as workers:
            await workers.guards[0].record(_CLIENT, Decimal("0.90"), today=_TODAY)
            assert (await workers.guards[1].check(_CLIENT, today=_TODAY)).allowed
            assert await workers.observed(policy.limits[0]) == [900_000, 900_000]
            await workers.guards[1].record(_CLIENT, Decimal("0.20"), today=_TODAY)
            assert await workers.observed(policy.limits[0]) == [1_100_000, 1_100_000]
            await _assert_refused(workers, policy.limits[0], observed_usd=Decimal("1.10"))

    asyncio.run(scenario())


@pytest.mark.parametrize("window", [SpendWindow.DAILY, SpendWindow.MONTHLY])
@pytest.mark.parametrize("workload", [None, "rag.answer"])
def test_concurrent_checks_do_not_reserve_spend_before_recording(
    window: SpendWindow, workload: str | None
) -> None:
    async def scenario() -> None:
        policy = _policy(window, workload)
        limit = policy.limits[0]
        async with _workers(policy) as workers:
            await workers.guards[0].record(_CLIENT, Decimal("0.90"), today=_TODAY)
            checked = tuple(asyncio.Event() for _ in workers.guards)
            record_now = asyncio.Event()

            async def check_then_record(index: int) -> SpendDecision:
                decision = await workers.guards[index].check(_CLIENT, today=_TODAY)
                checked[index].set()
                # Represents the gap before usage is recorded, not real provider execution.
                await record_now.wait()
                if decision.allowed:
                    await workers.guards[index].record(_CLIENT, Decimal("0.20"), today=_TODAY)
                return decision

            tasks = tuple(asyncio.create_task(check_then_record(index)) for index in range(2))
            try:
                # Bound fixture waits only; ordering is event-driven, never sleep-driven.
                await asyncio.wait_for(
                    asyncio.gather(*(event.wait() for event in checked)), timeout=5
                )
                assert all(not task.done() for task in tasks)
                assert await workers.observed(limit) == [900_000, 900_000]
                record_now.set()
                decisions = await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)
                assert all(decision.allowed for decision in decisions)
                assert await workers.observed(limit) == [1_300_000, 1_300_000]
                await _assert_refused(workers, limit, observed_usd=Decimal("1.30"))
                for client, ledger in zip(workers.clients, workers.ledgers, strict=True):
                    ttl = await client.ttl(ledger.ledger_key(limit.scope, window.key_for(_TODAY)))
                    assert 0 < ttl <= window.retention_seconds
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(scenario())


def test_concurrent_checks_at_the_ceiling_all_refuse_without_changing_the_counter() -> None:
    async def scenario() -> None:
        policy = _policy()
        async with _workers(policy) as workers:
            await workers.guards[0].record(_CLIENT, Decimal("1.00"), today=_TODAY)
            decisions = await asyncio.gather(
                *(workers.guards[index % 2].check(_CLIENT, today=_TODAY) for index in range(16))
            )
            assert all(not decision.allowed for decision in decisions)
            await _assert_refused(workers, policy.limits[0], observed_usd=Decimal("1.00"))
            assert await workers.observed(policy.limits[0]) == [1_000_000, 1_000_000]

    asyncio.run(scenario())


def test_corrupt_shared_counter_fails_closed_for_both_guards() -> None:
    async def scenario() -> None:
        policy = _policy()
        async with _workers(policy) as workers:
            limit = policy.limits[0]
            key = workers.ledgers[0].ledger_key(limit.scope, limit.window.key_for(_TODAY))
            await workers.clients[0].set(key, "synthetic-invalid-counter")
            outcomes = await asyncio.gather(
                *(guard.check(_CLIENT, today=_TODAY) for guard in workers.guards),
                return_exceptions=True,
            )
            assert all(isinstance(outcome, SpendLedgerUnavailableError) for outcome in outcomes)
            assert await workers.clients[1].get(key) == "synthetic-invalid-counter"

    asyncio.run(scenario())


def test_concurrent_cached_records_do_not_charge_the_original_answer_again() -> None:
    async def scenario() -> None:
        policy = _policy()
        async with _workers(policy) as workers:
            await workers.guards[0].record(_CLIENT, Decimal("0.90"), today=_TODAY)
            await asyncio.gather(
                *(
                    workers.guards[index % 2].record(
                        _CLIENT, Decimal("0.20"), today=_TODAY, cached=True
                    )
                    for index in range(16)
                )
            )
            assert await workers.observed(policy.limits[0]) == [900_000, 900_000]
            decisions = await asyncio.gather(
                *(guard.check(_CLIENT, today=_TODAY) for guard in workers.guards)
            )
            assert all(decision.allowed for decision in decisions)

    asyncio.run(scenario())


def test_concurrent_records_keep_client_workload_and_window_buckets_separate() -> None:
    async def scenario() -> None:
        daily = SpendLimit("client-a", SpendWindow.DAILY, Decimal("1.00"))
        workload = SpendLimit("client-a", SpendWindow.DAILY, Decimal("1.00"), "rag.answer")
        monthly = SpendLimit("client-a", SpendWindow.MONTHLY, Decimal("1.00"))
        other_client = SpendLimit("client-b", SpendWindow.DAILY, Decimal("1.00"))
        policy = SpendPolicy(enabled=True, limits=(daily, workload, monthly, other_client))
        async with _workers(policy) as workers:
            await asyncio.gather(
                workers.guards[0].record(_CLIENT, Decimal("0.10"), today=_TODAY),
                workers.guards[1].record(
                    SpendAttribution("client-a", "reasoning.complex"), Decimal("0.20"), today=_TODAY
                ),
                workers.guards[1].record(
                    SpendAttribution("client-b", "rag.answer"), Decimal("0.30"), today=_TODAY
                ),
            )
            for limit, expected in (
                (daily, 300_000),
                (workload, 100_000),
                (monthly, 300_000),
                (other_client, 300_000),
            ):
                assert await workers.observed(limit) == [expected, expected]
            assert await workers.observed(daily, today=date(2026, 9, 18)) == [0, 0]
            assert await workers.observed(monthly, today=date(2026, 9, 18)) == [300_000, 300_000]
            assert await workers.observed(monthly, today=date(2026, 10, 1)) == [0, 0]

    asyncio.run(scenario())
