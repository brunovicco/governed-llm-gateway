"""Same-process synthetic conformance, not durable storage, billing or serving proof."""

import ast
import asyncio
import inspect
import traceback
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime
from threading import Barrier
from typing import cast
from uuid import UUID

import pytest
from governed_llm_gateway_core.adapters import spend_admission_memory as memory
from governed_llm_gateway_core.adapters.spend_admission_memory import (
    InMemorySpendAdmissionReader,
    InMemorySpendAdmissionState,
    InMemorySpendAdmissionWorker,
)
from governed_llm_gateway_core.application.spend_admission import (
    SpendControlError,
    SpendControlErrorCode,
    SpendReservationPort,
    SpendReservationReadPort,
)
from governed_llm_gateway_core.domain.spend import SpendWindow
from governed_llm_gateway_core.domain.spend_admission import (
    MAX_SPEND_MICROS,
    SpendAdmissionContractError,
    SpendAttemptAllocation,
    SpendAttemptState,
    SpendBudgetLimit,
    SpendBudgetScope,
    SpendBudgetSnapshot,
    SpendReservation,
    SpendReservationRequest,
    SpendSettlement,
)

_DAY = date(2026, 9, 17)
_DIGEST = "sha256:" + "a" * 64
_OTHER_DIGEST = "sha256:" + "b" * 64
_PRIVATE = "private-backend-marker"


def _run[T](coroutine: Coroutine[object, object, T]) -> T:
    return asyncio.run(coroutine)


def _change[T](value: T, **changes: object) -> T:
    return cast(Callable[..., T], replace)(value, **changes)


def _request(
    index: int = 0,
    *,
    client: str = "client-private",
    workload: str = "rag.answer",
    bound: int = 200_000,
    all_attempts: bool = False,
    day: date = _DAY,
) -> SpendReservationRequest:
    scopes = tuple(
        SpendBudgetScope(
            client,
            window,
            day if window is SpendWindow.DAILY else day.replace(day=1),
            scoped_workload,
        )
        for scoped_workload in (None, workload)
        for window in (SpendWindow.DAILY, SpendWindow.MONTHLY)
    )
    first = SpendAttemptAllocation("deployment-private", 0, 1, bound, _DIGEST, "bound-private")
    allocations = (
        (
            first,
            replace(first, attempt_number=2),
            replace(first, deployment_id="fallback-private", fallback_index=1),
        )
        if all_attempts
        else (first,)
    )
    return SpendReservationRequest(
        f"execution-private-{index}",
        f"owner-private-{index}",
        client,
        workload,
        day,
        7,
        _DIGEST,
        _DIGEST,
        _DIGEST,
        _DIGEST,
        tuple(SpendBudgetLimit(scope, 1_000_000) for scope in scopes),
        allocations,
    )


class Clock:
    def __init__(self) -> None:
        self.now = 100.0
        self.utc = datetime(2026, 9, 17, 23, 59, tzinfo=UTC)

    def __call__(self) -> float:
        return self.now

    def utc_now(self) -> datetime:
        return self.utc


class Backend:
    def __init__(
        self,
        requests: tuple[SpendReservationRequest, ...] | None = None,
        *,
        settled: int = 0,
        held: int = 0,
        budgets: tuple[SpendBudgetSnapshot, ...] | None = None,
        lease: float = 10.0,
    ) -> None:
        self.requests = requests if requests is not None else (_request(), _request(1), _request(2))
        self.clock = Clock()
        self.validated: set[SpendSettlement] = set()
        limits = tuple(dict.fromkeys(limit for r in self.requests for limit in r.limits))
        self.opening = (
            budgets
            if budgets is not None
            else tuple(SpendBudgetSnapshot(limit, settled, held) for limit in limits)
        )
        self.state = InMemorySpendAdmissionState(
            budgets=self.opening,
            approved_requests=self.requests,
            owner_lease_seconds=lease,
            usage_validator=lambda outcome: outcome in self.validated,
            clock=self.clock,
            utc_clock=self.clock.utc_now,
        )
        self.first = InMemorySpendAdmissionWorker(self.state)
        self.second = InMemorySpendAdmissionWorker(self.state)
        self.reader = InMemorySpendAdmissionReader(self.state)
        worker: SpendReservationPort = self.first
        reader: SpendReservationReadPort = self.reader
        self.worker_port, self.read_port = worker, reader

    def reserve(self, index: int = 0) -> SpendReservation:
        receipt = _run(self.first.reserve(self.requests[index]))
        assert receipt is not None
        return receipt

    def exposure(
        self, request: SpendReservationRequest | None = None
    ) -> tuple[tuple[int, int], ...]:
        target = request if request is not None else self.requests[0]
        return tuple(
            (snapshot.settled_micros, snapshot.held_micros)
            for snapshot in (
                _run(self.reader.budget(limit.scope, policy_epoch=target.policy_epoch))
                for limit in target.limits
            )
        )

    def outcome(self, reservation: SpendReservation, amount: int | None) -> SpendSettlement:
        dispatch = _run(self.first.dispatch(reservation, reservation.request.allocations[0]))
        outcome = SpendSettlement(dispatch, amount, "usage-private" if amount is not None else None)
        if amount is not None:
            self.validated.add(outcome)
        return outcome


@pytest.mark.parametrize("settled,held", [(900_000, 0), (0, 900_000), (500_000, 400_000)])
def test_first_twenty_cent_allocation_refuses_at_ninety_cents(settled: int, held: int) -> None:
    backend = Backend(settled=settled, held=held)
    assert _run(backend.first.reserve(backend.requests[0])) is None
    assert backend.exposure() == ((settled, held),) * 4
    assert _run(backend.second.reserve(backend.requests[0])) is None


@pytest.mark.parametrize("scope_index", range(4))
def test_one_exhausted_daily_monthly_global_workload_scope_prevents_all_holds(
    scope_index: int,
) -> None:
    request = _request()
    opening = tuple(
        SpendBudgetSnapshot(limit, 900_000 if i == scope_index else 0, 0)
        for i, limit in enumerate(request.limits)
    )
    backend = Backend((request,), budgets=opening)
    assert _run(backend.first.reserve(request)) is None
    assert backend.state._image.budgets == opening
    assert backend.state._image.fences == frozenset()


def test_async_admissions_allocate_one_remaining_slot_without_read_check_race() -> None:
    backend = Backend(tuple(_request(i) for i in range(16)), settled=800_000)

    async def scenario() -> list[SpendReservation | None]:
        return list(await asyncio.gather(*(backend.first.reserve(r) for r in backend.requests)))

    admitted = [r for r in _run(scenario()) if r is not None]
    assert len(admitted) == 1
    assert backend.exposure() == ((800_000, 200_000),) * 4


def test_independent_local_threads_event_loops_share_one_atomic_capacity_claim() -> None:
    backend = Backend(tuple(_request(i) for i in range(17)), settled=800_000)
    barrier = Barrier(16)

    def admit(index: int) -> SpendReservation | None:
        barrier.wait(timeout=10)
        wrapper = backend.first if index % 2 else backend.second
        return _run(wrapper.reserve(backend.requests[index]))

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(admit, range(16)))
    winners = [r for r in results if r is not None]
    assert len(winners) == 1
    assert backend.exposure() == ((800_000, 200_000),) * 4
    _run(backend.second.close(winners[0]))
    loser_index = results.index(None)
    assert _run(backend.first.reserve(backend.requests[loser_index])) is None
    fresh = _run(backend.first.reserve(backend.requests[16]))
    assert fresh is not None
    assert backend.exposure() == ((800_000, 200_000),) * 4


@pytest.mark.parametrize("settled,held", [(1_000_000, 0), (0, 1_000_000), (800_000, 200_000)])
def test_zero_bound_does_not_bypass_exact_ceiling(settled: int, held: int) -> None:
    backend = Backend((_request(bound=0),), settled=settled, held=held)
    assert _run(backend.first.reserve(backend.requests[0])) is None
    assert backend.exposure() == ((settled, held),) * 4


def test_complete_retry_fallback_plan_is_reserved_once_and_every_attempt_is_accounted() -> None:
    request = _request(all_attempts=True)
    backend = Backend((request,))
    owner = backend.reserve()
    assert request.reserved_micros == 600_000
    assert backend.exposure() == ((0, 600_000),) * 4
    first = backend.outcome(owner, None)
    _run(backend.first.settle(first))
    retry = _run(backend.second.dispatch(owner, request.allocations[1]))
    retry_outcome = SpendSettlement(retry, 120_000, "retry-usage")
    backend.validated.add(retry_outcome)
    _run(backend.first.settle(retry_outcome))
    fallback = _run(backend.first.dispatch(owner, request.allocations[2]))
    fallback_outcome = SpendSettlement(fallback, 80_000, "fallback-usage")
    backend.validated.add(fallback_outcome)
    _run(backend.second.settle(fallback_outcome))
    closed = _run(backend.first.close(owner))
    assert tuple(s.state for s in closed.attempts) == (
        SpendAttemptState.UNKNOWN,
        SpendAttemptState.SETTLED,
        SpendAttemptState.SETTLED,
    )
    assert backend.exposure() == ((200_000, 200_000),) * 4
    assert _run(backend.second.close(owner)) == closed
    assert backend.exposure() == ((200_000, 200_000),) * 4


def test_reads_duplicate_reserve_and_receipt_reconstruction_never_renew_fixed_deadline() -> None:
    backend = Backend()
    owner = backend.reserve()
    image = backend.state._image
    backend.clock.now = 109.0
    assert _run(backend.second.reserve(owner.request)) == owner
    assert _run(backend.second.is_current(owner))
    _run(backend.reader.journal(owner))
    backend.exposure()
    assert backend.state._image is image
    with pytest.raises(SpendControlError):
        _run(backend.first.is_current(replace(owner, owner_timeout_seconds=1000)))
    backend.clock.now = 110.0
    assert not _run(backend.first.is_current(owner))
    assert _run(backend.first.reserve(owner.request)) == owner
    assert backend.exposure() == ((0, 200_000),) * 4


@pytest.mark.parametrize("operation", ["dispatch", "settle", "close"])
def test_expired_owner_cannot_mutate_or_release_exposure(operation: str) -> None:
    backend = Backend()
    owner = backend.reserve()
    outcome = backend.outcome(owner, 100_000) if operation == "settle" else None
    image = backend.state._image
    backend.clock.now = 110.0
    with pytest.raises(SpendControlError) as refused:
        if operation == "dispatch":
            _run(backend.first.dispatch(owner, owner.request.allocations[0]))
        elif operation == "close":
            _run(backend.first.close(owner))
        else:
            assert outcome is not None
            _run(backend.first.settle(outcome))
    assert refused.value.code is SpendControlErrorCode.EXPIRED
    assert backend.state._image is image
    assert backend.exposure() == ((0, 200_000),) * 4
    _run(backend.reader.journal(owner))


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_id", "other-owner"),
        ("client_id", "other-client"),
        ("policy_epoch", 8),
        ("policy_digest", _OTHER_DIGEST),
        ("plan_digest", _OTHER_DIGEST),
        ("registry_digest", _OTHER_DIGEST),
        ("retry_policy_digest", _OTHER_DIGEST),
        ("execution_id", "unknown-execution"),
    ],
)
def test_changed_or_unapproved_intent_never_acquires_capacity(field: str, value: object) -> None:
    backend = Backend()
    request = backend.requests[0]
    if field == "client_id":
        changed = replace(
            request,
            client_id="other-client",
            limits=tuple(
                replace(limit, scope=replace(limit.scope, client_id="other-client"))
                for limit in request.limits
            ),
        )
    else:
        changed = _change(request, **{field: value})
    image = backend.state._image
    with pytest.raises(SpendControlError) as refused:
        _run(backend.first.reserve(changed))
    assert refused.value.code is SpendControlErrorCode.CONFLICT
    assert backend.state._image is image


@pytest.mark.parametrize("change", ["omit_scope", "ceiling", "omit_attempt", "bound", "pricing"])
def test_caller_cannot_drop_limits_or_edit_preapproved_attempt_pricing(change: str) -> None:
    backend = Backend((_request(all_attempts=True),))
    request = backend.requests[0]
    if change == "omit_scope":
        changed = replace(request, limits=request.limits[:-1])
    elif change == "ceiling":
        changed = replace(
            request,
            limits=tuple(replace(limit, ceiling_micros=9_000_000) for limit in request.limits),
        )
    elif change == "omit_attempt":
        changed = replace(request, allocations=request.allocations[:1])
    else:
        field, value = (
            ("bound_micros", 1) if change == "bound" else ("pricing_digest", _OTHER_DIGEST)
        )
        changed = replace(
            request, allocations=tuple(_change(a, **{field: value}) for a in request.allocations)
        )
    image = backend.state._image
    with pytest.raises(SpendControlError):
        _run(backend.first.reserve(changed))
    assert backend.state._image is image


def test_local_dispatch_duplicate_claim_is_idempotent_and_parallel_slot_is_refused() -> None:
    backend = Backend((_request(all_attempts=True),))
    owner = backend.reserve()
    barrier = Barrier(8)

    def claim(_: int) -> object:
        barrier.wait(timeout=10)
        return _run(backend.first.dispatch(owner, owner.request.allocations[0]))

    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(claim, range(8)))
    assert all(c == claims[0] for c in claims)
    assert len(backend.state._image.executions[0].dispatches) == 1
    image = backend.state._image
    with pytest.raises(SpendControlError):
        _run(backend.second.dispatch(owner, owner.request.allocations[1]))
    with pytest.raises(SpendControlError):
        _run(backend.second.dispatch(owner, replace(owner.request.allocations[0], bound_micros=1)))
    assert backend.state._image is image


@pytest.mark.parametrize("amount", [None, 0, 100_000, 300_000])
def test_settlement_duplicates_preserve_exact_cost_unknown_and_truthful_excess(
    amount: int | None,
) -> None:
    backend = Backend()
    owner = backend.reserve()
    outcome = backend.outcome(owner, amount)
    receipt = _run(backend.first.settle(outcome))
    image = backend.state._image
    assert _run(backend.second.settle(outcome)) == receipt
    assert backend.state._image is image
    expected = (0, 200_000) if amount is None else (amount, 0)
    assert backend.exposure() == (expected,) * 4
    assert receipt.bound_exceeded is (amount == 300_000)
    closed = _run(backend.first.close(owner))
    backend.clock.now = 120.0
    assert _run(backend.second.settle(outcome)) == receipt
    assert _run(backend.second.close(owner)) == closed
    assert not _run(backend.first.is_current(owner))
    assert _run(backend.first.dispatch(owner, outcome.dispatch.allocation)) == outcome.dispatch
    assert backend.exposure() == (expected,) * 4


@pytest.mark.parametrize(
    "original,changed", [(None, 0), (0, 1), (100_000, None), (100_000, 120_000)]
)
def test_conflicting_or_late_changed_settlement_is_not_reconciliation(
    original: int | None, changed: int | None
) -> None:
    backend = Backend()
    owner = backend.reserve()
    outcome = backend.outcome(owner, original)
    _run(backend.first.settle(outcome))
    image = backend.state._image
    conflicting = replace(
        outcome,
        estimated_micros=changed,
        usage_evidence_id="new-usage" if changed is not None else None,
    )
    backend.validated.add(conflicting)
    with pytest.raises(SpendControlError) as refused:
        _run(backend.second.settle(conflicting))
    assert refused.value.code is SpendControlErrorCode.CONFLICT
    assert backend.state._image is image


def test_unvalidated_usage_and_fabricated_store_receipts_cannot_settle_or_close() -> None:
    backend = Backend()
    owner = backend.reserve()
    outcome = backend.outcome(owner, 100_000)
    backend.validated.clear()
    image = backend.state._image
    invalid = (
        outcome,
        replace(outcome, dispatch=replace(outcome.dispatch, dispatch_fence="fake-dispatch")),
        replace(
            outcome,
            dispatch=replace(
                outcome.dispatch, reservation=replace(owner, owner_fence="fake-owner")
            ),
        ),
    )
    for candidate in invalid:
        with pytest.raises(SpendControlError):
            _run(backend.first.settle(candidate))
    with pytest.raises(SpendControlError):
        _run(backend.first.close(replace(owner, owner_fence="fake-owner")))
    assert backend.state._image is image


def test_excess_suspends_model_admissions_and_pending_claims_without_clamping_cost() -> None:
    backend = Backend()
    first, second = backend.reserve(0), backend.reserve(1)
    receipt = _run(backend.first.settle(backend.outcome(first, 1_100_000)))
    assert receipt.bound_exceeded
    assert backend.exposure() == ((1_100_000, 200_000),) * 4
    with pytest.raises(SpendControlError):
        _run(backend.second.reserve(backend.requests[2]))
    with pytest.raises(SpendControlError):
        _run(backend.second.dispatch(second, second.request.allocations[0]))
    _run(backend.first.close(second))
    assert backend.exposure() == ((1_100_000, 0),) * 4


@pytest.mark.parametrize("claimed", [False, True])
def test_close_for_unused_cache_abandonment_or_possible_execution_only_releases_unclaimed(
    claimed: bool,
) -> None:
    backend = Backend((_request(all_attempts=True),))
    owner = backend.reserve()
    if claimed:
        _run(backend.first.dispatch(owner, owner.request.allocations[0]))
    closed = _run(backend.second.close(owner))
    assert closed.closed
    assert backend.exposure() == ((0, 200_000 if claimed else 0),) * 4
    assert all(s.state is SpendAttemptState.CLOSED_UNUSED for s in closed.attempts[1:])
    with pytest.raises(SpendControlError):
        _run(backend.first.dispatch(owner, owner.request.allocations[1]))
    if claimed:
        assert closed.attempts[0].state is SpendAttemptState.UNKNOWN
        late = SpendSettlement(backend.state._image.executions[0].dispatches[0], 0, "late-zero")
        backend.validated.add(late)
        with pytest.raises(SpendControlError):
            _run(backend.first.settle(late))
    # This exercises explicit close only, not a real cache or never-started HTTP generator.


@pytest.mark.parametrize("after", [False, True])
@pytest.mark.parametrize("operation", ["reserve", "dispatch", "settle", "close"])
def test_commit_faults_preserve_prestate_or_exact_committed_journal_without_compensation(
    after: bool, operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = Backend((_request(all_attempts=True),))
    owner = backend.reserve() if operation != "reserve" else None
    outcome = (
        backend.outcome(owner, 100_000) if owner is not None and operation == "settle" else None
    )
    if owner is not None and operation == "close":
        backend.outcome(owner, None)
    image = backend.state._image
    commit = backend.state._commit

    def fault(candidate: memory._Image) -> None:
        if after:
            commit(candidate)
        raise OSError(_PRIVATE)

    monkeypatch.setattr(backend.state, "_commit", fault)
    with pytest.raises(SpendControlError) as refused:
        if operation == "reserve":
            _run(backend.first.reserve(backend.requests[0]))
        elif operation == "settle":
            assert outcome is not None
            _run(backend.first.settle(outcome))
        else:
            assert owner is not None
            if operation == "dispatch":
                _run(backend.first.dispatch(owner, owner.request.allocations[0]))
            else:
                _run(backend.first.close(owner))
    assert refused.value.code is SpendControlErrorCode.UNAVAILABLE
    assert _PRIVATE not in "".join(traceback.format_exception(refused.value))
    assert (backend.state._image is image) is (not after)
    monkeypatch.setattr(backend.state, "_commit", commit)
    if operation == "reserve":
        recovered = backend.reserve()
        assert recovered == backend.state._image.executions[0].reservation
        assert backend.exposure() == ((0, 600_000),) * 4
    else:
        assert owner is not None
        journal = _run(backend.reader.journal(owner))
        if operation == "settle":
            assert outcome is not None
            resolved = _run(backend.second.settle(outcome))
            assert resolved.settlement == outcome
            assert backend.exposure() == ((100_000, 400_000),) * 4
        elif operation == "close":
            if after:
                assert journal.closed and journal.attempts[0].state is SpendAttemptState.UNKNOWN
                assert backend.exposure() == ((0, 200_000),) * 4
            else:
                assert not journal.closed and backend.exposure() == ((0, 600_000),) * 4
        else:
            assert journal.attempts[0].state is (
                SpendAttemptState.MAY_HAVE_EXECUTED if after else SpendAttemptState.RESERVED
            )
            resolved_dispatch = _run(backend.second.dispatch(owner, owner.request.allocations[0]))
            assert resolved_dispatch == backend.state._image.executions[0].dispatches[0]
            assert backend.exposure() == ((0, 600_000),) * 4


@pytest.mark.parametrize("after", [False, True])
def test_cancelled_close_propagates_and_does_not_default_possible_usage_to_zero(
    after: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = Backend((_request(all_attempts=True),))
    owner = backend.reserve()
    backend.outcome(owner, None)
    commit = backend.state._commit

    def cancelled(candidate: memory._Image) -> None:
        if after:
            commit(candidate)
        raise asyncio.CancelledError

    monkeypatch.setattr(backend.state, "_commit", cancelled)
    with pytest.raises(asyncio.CancelledError):
        _run(backend.first.close(owner))
    monkeypatch.setattr(backend.state, "_commit", commit)
    assert backend.exposure() == ((0, 200_000 if after else 600_000),) * 4


@pytest.mark.parametrize("fault", ["clock", "utc", "usage", "fence"])
def test_dependency_failures_are_sanitized_without_partial_state(
    fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = Backend()
    owner = backend.reserve() if fault == "usage" else None
    outcome = backend.outcome(owner, 100_000) if owner is not None else None
    image = backend.state._image

    def broken(*_: object) -> object:
        raise OSError(_PRIVATE)

    if fault == "fence":
        monkeypatch.setattr(memory, "uuid4", broken)
    else:
        attribute = {"clock": "_clock", "utc": "_utc_clock", "usage": "_usage_validator"}[fault]
        monkeypatch.setattr(backend.state, attribute, broken)
    with pytest.raises(SpendControlError) as refused:
        if outcome is not None:
            _run(backend.first.settle(outcome))
        else:
            _run(backend.first.reserve(backend.requests[0]))
    assert refused.value.code is SpendControlErrorCode.UNAVAILABLE
    assert _PRIVATE not in "".join(traceback.format_exception(refused.value))
    assert backend.state._image is image


@pytest.mark.parametrize("value", [True, "100", -1.0, float("nan"), float("inf"), 10**400])
def test_invalid_monotonic_clock_never_creates_capacity(
    value: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = Backend()
    image = backend.state._image
    monkeypatch.setattr(backend.state, "_clock", lambda: value)
    with pytest.raises(SpendControlError):
        _run(backend.first.reserve(backend.requests[0]))
    assert backend.state._image is image


def test_clock_regression_and_unrepresentable_deadline_refuse_without_release() -> None:
    backend = Backend()
    owner = backend.reserve()
    backend.clock.now = 99.0
    with pytest.raises(SpendControlError):
        _run(backend.first.close(owner))
    assert backend.exposure() == ((0, 200_000),) * 4
    backend = Backend(lease=1e308)
    backend.clock.now = 1e308
    image = backend.state._image
    with pytest.raises(SpendControlError):
        _run(backend.first.reserve(backend.requests[0]))
    assert backend.state._image is image


@pytest.mark.parametrize("fault", ["duplicate", "invalid"])
def test_invalid_or_reused_fences_cannot_publish_new_transition(
    fault: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = Backend()
    fixed = UUID(int=1)
    monkeypatch.setattr(memory, "uuid4", lambda: fixed)
    owner = backend.reserve()
    image = backend.state._image
    if fault == "invalid":
        monkeypatch.setattr(memory, "uuid4", lambda: "invalid-private-fence")
    with pytest.raises(SpendControlError):
        _run(backend.first.dispatch(owner, owner.request.allocations[0]))
    assert backend.state._image is image


def test_unrepresentable_truthful_settlement_freezes_admission_without_partial_write() -> None:
    request = _request(bound=0)
    request = replace(
        request,
        limits=tuple(replace(limit, ceiling_micros=MAX_SPEND_MICROS) for limit in request.limits),
    )
    backend = Backend((request,), settled=MAX_SPEND_MICROS - 1)
    owner = backend.reserve()
    outcome = backend.outcome(owner, MAX_SPEND_MICROS)
    image = backend.state._image
    with pytest.raises(SpendControlError) as refused:
        _run(backend.first.settle(outcome))
    assert refused.value.code is SpendControlErrorCode.INVALID_STATE
    assert backend.state._image is image
    with pytest.raises(SpendControlError):
        _run(backend.first.reserve(request))
    with pytest.raises(SpendControlError):
        backend.exposure()


def test_rollover_keeps_original_windows_and_rejects_uninitialized_new_day() -> None:
    request = _request(day=date(2026, 9, 30))
    backend = Backend((request,))
    backend.clock.utc = datetime(2026, 9, 30, 23, 59, tzinfo=UTC)
    owner = backend.reserve()
    outcome = backend.outcome(owner, 100_000)
    backend.clock.utc = datetime(2026, 10, 1, tzinfo=UTC)
    _run(backend.first.settle(outcome))
    assert backend.exposure() == ((100_000, 0),) * 4
    assert _run(backend.second.reserve(request)) == owner
    tomorrow = replace(request.limits[0].scope, window_start=date(2026, 10, 1))
    with pytest.raises(SpendControlError):
        _run(backend.reader.budget(tomorrow, policy_epoch=7))
    with pytest.raises(SpendAdmissionContractError):
        Backend((_request(day=date(2026, 10, 1)),), budgets=backend.opening)


@pytest.mark.parametrize(
    "value", [datetime(2026, 9, 17), datetime(2026, 9, 18, tzinfo=UTC), "2026-09-17", None]
)
def test_authoritative_utc_admission_date_is_required(
    value: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = Backend()
    image = backend.state._image
    monkeypatch.setattr(backend.state, "_utc_clock", lambda: value)
    with pytest.raises(SpendControlError):
        _run(backend.first.reserve(backend.requests[0]))
    assert backend.state._image is image


def test_client_workload_and_shared_client_scopes_remain_distinct() -> None:
    requests = (
        _request(),
        _request(1, client="other-client"),
        _request(2, workload="other.workload"),
    )
    backend = Backend(requests)
    backend.reserve(0)
    assert backend.exposure(requests[0]) == ((0, 200_000),) * 4
    assert backend.exposure(requests[1]) == ((0, 0),) * 4
    assert backend.exposure(requests[2]) == ((0, 200_000),) * 2 + ((0, 0),) * 2
    backend.reserve(2)
    assert backend.exposure(requests[0]) == ((0, 400_000),) * 2 + ((0, 200_000),) * 2


@pytest.mark.parametrize(
    "corruption",
    [
        "lost_image",
        "lost_budgets",
        "drift",
        "lost_execution",
        "duplicate_execution",
        "deadline",
        "lost_dispatch",
        "lost_settlement",
        "lost_fences",
        "extra_fence",
        "suspension",
        "revision",
        "owner",
    ],
)
def test_missing_or_corrupt_known_state_denies_without_zero_defaults(corruption: str) -> None:
    backend = Backend()
    owner = backend.reserve()
    outcome = backend.outcome(owner, 100_000)
    _run(backend.first.settle(outcome))
    image = backend.state._image
    execution = image.executions[0]
    if corruption == "lost_image":
        changed = memory._Image(image.revision, backend.opening)
    elif corruption == "lost_budgets":
        changed = replace(image, budgets=())
    elif corruption == "drift":
        changed = replace(
            image, budgets=(replace(image.budgets[0], settled_micros=0), *image.budgets[1:])
        )
    elif corruption in ("lost_execution", "duplicate_execution"):
        changed = replace(
            image, executions=() if corruption == "lost_execution" else (execution, execution)
        )
    elif corruption in ("deadline", "lost_dispatch", "lost_settlement", "owner"):
        if corruption == "deadline":
            assert execution.expires_at is not None
            record = replace(execution, expires_at=execution.expires_at + 1000)
        elif corruption == "owner":
            record = replace(execution, reservation=replace(owner, owner_fence="fake-owner"))
        else:
            field = "dispatches" if corruption == "lost_dispatch" else "settlements"
            record = _change(execution, **{field: ()})
        changed = replace(image, executions=(record,))
    elif corruption == "revision":
        changed = replace(image, revision=image.revision - 1)
    elif corruption == "suspension":
        changed = replace(image, suspended=frozenset({"fake-model"}))
    else:
        changed = replace(
            image,
            fences=frozenset() if corruption == "lost_fences" else image.fences | {"fake-fence"},
        )
    backend.state._image = changed
    for operation in (
        lambda: backend.exposure(),
        lambda: _run(backend.reader.journal(owner)),
        lambda: _run(backend.first.reserve(backend.requests[1])),
        lambda: _run(backend.first.close(owner)),
    ):
        with pytest.raises(SpendControlError) as refused:
            operation()
        assert refused.value.code is SpendControlErrorCode.INVALID_STATE
        assert backend.state._image is changed


def test_close_and_settlement_race_is_one_complete_outcome_in_every_scope() -> None:
    backend = Backend()
    owner = backend.reserve()
    outcome = backend.outcome(owner, 100_000)
    barrier = Barrier(2)

    def settle() -> bool:
        barrier.wait(timeout=10)
        try:
            _run(backend.first.settle(outcome))
            return True
        except SpendControlError as refused:
            assert refused.code is SpendControlErrorCode.CONFLICT
            return False

    def close() -> None:
        barrier.wait(timeout=10)
        _run(backend.second.close(owner))

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = pool.submit(settle)
        closing = pool.submit(close)
        settled = result.result(timeout=10)
        closing.result(timeout=10)
    assert backend.exposure() == (((100_000, 0) if settled else (0, 200_000)),) * 4
    journal = _run(backend.reader.journal(owner))
    assert journal.closed
    assert journal.attempts[0].state is (
        SpendAttemptState.SETTLED if settled else SpendAttemptState.UNKNOWN
    )


@pytest.mark.parametrize(
    "change", ["empty", "list", "duplicate", "missing_scope", "epoch", "lease", "validator"]
)
def test_bootstrap_requires_explicit_complete_fixtures_not_worker_policy_reset(change: str) -> None:
    request = _request()
    budgets = tuple(SpendBudgetSnapshot(limit, 0, 0) for limit in request.limits)
    kwargs: dict[str, object] = {
        "budgets": budgets,
        "approved_requests": (request,),
        "owner_lease_seconds": 10.0,
        "usage_validator": lambda _: False,
    }
    if change == "empty":
        kwargs["budgets"] = ()
    elif change == "list":
        kwargs["approved_requests"] = [request]
    elif change == "duplicate":
        kwargs["approved_requests"] = (request, request)
    elif change == "missing_scope":
        kwargs["budgets"] = budgets[:-1]
    elif change == "epoch":
        kwargs["approved_requests"] = (request, replace(_request(1), policy_epoch=8))
    elif change == "lease":
        kwargs["owner_lease_seconds"] = True
    else:
        kwargs["usage_validator"] = None
    with pytest.raises(SpendAdmissionContractError):
        cast(Callable[..., InMemorySpendAdmissionState], InMemorySpendAdmissionState)(**kwargs)


def test_reader_permissions_and_private_metadata_are_not_public_exports_or_reset_capabilities() -> (
    None
):
    backend = Backend()
    owner = backend.reserve()
    for method in ("reserve", "dispatch", "settle", "close", "is_current"):
        assert not hasattr(backend.reader, method)
    for method in ("publish", "reset", "renew", "recover", "prune"):
        assert not hasattr(backend.first, method)
    for value in (backend.state, backend.state._image, backend.state._image.executions[0], owner):
        assert "private" not in repr(value)
        assert _DIGEST not in repr(value)
    with pytest.raises(SpendControlError):
        _run(backend.reader.budget(owner.request.limits[0].scope, policy_epoch=8))
    with pytest.raises(SpendControlError):
        _run(backend.reader.budget(owner.request.limits[0].scope, policy_epoch=True))
    with pytest.raises(SpendAdmissionContractError):
        InMemorySpendAdmissionReader(cast(InMemorySpendAdmissionState, object()))


def test_fail_closed_runtime_checks_have_no_optimized_assert_dependency() -> None:
    tree = ast.parse(inspect.getsource(memory))
    assert not any(isinstance(node, ast.Assert) for node in ast.walk(tree))
    with pytest.raises(SpendAdmissionContractError):
        memory._check(False)
    backend = Backend()
    backend.state._image = replace(backend.state._image, budgets=())
    with pytest.raises(SpendControlError):
        backend.state._validated_image()


@pytest.mark.parametrize("value", [False, None, 1, "true"])
def test_usage_validator_requires_explicit_true_not_truthy_untrusted_values(
    value: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = Backend()
    owner = backend.reserve()
    outcome = backend.outcome(owner, 100_000)
    image = backend.state._image
    monkeypatch.setattr(backend.state, "_usage_validator", lambda _: value)
    with pytest.raises(SpendControlError) as refused:
        _run(backend.first.settle(outcome))
    assert refused.value.code is SpendControlErrorCode.INVALID_STATE
    assert backend.state._image is image
    assert backend.exposure() == ((0, 200_000),) * 4


def test_unclaimed_or_cross_execution_dispatch_cannot_settle_another_journal() -> None:
    backend = Backend()
    first, second = backend.reserve(0), backend.reserve(1)
    outcome = backend.outcome(first, 100_000)
    fabricated = replace(outcome, dispatch=replace(outcome.dispatch, reservation=second))
    backend.validated.add(fabricated)
    image = backend.state._image
    with pytest.raises(SpendControlError) as refused:
        _run(backend.first.settle(fabricated))
    assert refused.value.code is SpendControlErrorCode.CONFLICT
    assert backend.state._image is image
    assert backend.exposure() == ((0, 400_000),) * 4


def test_new_execution_after_utc_regression_fails_without_mutating_frozen_windows() -> None:
    backend = Backend()
    backend.reserve()
    image = backend.state._image
    backend.clock.utc = datetime(2026, 9, 17, 22, tzinfo=UTC)
    with pytest.raises(SpendControlError) as refused:
        _run(backend.second.reserve(backend.requests[1]))
    assert refused.value.code is SpendControlErrorCode.INVALID_STATE
    assert backend.state._image is image


@pytest.mark.parametrize("operation", ["reserve", "settle", "dispatch"])
def test_untyped_worker_inputs_are_sanitized_control_failures(operation: str) -> None:
    backend = Backend()
    owner = backend.reserve()
    image = backend.state._image
    with pytest.raises(SpendControlError):
        if operation == "reserve":
            _run(backend.first.reserve(cast(SpendReservationRequest, object())))
        elif operation == "settle":
            _run(backend.first.settle(cast(SpendSettlement, object())))
        else:
            _run(backend.first.dispatch(owner, cast(SpendAttemptAllocation, object())))
    assert backend.state._image is image
