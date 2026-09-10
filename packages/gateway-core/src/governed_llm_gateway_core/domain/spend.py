"""Estimated-spend accounting and budget limits.

**Estimated, never billed.** Every amount here is derived from the Model Registry's
pinned pricing metadata and the provider's reported token usage. That pricing is reviewed
at a source date and can drift from a provider's live catalog, so this is the gateway's
own estimate of what a call implied — it is not an invoice, and nothing in this module
may be presented as one. A deployment that reconciles against real provider billing will
find differences, and that is expected rather than a defect.

**Money is integer micro-USD.** Accumulating a budget in binary floating point loses
cents at exactly the scale that matters, and a shared counter across replicas must be
incremented atomically as an integer. Decimal is the boundary type; micro-USD is the
stored one.

**A budget narrows, it never widens.** Exhausting a limit removes a request's permission
to execute. It can never grant one, so this stays consistent with the permanent rule that
the Gateway's allowed set is a subset of what the Policy Model Router authorized.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

MICRO_USD = Decimal("0.000001")
_MICROS_PER_USD = 1_000_000


class SpendPolicyError(ValueError):
    """Raised when a spend policy would be ambiguous or unenforceable."""


class SpendWindow(StrEnum):
    """The period a limit accumulates over."""

    DAILY = "daily"
    MONTHLY = "monthly"

    def key_for(self, moment: date) -> str:
        """Return the deterministic bucket identifier this moment falls in."""
        if self is SpendWindow.DAILY:
            return moment.strftime("%Y-%m-%d")
        return moment.strftime("%Y-%m")

    @property
    def retention_seconds(self) -> int:
        """Return how long a closed bucket stays readable before expiring.

        Generous enough that a late-arriving record cannot land in an expired bucket,
        bounded so a ledger of estimated spend is not an indefinite record.
        """
        return 172_800 if self is SpendWindow.DAILY else 4_147_200


def to_micro_usd(amount: Decimal) -> int:
    """Convert USD to integer micro-USD, rounding half up at the sixth decimal."""
    if amount < 0:
        raise SpendPolicyError("a spend amount must not be negative")
    return int(amount.quantize(MICRO_USD, rounding=ROUND_HALF_UP) * _MICROS_PER_USD)


def from_micro_usd(micros: int) -> Decimal:
    """Convert integer micro-USD back to USD without losing a cent."""
    return (Decimal(micros) / _MICROS_PER_USD).quantize(MICRO_USD)


@dataclass(frozen=True, slots=True)
class SpendLimit:
    """One deployment-owned ceiling on estimated spend."""

    client_id: str
    window: SpendWindow
    limit_usd: Decimal
    workload: str | None = None

    def __post_init__(self) -> None:
        """Reject a limit that could not be enforced or attributed."""
        if not self.client_id or self.client_id.strip() != self.client_id:
            raise SpendPolicyError("client_id must be a normalized non-empty string")
        if self.workload is not None and (
            not self.workload or self.workload.strip() != self.workload
        ):
            raise SpendPolicyError("workload must be a normalized non-empty string or absent")
        if self.limit_usd <= 0:
            raise SpendPolicyError("limit_usd must be positive")

    @property
    def limit_micros(self) -> int:
        """Return the ceiling in the units the ledger accumulates."""
        return to_micro_usd(self.limit_usd)

    @property
    def scope(self) -> str:
        """Return the deterministic accumulation scope this limit applies to."""
        return f"{self.client_id}:{self.workload or '*'}:{self.window.value}"

    def applies_to(self, *, client_id: str, workload: str) -> bool:
        """Return whether this limit governs one request."""
        if self.client_id != client_id:
            return False
        return self.workload is None or self.workload == workload


@dataclass(frozen=True, slots=True)
class SpendPolicy:
    """Deployment-owned budget rules. Disabled by default."""

    enabled: bool = False
    limits: tuple[SpendLimit, ...] = ()

    def __post_init__(self) -> None:
        """Reject an enabled policy with nothing to enforce, or duplicate scopes."""
        if self.enabled and not self.limits:
            raise SpendPolicyError("an enabled spend policy must declare at least one limit")
        scopes = [limit.scope for limit in self.limits]
        if len(scopes) != len(set(scopes)):
            raise SpendPolicyError("spend limits must not repeat a scope")

    def limits_for(self, *, client_id: str, workload: str) -> tuple[SpendLimit, ...]:
        """Return every limit governing one request, in deterministic order."""
        if not self.enabled:
            return ()
        matching = [
            limit
            for limit in self.limits
            if limit.applies_to(client_id=client_id, workload=workload)
        ]
        return tuple(sorted(matching, key=lambda limit: limit.scope))


@dataclass(frozen=True, slots=True)
class BudgetExceeded:
    """The one limit that refused a request, and the evidence behind the refusal."""

    scope: str
    window: SpendWindow
    window_key: str
    observed_usd: Decimal
    limit_usd: Decimal


@dataclass(frozen=True, slots=True)
class SpendDecision:
    """Whether estimated spend permits a request to proceed."""

    allowed: bool
    exceeded: BudgetExceeded | None = None

    def __post_init__(self) -> None:
        """Require a refusal to name the limit that caused it."""
        if self.allowed and self.exceeded is not None:
            raise SpendPolicyError("an allowed decision must not carry an exceeded limit")
        if not self.allowed and self.exceeded is None:
            raise SpendPolicyError("a refusal must name the limit that caused it")


def evaluate_limit(
    limit: SpendLimit,
    *,
    observed_micros: int,
    window_key: str,
) -> BudgetExceeded | None:
    """Return the refusal for one limit, or None when it still permits spend.

    A limit is exhausted when observed spend has reached it, not merely passed it: a
    budget that permits one more call at exactly its ceiling is a budget that can be
    exceeded by design.
    """
    if observed_micros < limit.limit_micros:
        return None
    return BudgetExceeded(
        scope=limit.scope,
        window=limit.window,
        window_key=window_key,
        observed_usd=from_micro_usd(observed_micros),
        limit_usd=limit.limit_usd,
    )
