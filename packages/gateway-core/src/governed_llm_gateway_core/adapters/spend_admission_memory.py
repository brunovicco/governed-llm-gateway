"""ADR-0021 same-process reference, never a serving/shared-mode fallback.

Bootstrap snapshots, preapproved intents and usage validation are synthetic trusted inputs,
not authentication, a cost estimator, provider finality, restoration or durable authority.
Callbacks must be synchronous, side-effect-free and non-reentrant. State is explicitly
retained, bounded by the supplied intents, and never reset/pruned/renewed by workers.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from math import isfinite
from threading import Lock
from time import monotonic
from uuid import UUID, uuid4

from governed_llm_gateway_core.application.spend_admission import (
    SpendControlError,
    SpendControlErrorCode,
)
from governed_llm_gateway_core.domain.spend import SpendWindow
from governed_llm_gateway_core.domain.spend_admission import (
    SpendAdmissionContractError,
    SpendAttemptAllocation,
    SpendAttemptSnapshot,
    SpendAttemptState,
    SpendBudgetLimit,
    SpendBudgetScope,
    SpendBudgetSnapshot,
    SpendDispatchReceipt,
    SpendJournalSnapshot,
    SpendReservation,
    SpendReservationRequest,
    SpendSettlement,
    SpendSettlementReceipt,
)


@dataclass(frozen=True, slots=True, repr=False)
class _Execution:
    request: SpendReservationRequest
    reservation: SpendReservation | None = None
    expires_at: float | None = None
    journal: SpendJournalSnapshot | None = None
    dispatches: tuple[SpendDispatchReceipt, ...] = ()
    settlements: tuple[SpendSettlementReceipt, ...] = ()
    admitted_at: float | None = None


@dataclass(frozen=True, slots=True, repr=False)
class _Image:
    revision: int
    budgets: tuple[SpendBudgetSnapshot, ...]
    executions: tuple[_Execution, ...] = ()
    suspended: frozenset[str] = frozenset()
    fences: frozenset[str] = frozenset()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _finite(value: object) -> bool:
    if not isinstance(value, int | float) or type(value) not in (int, float):
        return False
    try:
        return isfinite(value)
    except OverflowError:
        return False


def _check(condition: bool) -> None:
    """Runtime validation remains active under optimized Python; never use assert."""
    if not condition:
        raise SpendAdmissionContractError("spend reference state is inconsistent")


class InMemorySpendAdmissionState:
    """Explicit local fixture authority; recreating this object is NOT recovery.

    The manifest and conservation checks detect modeled partial/lost/corrupt images.
    Loss of the entire process/manifest cannot be detected or restored here. No hot
    policy migration, publication, recovery owner or durable acknowledgement exists.
    """

    def __init__(
        self,
        *,
        budgets: tuple[SpendBudgetSnapshot, ...],
        approved_requests: tuple[SpendReservationRequest, ...],
        owner_lease_seconds: float,
        usage_validator: Callable[[SpendSettlement], bool],
        clock: Callable[[], float] = monotonic,
        utc_clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        """Freeze explicit opening exposure and a finite set of synthetic approved intents."""
        if (
            type(budgets) is not tuple
            or not budgets
            or any(type(b) is not SpendBudgetSnapshot for b in budgets)
            or type(approved_requests) is not tuple
            or not approved_requests
            or any(type(r) is not SpendReservationRequest for r in approved_requests)
            or not _finite(owner_lease_seconds)
            or owner_lease_seconds <= 0
            or not all(callable(c) for c in (clock, utc_clock, usage_validator))
        ):
            raise SpendAdmissionContractError("spend reference needs explicit validated fixtures")
        for budget in budgets:
            replace(budget)
        for request in approved_requests:
            replace(request)
        self._opening = budgets
        self._approved = {r.execution_id: r for r in approved_requests}
        first = approved_requests[0]
        self._epoch, self._digest = first.policy_epoch, first.policy_digest
        if (
            len(self._approved) != len(approved_requests)
            or len({b.limit.scope for b in budgets}) != len(budgets)
            or any(
                (r.policy_epoch, r.policy_digest) != (self._epoch, self._digest)
                or set(r.limits) != set(self._limits_for(r))
                for r in approved_requests
            )
        ):
            raise SpendAdmissionContractError("spend reference needs one complete frozen policy")
        self._lease = float(owner_lease_seconds)
        self._clock, self._utc_clock = clock, utc_clock
        self._usage_validator = usage_validator
        self._last_now: float | None = None
        self._last_utc: datetime | None = None
        self._lock = Lock()
        self._revision = 0
        self._seen: frozenset[str] = frozenset()
        self._failed = False
        self._image = _Image(0, budgets)

    def _limits_for(self, request: SpendReservationRequest) -> tuple[SpendBudgetLimit, ...]:
        return tuple(
            b.limit
            for b in self._opening
            if b.limit.scope.client_id == request.client_id
            and b.limit.scope.workload in (None, request.workload)
            and b.limit.scope.window_start
            == (
                request.admitted_on
                if b.limit.scope.window is SpendWindow.DAILY
                else request.admitted_on.replace(day=1)
            )
        )

    def _now(self) -> float:
        try:
            value = self._clock()
        except Exception:
            raise SpendControlError(SpendControlErrorCode.UNAVAILABLE) from None
        if (
            not _finite(value)
            or value < 0
            or (self._last_now is not None and value < self._last_now)
        ):
            raise SpendControlError(SpendControlErrorCode.INVALID_STATE)
        self._last_now = float(value)
        return self._last_now

    def _check_admission_date(self, request: SpendReservationRequest) -> None:
        try:
            value = self._utc_clock()
        except Exception:
            raise SpendControlError(SpendControlErrorCode.UNAVAILABLE) from None
        if (
            type(value) is not datetime
            or value.tzinfo is not UTC
            or (self._last_utc is not None and value < self._last_utc)
        ):
            raise SpendControlError(SpendControlErrorCode.INVALID_STATE)
        self._last_utc = value
        if value.date() != request.admitted_on:
            raise SpendControlError(SpendControlErrorCode.CONFLICT)

    def _fence(self, image: _Image) -> str:
        try:
            value = uuid4()
        except Exception:
            raise SpendControlError(SpendControlErrorCode.UNAVAILABLE) from None
        if type(value) is not UUID or value.hex in image.fences:
            raise SpendControlError(SpendControlErrorCode.INVALID_STATE)
        return value.hex

    def _validated_image(self) -> _Image:
        """Fail closed on modeled state loss, contradictory journals or accounting drift."""
        try:
            image = self._image
            _check(not self._failed and type(image) is _Image)
            _check(type(image.revision) is int and image.revision == self._revision)
            _check(type(image.budgets) is tuple and type(image.executions) is tuple)
            _check(type(image.fences) is frozenset and type(image.suspended) is frozenset)
            _check({e.request.execution_id for e in image.executions} == self._seen)
            _check(len(image.executions) == len(self._seen))
            expected_s = {b.limit.scope: b.settled_micros for b in self._opening}
            expected_h = {b.limit.scope: b.held_micros for b in self._opening}
            fences: list[str] = []
            suspended: set[str] = set()
            for execution in image.executions:
                _check(type(execution) is _Execution)
                _check(execution.request == self._approved[execution.request.execution_id])
                reservation, journal = execution.reservation, execution.journal
                if reservation is None:
                    _check(
                        journal is None
                        and execution.expires_at is None
                        and execution.admitted_at is None
                    )
                    _check(execution.dispatches == () and execution.settlements == ())
                    continue
                _check(
                    type(reservation) is SpendReservation
                    and reservation.request == execution.request
                )
                replace(reservation)
                _check(_finite(execution.admitted_at) and _finite(execution.expires_at))
                if execution.expires_at is None or execution.admitted_at is None or journal is None:
                    raise SpendAdmissionContractError(
                        "spend reference needs a complete owned record"
                    )
                _check(
                    execution.admitted_at >= 0
                    and execution.expires_at == execution.admitted_at + self._lease
                )
                _check(
                    execution.expires_at > execution.admitted_at
                    and reservation.owner_timeout_seconds == self._lease
                )
                _check(type(journal) is SpendJournalSnapshot and journal.reservation == reservation)
                replace(journal)
                _check(type(execution.dispatches) is tuple and type(execution.settlements) is tuple)
                dispatches = {d.allocation: d for d in execution.dispatches}
                settlements = {s.settlement.dispatch.allocation: s for s in execution.settlements}
                _check(len(dispatches) == len(execution.dispatches))
                _check(len(settlements) == len(execution.settlements))
                _check(
                    sum(s.state is SpendAttemptState.MAY_HAVE_EXECUTED for s in journal.attempts)
                    <= 1
                )
                fences.append(reservation.owner_fence)
                for dispatch in execution.dispatches:
                    _check(
                        type(dispatch) is SpendDispatchReceipt
                        and dispatch.reservation == reservation
                    )
                    replace(dispatch)
                    fences.append(dispatch.dispatch_fence)
                for receipt in execution.settlements:
                    _check(type(receipt) is SpendSettlementReceipt)
                    replace(receipt)
                    _check(
                        dispatches[receipt.settlement.dispatch.allocation]
                        == receipt.settlement.dispatch
                    )
                    fences.append(receipt.settlement_fence)
                    if receipt.bound_exceeded:
                        suspended.add(receipt.settlement.dispatch.allocation.deployment_id)
                for slot in journal.attempts:
                    replace(slot)
                    claimed = dispatches.get(slot.allocation)
                    outcome = settlements.get(slot.allocation)
                    _check((claimed is None) == (slot.dispatch_fence is None))
                    if claimed is not None:
                        _check(claimed.dispatch_fence == slot.dispatch_fence)
                    if outcome is not None:
                        _check(slot.estimated_micros == outcome.settlement.estimated_micros)
                        _check(slot.usage_evidence_id == outcome.settlement.usage_evidence_id)
                        _check(
                            slot.state
                            is (
                                SpendAttemptState.UNKNOWN
                                if outcome.settlement.estimated_micros is None
                                else SpendAttemptState.SETTLED
                            )
                        )
                    else:
                        _check(slot.state is not SpendAttemptState.SETTLED)
                        if slot.state is SpendAttemptState.UNKNOWN:
                            _check(journal.closed)
                    if slot.state is SpendAttemptState.CLOSED_UNUSED:
                        _check(journal.closed)
                    for limit in reservation.request.limits:
                        if slot.state is SpendAttemptState.SETTLED:
                            if slot.estimated_micros is None:
                                raise SpendAdmissionContractError(
                                    "settled reference slot needs a cost"
                                )
                            expected_s[limit.scope] += slot.estimated_micros
                        elif slot.state is not SpendAttemptState.CLOSED_UNUSED:
                            expected_h[limit.scope] += slot.allocation.bound_micros
                if journal.closed:
                    if journal.closure_fence is None:
                        raise SpendAdmissionContractError("closed reference journal needs a fence")
                    fences.append(journal.closure_fence)
            _check(set(fences) == image.fences and len(fences) == len(image.fences))
            _check(suspended == image.suspended)
            _check(len(image.budgets) == len(self._opening))
            for opening, budget in zip(self._opening, image.budgets, strict=True):
                _check(type(budget) is SpendBudgetSnapshot and budget.limit == opening.limit)
                replace(budget)
                _check(budget.settled_micros == expected_s[budget.limit.scope])
                _check(budget.held_micros == expected_h[budget.limit.scope])
            return image
        except Exception:
            raise SpendControlError(SpendControlErrorCode.INVALID_STATE) from None

    def _persist(self, image: _Image) -> None:
        try:
            self._commit(image)
        except Exception:
            raise SpendControlError(SpendControlErrorCode.UNAVAILABLE) from None

    def _commit(self, image: _Image) -> None:
        """Publish one already-built image; no awaits, callbacks or I/O between assignments."""
        seen = frozenset(e.request.execution_id for e in image.executions)
        self._seen, self._revision = seen, image.revision
        self._image = image

    def _update(
        self,
        image: _Image,
        execution: _Execution,
        *,
        held_delta: int = 0,
        settled_delta: int = 0,
        fence: str | None = None,
        suspended_model: str | None = None,
    ) -> None:
        """Build every affected bucket/journal before any publication; never compensate."""
        scopes = {limit.scope for limit in execution.request.limits}
        try:
            budgets = tuple(
                replace(
                    b,
                    held_micros=b.held_micros + held_delta,
                    settled_micros=b.settled_micros + settled_delta,
                )
                if b.limit.scope in scopes
                else b
                for b in image.budgets
            )
        except SpendAdmissionContractError:
            # A truthful outcome that cannot fit requires reconciliation, not new spending.
            self._failed = True
            raise SpendControlError(SpendControlErrorCode.INVALID_STATE) from None
        executions = (
            *(
                e
                for e in image.executions
                if e.request.execution_id != execution.request.execution_id
            ),
            execution,
        )
        candidate = _Image(
            image.revision + 1,
            budgets,
            executions,
            image.suspended | ({suspended_model} if suspended_model else set()),
            image.fences | ({fence} if fence else set()),
        )
        self._persist(candidate)


class InMemorySpendAdmissionReader:
    """Read-only local wrapper; separation is a capability shape, not an ACL."""

    def __init__(self, state: InMemorySpendAdmissionState) -> None:
        """Retain the explicitly supplied local state, never construct a default authority."""
        if type(state) is not InMemorySpendAdmissionState:
            raise SpendAdmissionContractError("spend reference requires explicit retained state")
        self._state = state

    async def budget(self, scope: SpendBudgetScope, *, policy_epoch: int) -> SpendBudgetSnapshot:
        """Read one initialized bucket at the fixed epoch, without claiming capacity."""
        with self._state._lock:
            image = self._state._validated_image()
            if type(scope) is not SpendBudgetScope or type(policy_epoch) is not int:
                raise SpendControlError(SpendControlErrorCode.INVALID_STATE)
            if policy_epoch != self._state._epoch:
                raise SpendControlError(SpendControlErrorCode.CONFLICT)
            for budget in image.budgets:
                if budget.limit.scope == scope:
                    return budget
            raise SpendControlError(SpendControlErrorCode.INVALID_STATE)

    def _execution(self, image: _Image, reservation: SpendReservation) -> _Execution:
        if type(reservation) is not SpendReservation:
            raise SpendControlError(SpendControlErrorCode.INVALID_STATE)
        for execution in image.executions:
            if execution.request.execution_id == reservation.request.execution_id:
                if execution.reservation != reservation:
                    raise SpendControlError(SpendControlErrorCode.CONFLICT)
                return execution
        raise SpendControlError(SpendControlErrorCode.INVALID_STATE)

    async def journal(self, reservation: SpendReservation) -> SpendJournalSnapshot:
        """Resolve an exact issued journal even after expiry, without renewing ownership."""
        with self._state._lock:
            execution = self._execution(self._state._validated_image(), reservation)
            if execution.journal is None:
                raise SpendControlError(SpendControlErrorCode.INVALID_STATE)
            return execution.journal


class InMemorySpendAdmissionWorker(InMemorySpendAdmissionReader):
    """Local serialized transitions; zero provider calls, no lease renewal or recovery."""

    def _live(self, execution: _Execution) -> None:
        now = self._state._now()
        if execution.expires_at is None or now >= execution.expires_at:
            raise SpendControlError(SpendControlErrorCode.EXPIRED)
        if execution.journal is None or execution.journal.closed:
            raise SpendControlError(SpendControlErrorCode.CONFLICT)

    async def reserve(self, request: SpendReservationRequest) -> SpendReservation | None:
        """Reserve the complete preapproved intent everywhere, or retain an immutable denial."""
        with self._state._lock:
            image = self._state._validated_image()
            if type(request) is not SpendReservationRequest:
                raise SpendControlError(SpendControlErrorCode.INVALID_STATE)
            if self._state._approved.get(request.execution_id) != request:
                raise SpendControlError(SpendControlErrorCode.CONFLICT)
            for existing in image.executions:
                if existing.request.execution_id == request.execution_id:
                    return existing.reservation
            now = self._state._now()
            self._state._check_admission_date(request)
            if any(a.deployment_id in image.suspended for a in request.allocations):
                raise SpendControlError(SpendControlErrorCode.INVALID_STATE)
            execution = _Execution(request)
            scopes = {limit.scope for limit in request.limits}
            if not all(
                b.permits_allocation(request.reserved_micros)
                for b in image.budgets
                if b.limit.scope in scopes
            ):
                self._state._update(image, execution)
                return None
            deadline = now + self._state._lease
            if not _finite(deadline) or deadline <= now:
                raise SpendControlError(SpendControlErrorCode.INVALID_STATE)
            fence = self._state._fence(image)
            reservation = SpendReservation(request, fence, self._state._lease)
            journal = SpendJournalSnapshot(
                reservation,
                tuple(
                    SpendAttemptSnapshot(a, SpendAttemptState.RESERVED) for a in request.allocations
                ),
                False,
            )
            self._state._update(
                image,
                _Execution(request, reservation, deadline, journal, admitted_at=now),
                held_delta=request.reserved_micros,
                fence=fence,
            )
            return reservation

    async def is_current(self, reservation: SpendReservation) -> bool:
        """Check the fixed local deadline and open journal without renewal or release."""
        with self._state._lock:
            execution = self._execution(self._state._validated_image(), reservation)
            now = self._state._now()
            return (
                execution.expires_at is not None
                and now < execution.expires_at
                and execution.journal is not None
                and not execution.journal.closed
            )

    async def dispatch(
        self, reservation: SpendReservation, allocation: SpendAttemptAllocation
    ) -> SpendDispatchReceipt:
        """Claim an exact slot once; duplicate resolution cannot authorize provider replay."""
        with self._state._lock:
            image = self._state._validated_image()
            execution = self._execution(image, reservation)
            if (
                type(allocation) is not SpendAttemptAllocation
                or allocation not in reservation.request.allocations
            ):
                raise SpendControlError(SpendControlErrorCode.CONFLICT)
            for dispatch in execution.dispatches:
                if dispatch.allocation == allocation:
                    return (
                        dispatch  # Resolve a claim; never permission for a second provider opening.
                    )
            self._live(execution)
            journal = execution.journal
            if journal is None or allocation.deployment_id in image.suspended:
                raise SpendControlError(SpendControlErrorCode.INVALID_STATE)
            if any(s.state is SpendAttemptState.MAY_HAVE_EXECUTED for s in journal.attempts):
                raise SpendControlError(SpendControlErrorCode.CONFLICT)
            fence = self._state._fence(image)
            dispatch = SpendDispatchReceipt(reservation, allocation, fence)
            slots = tuple(
                replace(s, state=SpendAttemptState.MAY_HAVE_EXECUTED, dispatch_fence=fence)
                if s.allocation == allocation
                else s
                for s in journal.attempts
            )
            self._state._update(
                image,
                replace(
                    execution,
                    journal=replace(journal, attempts=slots),
                    dispatches=(*execution.dispatches, dispatch),
                ),
                fence=fence,
            )
            return dispatch

    async def settle(self, settlement: SpendSettlement) -> SpendSettlementReceipt:
        """Apply exact synthetic validated usage or retain the full unknown allocation."""
        with self._state._lock:
            image = self._state._validated_image()
            if type(settlement) is not SpendSettlement:
                raise SpendControlError(SpendControlErrorCode.INVALID_STATE)
            execution = self._execution(image, settlement.dispatch.reservation)
            if settlement.dispatch not in execution.dispatches:
                raise SpendControlError(SpendControlErrorCode.CONFLICT)
            for existing in execution.settlements:
                if existing.settlement.dispatch == settlement.dispatch:
                    if existing.settlement != settlement:
                        raise SpendControlError(SpendControlErrorCode.CONFLICT)
                    return existing  # Read resolution is safe even after close/lease expiry.
            self._live(execution)
            if settlement.estimated_micros is not None:
                try:
                    valid = self._state._usage_validator(settlement)
                except Exception:
                    raise SpendControlError(SpendControlErrorCode.UNAVAILABLE) from None
                if valid is not True:
                    raise SpendControlError(SpendControlErrorCode.INVALID_STATE)
            journal = execution.journal
            if journal is None:
                raise SpendControlError(SpendControlErrorCode.INVALID_STATE)
            fence = self._state._fence(image)
            receipt = SpendSettlementReceipt(settlement, fence)
            known = settlement.estimated_micros is not None
            slots = tuple(
                replace(
                    s,
                    state=SpendAttemptState.SETTLED if known else SpendAttemptState.UNKNOWN,
                    estimated_micros=settlement.estimated_micros,
                    usage_evidence_id=settlement.usage_evidence_id,
                )
                if s.allocation == settlement.dispatch.allocation
                else s
                for s in journal.attempts
            )
            self._state._update(
                image,
                replace(
                    execution,
                    journal=replace(journal, attempts=slots),
                    settlements=(*execution.settlements, receipt),
                ),
                held_delta=-settlement.dispatch.allocation.bound_micros if known else 0,
                settled_delta=settlement.estimated_micros
                if known and settlement.estimated_micros is not None
                else 0,
                fence=fence,
                suspended_model=settlement.dispatch.allocation.deployment_id
                if receipt.bound_exceeded
                else None,
            )
            return receipt

    async def close(self, reservation: SpendReservation) -> SpendJournalSnapshot:
        """Release only unclaimed slots; expiry/failed cleanup require separate recovery."""
        with self._state._lock:
            image = self._state._validated_image()
            execution = self._execution(image, reservation)
            journal = execution.journal
            if journal is None:
                raise SpendControlError(SpendControlErrorCode.INVALID_STATE)
            if journal.closed:
                return journal
            self._live(execution)
            unused = sum(
                s.allocation.bound_micros
                for s in journal.attempts
                if s.state is SpendAttemptState.RESERVED
            )
            slots = tuple(
                replace(s, state=SpendAttemptState.CLOSED_UNUSED)
                if s.state is SpendAttemptState.RESERVED
                else replace(s, state=SpendAttemptState.UNKNOWN)
                if s.state is SpendAttemptState.MAY_HAVE_EXECUTED
                else s
                for s in journal.attempts
            )
            fence = self._state._fence(image)
            closed = replace(journal, attempts=slots, closed=True, closure_fence=fence)
            self._state._update(
                image, replace(execution, journal=closed), held_delta=-unused, fence=fence
            )
            return closed
