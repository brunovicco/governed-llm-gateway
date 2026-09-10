"""Estimated-spend accounting: exact money, fail-closed budgets, no double counting."""

import unittest
from datetime import date
from decimal import Decimal

import fakeredis.aioredis
from governed_llm_gateway_core.adapters.spend_redis import RedisSpendLedger
from governed_llm_gateway_core.application.spend import (
    SpendAttribution,
    SpendGuard,
    SpendLedgerUnavailableError,
)
from governed_llm_gateway_core.domain.model_registry import PricingMetadata, estimated_cost_usd
from governed_llm_gateway_core.domain.spend import (
    SpendLimit,
    SpendPolicy,
    SpendPolicyError,
    SpendWindow,
    from_micro_usd,
    to_micro_usd,
)

TODAY = date(2026, 9, 10)
CLIENT = SpendAttribution(client_id="client-a", workload="rag.answer")


def _policy(limit_usd: str = "1.00", workload: str | None = None) -> SpendPolicy:
    return SpendPolicy(
        enabled=True,
        limits=(
            SpendLimit(
                client_id="client-a",
                window=SpendWindow.DAILY,
                limit_usd=Decimal(limit_usd),
                workload=workload,
            ),
        ),
    )


class MoneyPrecisionTests(unittest.TestCase):
    def test_micro_usd_round_trips_without_losing_a_cent(self) -> None:
        for amount in ("0.000001", "0.01", "1.234567", "999.999999"):
            with self.subTest(amount=amount):
                self.assertEqual(from_micro_usd(to_micro_usd(Decimal(amount))), Decimal(amount))

    def test_accumulating_small_amounts_stays_exact(self) -> None:
        """The failure mode a float ledger has: a thousand tenths of a cent."""
        total = sum(to_micro_usd(Decimal("0.001")) for _ in range(1000))

        self.assertEqual(from_micro_usd(total), Decimal("1.000000"))

    def test_a_negative_amount_is_refused(self) -> None:
        with self.assertRaises(SpendPolicyError):
            to_micro_usd(Decimal("-0.01"))

    def test_cost_comes_from_pinned_pricing_and_reported_usage(self) -> None:
        pricing = PricingMetadata(
            input_usd_per_million_tokens=Decimal("1.00"),
            output_usd_per_million_tokens=Decimal("2.00"),
            source_date=TODAY,
            snapshot_version="pricing-v1",
        )

        cost = estimated_cost_usd(pricing, input_tokens=1_000_000, output_tokens=500_000)

        self.assertEqual(cost, Decimal("2.00"))

    def test_a_deployment_without_pricing_yields_no_invented_cost(self) -> None:
        self.assertIsNone(estimated_cost_usd(None, input_tokens=10, output_tokens=10))


class PolicyShapeTests(unittest.TestCase):
    def test_budgets_are_off_by_default(self) -> None:
        self.assertEqual(SpendPolicy().limits_for(client_id="client-a", workload="rag.answer"), ())

    def test_an_enabled_policy_must_declare_a_limit(self) -> None:
        with self.assertRaises(SpendPolicyError):
            SpendPolicy(enabled=True)

    def test_duplicate_scopes_are_refused(self) -> None:
        limit = SpendLimit(client_id="client-a", window=SpendWindow.DAILY, limit_usd=Decimal("1"))
        with self.assertRaises(SpendPolicyError):
            SpendPolicy(enabled=True, limits=(limit, limit))

    def test_a_workload_limit_applies_only_to_that_workload(self) -> None:
        policy = _policy(workload="rag.answer")

        self.assertEqual(len(policy.limits_for(client_id="client-a", workload="rag.answer")), 1)
        self.assertEqual(policy.limits_for(client_id="client-a", workload="reasoning.complex"), ())

    def test_a_client_wide_limit_applies_to_every_workload(self) -> None:
        policy = _policy()

        self.assertEqual(
            len(policy.limits_for(client_id="client-a", workload="reasoning.complex")), 1
        )

    def test_windows_bucket_deterministically(self) -> None:
        self.assertEqual(SpendWindow.DAILY.key_for(TODAY), "2026-09-10")
        self.assertEqual(SpendWindow.MONTHLY.key_for(TODAY), "2026-09")


class _BrokenLedger:
    async def observed_micros(self, scope: str, window_key: str) -> int:
        del scope, window_key
        raise RuntimeError("ledger unreachable")

    async def add_micros(
        self, scope: str, window_key: str, amount_micros: int, *, retention_seconds: int
    ) -> int:
        del scope, window_key, amount_micros, retention_seconds
        raise RuntimeError("ledger unreachable")


class BudgetEnforcementTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        self.ledger = RedisSpendLedger(self.client, prefix="test")
        self.addAsyncCleanup(self.client.aclose)

    async def test_spend_below_the_limit_is_permitted(self) -> None:
        guard = SpendGuard(_policy("1.00"), self.ledger)
        await guard.record(CLIENT, Decimal("0.25"), today=TODAY)

        self.assertTrue((await guard.check(CLIENT, today=TODAY)).allowed)

    async def test_reaching_the_limit_exactly_refuses_the_next_request(self) -> None:
        """A budget that permits one more call at its ceiling can be exceeded by design."""
        guard = SpendGuard(_policy("1.00"), self.ledger)
        await guard.record(CLIENT, Decimal("1.00"), today=TODAY)

        decision = await guard.check(CLIENT, today=TODAY)

        self.assertFalse(decision.allowed)
        assert decision.exceeded is not None
        self.assertEqual(decision.exceeded.observed_usd, Decimal("1.000000"))
        self.assertEqual(decision.exceeded.limit_usd, Decimal("1.00"))

    async def test_a_refusal_names_the_limit_that_caused_it(self) -> None:
        guard = SpendGuard(_policy("0.10", workload="rag.answer"), self.ledger)
        await guard.record(CLIENT, Decimal("0.50"), today=TODAY)

        decision = await guard.check(CLIENT, today=TODAY)

        assert decision.exceeded is not None
        self.assertEqual(decision.exceeded.scope, "client-a:rag.answer:daily")
        self.assertEqual(decision.exceeded.window_key, "2026-09-10")

    async def test_a_different_day_starts_a_fresh_budget(self) -> None:
        guard = SpendGuard(_policy("1.00"), self.ledger)
        await guard.record(CLIENT, Decimal("2.00"), today=TODAY)

        self.assertFalse((await guard.check(CLIENT, today=TODAY)).allowed)
        self.assertTrue((await guard.check(CLIENT, today=date(2026, 9, 11))).allowed)

    async def test_another_client_is_unaffected(self) -> None:
        guard = SpendGuard(_policy("1.00"), self.ledger)
        await guard.record(CLIENT, Decimal("5.00"), today=TODAY)

        other = SpendAttribution(client_id="client-b", workload="rag.answer")
        self.assertTrue((await guard.check(other, today=TODAY)).allowed)

    async def test_an_unreadable_ledger_fails_closed(self) -> None:
        """Spending against a ceiling nobody can see is worse than refusing."""
        guard = SpendGuard(_policy("1.00"), _BrokenLedger())

        with self.assertRaises(SpendLedgerUnavailableError):
            await guard.check(CLIENT, today=TODAY)

    async def test_a_disabled_policy_permits_without_reading_the_ledger(self) -> None:
        guard = SpendGuard(SpendPolicy(), _BrokenLedger())

        self.assertTrue((await guard.check(CLIENT, today=TODAY)).allowed)


class RecordingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        self.ledger = RedisSpendLedger(self.client, prefix="test")
        self.guard = SpendGuard(_policy("10.00"), self.ledger)
        self.addAsyncCleanup(self.client.aclose)

    async def test_a_cached_answer_is_never_counted_again(self) -> None:
        """Its tokens were counted when the original call produced them."""
        await self.guard.record(CLIENT, Decimal("0.50"), today=TODAY, cached=True)

        self.assertEqual(await self.ledger.observed_micros("client-a:*:daily", "2026-09-10"), 0)

    async def test_an_absent_cost_records_nothing(self) -> None:
        await self.guard.record(CLIENT, None, today=TODAY)

        self.assertEqual(await self.ledger.observed_micros("client-a:*:daily", "2026-09-10"), 0)

    async def test_concurrent_records_do_not_lose_a_fraction_of_a_cent(self) -> None:
        import asyncio

        await asyncio.gather(
            *(self.guard.record(CLIENT, Decimal("0.001"), today=TODAY) for _ in range(50))
        )

        observed = await self.ledger.observed_micros("client-a:*:daily", "2026-09-10")
        self.assertEqual(from_micro_usd(observed), Decimal("0.050000"))

    async def test_a_ledger_write_failure_never_raises(self) -> None:
        """The caller already has their answer; losing an estimate must not undo that."""
        guard = SpendGuard(_policy("10.00"), _BrokenLedger())

        await guard.record(CLIENT, Decimal("0.50"), today=TODAY)

    async def test_buckets_expire_so_the_ledger_is_not_a_permanent_record(self) -> None:
        await self.guard.record(CLIENT, Decimal("0.50"), today=TODAY)

        ttl = await self.client.ttl(self.ledger.ledger_key("client-a:*:daily", "2026-09-10"))

        self.assertGreater(ttl, 0)
        self.assertLessEqual(ttl, SpendWindow.DAILY.retention_seconds)

    async def test_a_corrupt_bucket_is_surfaced_rather_than_read_as_zero(self) -> None:
        await self.client.set(self.ledger.ledger_key("client-a:*:daily", "2026-09-10"), "oops")

        with self.assertRaises(ValueError):
            await self.ledger.observed_micros("client-a:*:daily", "2026-09-10")


if __name__ == "__main__":
    unittest.main()
