"""Estimated-spend ledger port and the guard that enforces budgets.

The guard runs after the Policy Model Router has authorized a request and before any
provider work: an exhausted budget removes permission to execute and can never grant it.

Recording is deliberately asymmetric with enforcement. A refusal must be exact, so the
guard reads the ledger and fails closed when it cannot. A record is written after the
caller already has their answer, so a ledger failure there is swallowed — losing an
estimate is bad, losing a delivered answer is worse.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from governed_llm_gateway_core.domain.spend import (
    SpendDecision,
    SpendLimit,
    SpendPolicy,
    SpendWindow,
    evaluate_limit,
    to_micro_usd,
)


class SpendLedgerUnavailableError(RuntimeError):
    """Raised when accumulated spend cannot be read, so no budget can be trusted."""


class SpendLedgerPort(Protocol):
    """Accumulate and read estimated spend in integer micro-USD."""

    async def observed_micros(self, scope: str, window_key: str) -> int:
        """Return spend already accumulated in one scope's window bucket."""
        ...

    async def add_micros(
        self,
        scope: str,
        window_key: str,
        amount_micros: int,
        *,
        retention_seconds: int,
    ) -> int:
        """Add to one bucket atomically and return the new total."""
        ...


@dataclass(frozen=True, slots=True)
class SpendAttribution:
    """Who a recorded amount belongs to."""

    client_id: str
    workload: str

    def __post_init__(self) -> None:
        """Require attribution that can actually be reconciled later."""
        for name in ("client_id", "workload"):
            value = getattr(self, name)
            if not value or value.strip() != value:
                raise ValueError(f"{name} must be a normalized non-empty string")


class SpendGuard:
    """Enforce estimated-spend budgets and accumulate what execution implied."""

    def __init__(
        self,
        policy: SpendPolicy,
        ledger: SpendLedgerPort | None = None,
    ) -> None:
        """Bind deployment-owned limits and the ledger that accumulates against them."""
        self._policy = policy
        self._ledger = ledger

    @property
    def active(self) -> bool:
        """Return whether any budget can be enforced at all."""
        return self._policy.enabled and self._ledger is not None

    async def check(
        self,
        attribution: SpendAttribution,
        *,
        today: date,
    ) -> SpendDecision:
        """Return whether accumulated spend still permits this request.

        Fails closed. If the ledger cannot be read, the budget's state is unknown, and
        proceeding would mean spending against a ceiling nobody can see.
        """
        ledger = self._ledger
        if not self._policy.enabled or ledger is None:
            return SpendDecision(allowed=True)

        for limit in self._policy.limits_for(
            client_id=attribution.client_id,
            workload=attribution.workload,
        ):
            window_key = limit.window.key_for(today)
            try:
                observed = await ledger.observed_micros(limit.scope, window_key)
            except Exception as exc:
                raise SpendLedgerUnavailableError(
                    "accumulated spend could not be read, so no budget can be enforced"
                ) from exc
            exceeded = evaluate_limit(limit, observed_micros=observed, window_key=window_key)
            if exceeded is not None:
                return SpendDecision(allowed=False, exceeded=exceeded)
        return SpendDecision(allowed=True)

    async def record(
        self,
        attribution: SpendAttribution,
        amount_usd: Decimal | None,
        *,
        today: date,
        cached: bool = False,
    ) -> None:
        """Accumulate what one execution implied, against every governing limit.

        A cached answer records nothing: its tokens were already counted when the
        original call produced them, and counting them again would inflate the estimate
        every time the same question is asked.
        """
        ledger = self._ledger
        if not self._policy.enabled or ledger is None:
            return
        if cached or amount_usd is None or amount_usd <= 0:
            return

        micros = to_micro_usd(amount_usd)
        if micros == 0:
            return
        for limit in self._scopes(attribution):
            await self._add_best_effort(ledger, limit, micros, today=today)

    @staticmethod
    async def _add_best_effort(
        ledger: SpendLedgerPort,
        limit: SpendLimit,
        micros: int,
        *,
        today: date,
    ) -> None:
        """Accumulate one limit's bucket, never failing an answer the caller already has."""
        try:
            await ledger.add_micros(
                limit.scope,
                limit.window.key_for(today),
                micros,
                retention_seconds=limit.window.retention_seconds,
            )
        except Exception:
            return

    def _scopes(self, attribution: SpendAttribution) -> Sequence[SpendLimit]:
        return self._policy.limits_for(
            client_id=attribution.client_id,
            workload=attribution.workload,
        )


def window_keys(windows: Sequence[SpendWindow], today: date) -> dict[str, str]:
    """Return the bucket identifier for each window, for reporting."""
    return {window.value: window.key_for(today) for window in windows}
