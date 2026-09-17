"""Private ADR-0021 values, not admission, estimation, or durable-store guarantees.

Constructors validate shape/correlation only. Trusted attribution, complete policy/plan
coverage, cost bounds, usage finality and receipt issuance need separate capabilities.
No value grants authorization, dispatch, replay, or permission to release unknown cost.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, Context, Decimal, localcontext
from enum import StrEnum
from math import isfinite

from .spend import SpendWindow

MAX_SPEND_MICROS = 2**63 - 1
_MAX_USD = Decimal("9223372036854.775807")
_OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class SpendAdmissionContractError(ValueError):
    """Invalid private metadata; never echoes the rejected input."""


def to_reservation_micros(amount_usd: Decimal) -> int:
    """Round an already-established estimate upward, not prove its upper-bound validity.

    Use an independent decimal context with outward rounding, so caller precision or
    traps cannot round a positive fractional micro downward. Legacy conversion is unchanged.
    """
    if (
        type(amount_usd) is not Decimal
        or not amount_usd.is_finite()
        or amount_usd < 0
        or amount_usd > _MAX_USD
    ):
        raise SpendAdmissionContractError("spend estimate must be finite, nonnegative and bounded")
    if amount_usd == 0:
        return 0
    if amount_usd < Decimal("0.000001"):
        return 1
    with localcontext(Context(prec=20, rounding=ROUND_CEILING)):
        scaled = amount_usd * Decimal(1_000_000)
        return int(scaled.to_integral_value(rounding=ROUND_CEILING))


@dataclass(frozen=True, slots=True)
class SpendBudgetScope:
    """Canonical private scope tuple; window_start is the frozen UTC admission bucket."""

    client_id: str = field(repr=False)
    window: SpendWindow
    window_start: date
    workload: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Require bounded attribution and an unambiguous calendar bucket."""
        _require_id(self.client_id)
        if self.workload is not None:
            _require_workload(self.workload)
        if not isinstance(self.window, SpendWindow) or type(self.window_start) is not date:
            raise SpendAdmissionContractError("spend scope needs a validated window and date")
        if self.window is SpendWindow.MONTHLY and self.window_start.day != 1:
            raise SpendAdmissionContractError("monthly spend scope must start on day one")


@dataclass(frozen=True, slots=True)
class SpendBudgetLimit:
    """One required private bucket and ceiling; not proof of deployment policy ownership."""

    scope: SpendBudgetScope = field(repr=False)
    ceiling_micros: int

    def __post_init__(self) -> None:
        """Reject unvalidated scopes or nonpositive/overflowed ceilings."""
        _require_value(self.scope, SpendBudgetScope)
        _require_integer(self.ceiling_micros, minimum=1)


@dataclass(frozen=True, slots=True)
class SpendBudgetSnapshot:
    """Known read projection only; unknown/missing state cannot use zero defaults."""

    limit: SpendBudgetLimit = field(repr=False)
    settled_micros: int
    held_micros: int

    def __post_init__(self) -> None:
        """Permit truthful excess over the ceiling, but reject invalid stored amounts."""
        _require_value(self.limit, SpendBudgetLimit)
        _require_integer(self.settled_micros)
        _require_integer(self.held_micros)
        _require_integer(self.exposure_micros)

    @property
    def exposure_micros(self) -> int:
        """Include unknown exposure in retained allocations, never as observed usage."""
        return self.settled_micros + self.held_micros

    def permits_allocation(self, amount_micros: int) -> bool:
        """Check a read projection without claiming capacity or granting admission."""
        _require_integer(amount_micros)
        return (
            self.exposure_micros < self.limit.ceiling_micros
            and self.exposure_micros + amount_micros <= self.limit.ceiling_micros
        )


@dataclass(frozen=True, slots=True)
class SpendAttemptAllocation:
    """One preallocated attempt in an already-authorized plan, not execution authority."""

    deployment_id: str = field(repr=False)
    fallback_index: int
    attempt_number: int
    bound_micros: int
    pricing_digest: str = field(repr=False)
    bound_evidence_id: str = field(repr=False)

    def __post_init__(self) -> None:
        """Require bounded slot identity and cost-model correlation metadata."""
        _require_id(self.deployment_id)
        _require_id(self.bound_evidence_id)
        _require_digest(self.pricing_digest)
        _require_integer(self.fallback_index)
        _require_integer(self.attempt_number, minimum=1)
        _require_integer(self.bound_micros)


@dataclass(frozen=True, slots=True)
class SpendReservationRequest:
    """Complete immutable admission intent; store must verify trusted policy/plan coverage."""

    execution_id: str = field(repr=False)
    owner_id: str = field(repr=False)
    client_id: str = field(repr=False)
    workload: str = field(repr=False)
    admitted_on: date
    policy_epoch: int
    policy_digest: str = field(repr=False)
    plan_digest: str = field(repr=False)
    registry_digest: str = field(repr=False)
    retry_policy_digest: str = field(repr=False)
    limits: tuple[SpendBudgetLimit, ...] = field(repr=False)
    allocations: tuple[SpendAttemptAllocation, ...] = field(repr=False)

    def __post_init__(self) -> None:
        """Bind all scopes/windows/slots, preserving caller-independent control identity."""
        for value in (self.execution_id, self.owner_id, self.client_id):
            _require_id(value)
        _require_workload(self.workload)
        _require_integer(self.policy_epoch, minimum=1)
        for value in (
            self.policy_digest,
            self.plan_digest,
            self.registry_digest,
            self.retry_policy_digest,
        ):
            _require_digest(value)
        if type(self.admitted_on) is not date:
            raise SpendAdmissionContractError("spend admission needs a frozen date")
        _require_tuple(self.limits, SpendBudgetLimit)
        _require_tuple(self.allocations, SpendAttemptAllocation)
        scopes = tuple(limit.scope for limit in self.limits)
        if len(set(scopes)) != len(scopes):
            raise SpendAdmissionContractError("spend request must not repeat a scope")
        for scope in scopes:
            expected_start = (
                self.admitted_on
                if scope.window is SpendWindow.DAILY
                else self.admitted_on.replace(day=1)
            )
            if (
                scope.client_id != self.client_id
                or scope.workload not in (None, self.workload)
                or scope.window_start != expected_start
            ):
                raise SpendAdmissionContractError("spend scopes must match admission attribution")
        _require_allocation_sequence(self.allocations)
        _require_integer(self.reserved_micros)

    @property
    def reserved_micros(self) -> int:
        """Sum every possible attempt's allocation once per applicable scope."""
        return sum(allocation.bound_micros for allocation in self.allocations)


@dataclass(frozen=True, slots=True)
class SpendReservation:
    """Store-issued owned receipt; construction does not prove issuance or liveness."""

    request: SpendReservationRequest = field(repr=False)
    owner_fence: str = field(repr=False)
    owner_timeout_seconds: float

    def __post_init__(self) -> None:
        """Require exact immutable intent, a bounded fence and finite remaining lifetime."""
        _require_value(self.request, SpendReservationRequest)
        _require_id(self.owner_fence)
        _require_lifetime(self.owner_timeout_seconds)


@dataclass(frozen=True, slots=True)
class SpendDispatchReceipt:
    """Exact slot's dispatch claim, never a reusable permission to reopen inference."""

    reservation: SpendReservation = field(repr=False)
    allocation: SpendAttemptAllocation = field(repr=False)
    dispatch_fence: str = field(repr=False)

    def __post_init__(self) -> None:
        """Prevent a dispatch value from substituting an unreserved slot or bound."""
        _require_value(self.reservation, SpendReservation)
        _require_value(self.allocation, SpendAttemptAllocation)
        _require_id(self.dispatch_fence)
        if self.allocation not in self.reservation.request.allocations:
            raise SpendAdmissionContractError("spend dispatch must name an exact reserved slot")


@dataclass(frozen=True, slots=True)
class SpendSettlement:
    """Exact attempt outcome; None retains unknown exposure, not zero estimated usage."""

    dispatch: SpendDispatchReceipt = field(repr=False)
    estimated_micros: int | None
    usage_evidence_id: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Require paired known cost/finality evidence without proving its trustworthiness."""
        _require_value(self.dispatch, SpendDispatchReceipt)
        _require_cost_evidence(self.estimated_micros, self.usage_evidence_id)


@dataclass(frozen=True, slots=True)
class SpendSettlementReceipt:
    """Acknowledged exact outcome; not a substitute for authoritative journal validation."""

    settlement: SpendSettlement = field(repr=False)
    settlement_fence: str = field(repr=False)

    def __post_init__(self) -> None:
        """Reject uncorrelated outcomes and malformed store fences."""
        _require_value(self.settlement, SpendSettlement)
        _require_id(self.settlement_fence)

    @property
    def bound_exceeded(self) -> bool:
        """Retain truthful excess instead of clamping it to the reserved allocation."""
        amount = self.settlement.estimated_micros
        return amount is not None and amount > self.settlement.dispatch.allocation.bound_micros


class SpendAttemptState(StrEnum):
    """Closed journal vocabulary; UNKNOWN retains the original allocation."""

    RESERVED = "reserved"
    MAY_HAVE_EXECUTED = "may_have_executed"
    SETTLED = "settled"
    UNKNOWN = "unknown"
    CLOSED_UNUSED = "closed_unused"


@dataclass(frozen=True, slots=True)
class SpendAttemptSnapshot:
    """Read-only slot state; no snapshot acquires ownership or dispatch authority."""

    allocation: SpendAttemptAllocation = field(repr=False)
    state: SpendAttemptState
    dispatch_fence: str | None = field(default=None, repr=False)
    estimated_micros: int | None = None
    usage_evidence_id: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Reject contradictory no-dispatch, unknown and settled cost projections."""
        _require_value(self.allocation, SpendAttemptAllocation)
        if not isinstance(self.state, SpendAttemptState):
            raise SpendAdmissionContractError("spend attempt needs a closed state")
        if self.state in (SpendAttemptState.RESERVED, SpendAttemptState.CLOSED_UNUSED):
            if self.dispatch_fence is not None:
                raise SpendAdmissionContractError("unused spend slot cannot prove dispatch")
        else:
            _require_id(self.dispatch_fence)
        if self.state is SpendAttemptState.SETTLED:
            if self.estimated_micros is None:
                raise SpendAdmissionContractError("settled spend slot needs cost evidence")
            _require_cost_evidence(self.estimated_micros, self.usage_evidence_id)
        elif self.estimated_micros is not None or self.usage_evidence_id is not None:
            raise SpendAdmissionContractError("unsettled spend slot cannot prove measured cost")


@dataclass(frozen=True, slots=True)
class SpendJournalSnapshot:
    """Complete read projection; closed journals may retain UNKNOWN exposure."""

    reservation: SpendReservation = field(repr=False)
    attempts: tuple[SpendAttemptSnapshot, ...] = field(repr=False)
    closed: bool
    closure_fence: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Require exact plan coverage and consistent fenced closure, not backend atomicity."""
        _require_value(self.reservation, SpendReservation)
        _require_tuple(self.attempts, SpendAttemptSnapshot)
        if tuple(slot.allocation for slot in self.attempts) != self.reservation.request.allocations:
            raise SpendAdmissionContractError("spend journal must cover the exact reserved plan")
        if type(self.closed) is not bool:
            raise SpendAdmissionContractError("spend journal closure needs an explicit boolean")
        if self.closed:
            _require_id(self.closure_fence)
            if any(
                slot.state in (SpendAttemptState.RESERVED, SpendAttemptState.MAY_HAVE_EXECUTED)
                for slot in self.attempts
            ):
                raise SpendAdmissionContractError(
                    "closed spend journal cannot retain dispatchable slots"
                )
        elif self.closure_fence is not None:
            raise SpendAdmissionContractError("open spend journal cannot prove fenced closure")


def _require_id(value: object) -> None:
    if type(value) is not str or _OPAQUE_ID.fullmatch(value) is None:
        raise SpendAdmissionContractError("spend identity must be a bounded opaque identifier")


def _require_workload(value: str) -> None:
    _require_id(value)
    segments = value.split(".")
    if len(segments) < 2 or any(not segment.replace("-", "").isalnum() for segment in segments):
        raise SpendAdmissionContractError("spend workload must be a dotted policy identifier")


def _require_digest(value: str) -> None:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise SpendAdmissionContractError("spend provenance must use a canonical digest")


def _require_integer(value: int, *, minimum: int = 0) -> None:
    if type(value) is not int or not minimum <= value <= MAX_SPEND_MICROS:
        raise SpendAdmissionContractError("spend amount or index must be a bounded integer")


def _require_value(value: object, expected: type[object]) -> None:
    if type(value) is not expected:
        raise SpendAdmissionContractError("spend metadata needs a validated immutable value")


def _require_tuple(values: object, expected: type[object]) -> None:
    if (
        not isinstance(values, tuple)
        or type(values) is not tuple
        or not values
        or any(type(v) is not expected for v in values)
    ):
        raise SpendAdmissionContractError("spend collection must be a nonempty validated tuple")


def _require_cost_evidence(amount: int | None, evidence: str | None) -> None:
    if amount is None:
        if evidence is not None:
            raise SpendAdmissionContractError("unknown spend cannot prove usage finality")
    else:
        _require_integer(amount)
        _require_id(evidence)


def _require_lifetime(value: float) -> None:
    valid = type(value) in (int, float)
    if valid:
        try:
            valid = isfinite(value) and value > 0
        except OverflowError:
            valid = False
    if not valid:
        raise SpendAdmissionContractError("spend owner lifetime must be finite and positive")


def _require_allocation_sequence(allocations: tuple[SpendAttemptAllocation, ...]) -> None:
    groups: dict[int, list[SpendAttemptAllocation]] = {}
    for allocation in allocations:
        groups.setdefault(allocation.fallback_index, []).append(allocation)
    keys = tuple((a.fallback_index, a.attempt_number) for a in allocations)
    if keys != tuple(sorted(keys)) or sorted(groups) != list(range(len(groups))):
        raise SpendAdmissionContractError("spend slots must follow the bounded candidate order")
    deployments: set[str] = set()
    for group in groups.values():
        first = group[0]
        if [slot.attempt_number for slot in group] != list(range(1, len(group) + 1)):
            raise SpendAdmissionContractError("spend retry slots must be contiguous and unique")
        if first.deployment_id in deployments or any(
            (slot.deployment_id, slot.bound_micros, slot.pricing_digest, slot.bound_evidence_id)
            != (
                first.deployment_id,
                first.bound_micros,
                first.pricing_digest,
                first.bound_evidence_id,
            )
            for slot in group
        ):
            raise SpendAdmissionContractError("spend retry slots must retain their exact candidate")
        deployments.add(first.deployment_id)
