"""Private value/port conformance, not atomic reservation or provider-bound evidence."""

import inspect
from collections.abc import Callable
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime
from decimal import Decimal, Inexact, localcontext
from typing import cast, get_type_hints

import pytest
from governed_llm_gateway_core.application.spend_admission import (
    SpendControlError,
    SpendControlErrorCode,
    SpendReservationPort,
    SpendReservationReadPort,
)
from governed_llm_gateway_core.domain.spend import SpendWindow, to_micro_usd
from governed_llm_gateway_core.domain.spend_admission import (
    MAX_SPEND_MICROS,
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
    to_reservation_micros,
)

_TODAY = date(2026, 9, 17)
_DIGEST = "sha256:" + "a" * 64
_OTHER_DIGEST = "sha256:" + "b" * 64


def _invalid[T](value: T, **changes: object) -> T:
    """Exercise intentionally invalid/untyped fixtures without weakening checked APIs."""
    return cast(Callable[..., T], replace)(value, **changes)


def _scope() -> SpendBudgetScope:
    return SpendBudgetScope("client-private-marker", SpendWindow.DAILY, _TODAY)


def _allocation() -> SpendAttemptAllocation:
    return SpendAttemptAllocation(
        "deployment-private-marker", 0, 1, 200_000, _DIGEST, "bound-private"
    )


def _request() -> SpendReservationRequest:
    first = _allocation()
    return SpendReservationRequest(
        execution_id="execution-private-marker",
        owner_id="owner-private-marker",
        client_id=_scope().client_id,
        workload="rag.answer",
        admitted_on=_TODAY,
        policy_epoch=7,
        policy_digest=_DIGEST,
        plan_digest=_DIGEST,
        registry_digest=_DIGEST,
        retry_policy_digest=_DIGEST,
        limits=(
            SpendBudgetLimit(_scope(), 1_000_000),
            SpendBudgetLimit(
                replace(_scope(), window=SpendWindow.MONTHLY, window_start=date(2026, 9, 1)),
                5_000_000,
            ),
            SpendBudgetLimit(replace(_scope(), workload="rag.answer"), 500_000),
        ),
        allocations=(
            first,
            replace(first, attempt_number=2),
            replace(first, deployment_id="fallback-private-marker", fallback_index=1),
        ),
    )


def _reservation() -> SpendReservation:
    return SpendReservation(_request(), "owner-fence-private", 30.0)


def _dispatch() -> SpendDispatchReceipt:
    return SpendDispatchReceipt(_reservation(), _allocation(), "dispatch-fence-private")


def _settlement() -> SpendSettlement:
    return SpendSettlement(_dispatch(), 100_000, "usage-private-marker")


def _journal() -> SpendJournalSnapshot:
    reservation = _reservation()
    return SpendJournalSnapshot(
        reservation,
        tuple(
            SpendAttemptSnapshot(a, SpendAttemptState.RESERVED)
            for a in reservation.request.allocations
        ),
        closed=False,
    )


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("0", 0),
        ("0.0000000000001", 1),
        ("1e-1000000", 1),
        ("0.000001", 1),
        ("0.0000010000000000000000001", 2),
        ("1.234567", 1_234_567),
        ("1.23456700000000000000000001", 1_234_568),
        ("9223372036854.775806000000000000000001", MAX_SPEND_MICROS),
        ("9223372036854.775807", MAX_SPEND_MICROS),
    ],
)
def test_rounding_is_outward_and_independent_of_caller_decimal_context(
    amount: str, expected: int
) -> None:
    value = Decimal(amount)
    with localcontext() as context:
        context.prec = 1
        context.traps[Inexact] = True
        assert to_reservation_micros(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        1,
        0.1,
        "1",
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("-0.1"),
        Decimal("9223372036854.7758071"),
    ],
)
def test_conversion_rejects_untyped_nonfinite_negative_and_overflowed_cost(value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        to_reservation_micros(cast(Decimal, value))


def test_legacy_half_up_conversion_and_guard_are_not_reinterpreted() -> None:
    amount = Decimal("0.0000001")
    assert to_micro_usd(amount) == 0
    assert to_reservation_micros(amount) == 1


@pytest.mark.parametrize("field", ["execution_id", "owner_id", "client_id"])
@pytest.mark.parametrize("value", [None, 7, "", " padded", "a:b", "a/b", "a\n", "á", "x" * 129])
def test_request_identity_is_bounded_and_never_payload_or_backend_text(
    field: str, value: object
) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _invalid(_request(), **{field: value})


@pytest.mark.parametrize(
    "field", ["policy_digest", "plan_digest", "registry_digest", "retry_policy_digest"]
)
@pytest.mark.parametrize("value", [None, "", "a" * 64, "sha256:" + "A" * 64, "sha256:" + "a" * 63])
def test_request_requires_canonical_provenance(field: str, value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _invalid(_request(), **{field: value})


@pytest.mark.parametrize("value", [True, False, 0, -1, "7", 7.0, MAX_SPEND_MICROS + 1])
def test_policy_epoch_is_a_positive_bounded_integer(value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _invalid(_request(), policy_epoch=value)


@pytest.mark.parametrize(
    "value", [None, "rag", "rag..answer", "rag_answer", "rag.answer/other", "rag.answer\n"]
)
def test_request_and_scope_require_a_bounded_dotted_workload(value: object) -> None:
    for fixture in (_scope(), _request()):
        if value is None and isinstance(fixture, SpendBudgetScope):
            assert _invalid(fixture, workload=value).workload is None
            continue
        with pytest.raises(SpendAdmissionContractError):
            _invalid(fixture, workload=value)


def test_scope_window_dates_are_strict_and_canonical() -> None:
    assert replace(_scope(), window=SpendWindow.MONTHLY, window_start=date(2026, 9, 1)) != _scope()
    for changes in (
        {"window": "daily"},
        {"window_start": "2026-09-17"},
        {"window_start": datetime(2026, 9, 17)},
        {"window": SpendWindow.MONTHLY},
    ):
        with pytest.raises(SpendAdmissionContractError):
            _invalid(_scope(), **changes)
    with pytest.raises(SpendAdmissionContractError):
        _invalid(_request(), admitted_on=datetime(2026, 9, 17))


@pytest.mark.parametrize(
    "scope",
    [
        replace(_scope(), client_id="other-client"),
        replace(_scope(), workload="other.workload"),
        replace(_scope(), window_start=date(2026, 9, 18)),
        SpendBudgetScope(_scope().client_id, SpendWindow.MONTHLY, date(2026, 10, 1)),
    ],
)
def test_request_cannot_substitute_client_workload_or_admission_window(
    scope: SpendBudgetScope,
) -> None:
    with pytest.raises(SpendAdmissionContractError):
        replace(_request(), limits=(SpendBudgetLimit(scope, 1_000_000),))


@pytest.mark.parametrize("field", ["limits", "allocations"])
@pytest.mark.parametrize("value", [None, (), [], (object(),)])
def test_collections_are_nonempty_immutable_validated_tuples(field: str, value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _invalid(_request(), **{field: value})


def test_request_retains_complete_scope_set_and_reserves_every_attempt_without_mutation() -> None:
    request = _request()
    assert request.reserved_micros == 600_000
    assert len(request.limits) == 3
    for _ in range(3):
        assert request.reserved_micros == 600_000
    with pytest.raises(SpendAdmissionContractError):
        replace(request, limits=(request.limits[0], request.limits[0]))


@pytest.mark.parametrize("field", ["fallback_index", "attempt_number", "bound_micros"])
@pytest.mark.parametrize("value", [True, False, -1, 1.0, "1", MAX_SPEND_MICROS + 1])
def test_slot_numbers_and_bounds_reject_untyped_negative_or_unrepresentable_values(
    field: str, value: object
) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _invalid(_allocation(), **{field: value})


def test_amounts_and_total_reservation_preserve_zero_and_integer_boundaries() -> None:
    allocation = replace(_allocation(), bound_micros=0)
    assert replace(_request(), allocations=(allocation,)).reserved_micros == 0
    assert (
        replace(
            _request(), allocations=(replace(allocation, bound_micros=MAX_SPEND_MICROS),)
        ).reserved_micros
        == MAX_SPEND_MICROS
    )
    with pytest.raises(SpendAdmissionContractError):
        replace(
            _request(),
            allocations=(
                replace(allocation, bound_micros=MAX_SPEND_MICROS),
                replace(allocation, attempt_number=2, bound_micros=MAX_SPEND_MICROS),
            ),
        )
    for value in (0, True, -1, MAX_SPEND_MICROS + 1):
        with pytest.raises(SpendAdmissionContractError):
            replace(_request().limits[0], ceiling_micros=value)


@pytest.mark.parametrize(
    "allocations",
    [
        (_allocation(), _allocation()),
        (replace(_allocation(), attempt_number=2),),
        (replace(_allocation(), fallback_index=1),),
        (_allocation(), replace(_allocation(), fallback_index=2, deployment_id="other-deployment")),
        tuple(reversed(_request().allocations)),
        (_allocation(), replace(_allocation(), fallback_index=1)),
    ],
)
def test_slots_cannot_duplicate_skip_or_reorder_the_bounded_sequence(
    allocations: tuple[SpendAttemptAllocation, ...],
) -> None:
    with pytest.raises(SpendAdmissionContractError):
        replace(_request(), allocations=allocations)


@pytest.mark.parametrize(
    "changes",
    [
        {"deployment_id": "other-deployment"},
        {"pricing_digest": _OTHER_DIGEST},
        {"bound_evidence_id": "other-bound"},
        {"bound_micros": 300_000},
    ],
)
def test_retry_slots_cannot_change_the_frozen_candidate_or_bound(
    changes: dict[str, object],
) -> None:
    with pytest.raises(SpendAdmissionContractError):
        replace(
            _request(),
            allocations=(
                _allocation(),
                _invalid(replace(_allocation(), attempt_number=2), **changes),
            ),
        )


def test_projection_predicate_includes_held_cost_and_refuses_at_exact_ceiling() -> None:
    limit = SpendBudgetLimit(_scope(), 1_000_000)
    snapshot = SpendBudgetSnapshot(limit, 700_000, 100_000)
    for _ in range(3):
        assert snapshot.permits_allocation(200_000)
        assert not snapshot.permits_allocation(200_001)
        assert snapshot.exposure_micros == 800_000
    assert not SpendBudgetSnapshot(limit, 1_000_000, 0).permits_allocation(0)
    assert not SpendBudgetSnapshot(limit, 1_100_000, 0).permits_allocation(0)
    with pytest.raises(SpendAdmissionContractError):
        snapshot.permits_allocation(-1)
    with pytest.raises(SpendAdmissionContractError):
        SpendBudgetSnapshot(limit, MAX_SPEND_MICROS, 1)


@pytest.mark.parametrize("value", [True, "30", 0.0, -1.0, float("nan"), float("inf"), 10**400])
def test_owned_receipt_requires_finite_positive_lifetime(value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _invalid(_reservation(), owner_timeout_seconds=value)


def test_dispatch_binds_the_exact_reserved_allocation_not_just_a_slot_number() -> None:
    dispatch = _dispatch()
    assert dispatch.reservation.request == _request()
    with pytest.raises(SpendAdmissionContractError):
        replace(dispatch, allocation=replace(_allocation(), bound_micros=1))
    with pytest.raises(SpendAdmissionContractError):
        replace(dispatch, dispatch_fence="")


def test_unknown_is_not_zero_and_truthful_cost_above_bound_is_retained() -> None:
    unknown = SpendSettlement(_dispatch(), None)
    zero = SpendSettlement(_dispatch(), 0, "complete-zero-usage")
    excess = replace(_settlement(), estimated_micros=300_000)
    assert unknown != zero
    assert not SpendSettlementReceipt(unknown, "settlement-fence").bound_exceeded
    assert not SpendSettlementReceipt(zero, "settlement-fence").bound_exceeded
    receipt = SpendSettlementReceipt(excess, "settlement-fence")
    assert receipt.bound_exceeded
    assert receipt.settlement.estimated_micros == 300_000


@pytest.mark.parametrize(
    ("amount", "evidence"),
    [
        (None, "usage"),
        (0, None),
        (-1, "usage"),
        (True, "usage"),
        (MAX_SPEND_MICROS + 1, "usage"),
        (1, ""),
    ],
)
def test_settlement_requires_exact_known_cost_and_finality_pair(
    amount: object, evidence: object
) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _invalid(_settlement(), estimated_micros=amount, usage_evidence_id=evidence)


@pytest.mark.parametrize("state", list(SpendAttemptState))
def test_slot_snapshot_closed_vocabulary_has_consistent_cost_and_dispatch_evidence(
    state: SpendAttemptState,
) -> None:
    dispatched = state not in (SpendAttemptState.RESERVED, SpendAttemptState.CLOSED_UNUSED)
    settled = state is SpendAttemptState.SETTLED
    slot = SpendAttemptSnapshot(
        _allocation(),
        state,
        "dispatch-fence" if dispatched else None,
        100_000 if settled else None,
        "usage" if settled else None,
    )
    if dispatched:
        with pytest.raises(SpendAdmissionContractError):
            replace(slot, dispatch_fence=None)
    else:
        with pytest.raises(SpendAdmissionContractError):
            replace(slot, dispatch_fence="dispatch-fence")
    with pytest.raises(SpendAdmissionContractError):
        replace(slot, estimated_micros=None if settled else 0)
    if not settled:
        with pytest.raises(SpendAdmissionContractError):
            replace(slot, usage_evidence_id="usage")


def test_journal_close_preserves_unknown_slots_and_complete_original_coverage() -> None:
    journal = _journal()
    unknown = SpendAttemptSnapshot(_allocation(), SpendAttemptState.UNKNOWN, "dispatch-fence")
    closed_slots = (
        unknown,
        *(replace(slot, state=SpendAttemptState.CLOSED_UNUSED) for slot in journal.attempts[1:]),
    )
    closed = replace(journal, attempts=closed_slots, closed=True, closure_fence="closure-fence")
    assert closed.closed
    assert closed.attempts[0].state is SpendAttemptState.UNKNOWN
    assert closed.attempts[0].allocation.bound_micros == 200_000
    assert closed.attempts[0].estimated_micros is None
    with pytest.raises(SpendAdmissionContractError):
        replace(journal, attempts=closed_slots[:1])
    with pytest.raises(SpendAdmissionContractError):
        replace(journal, attempts=tuple(reversed(journal.attempts)))
    with pytest.raises(SpendAdmissionContractError):
        replace(journal, closure_fence="closure-fence")
    with pytest.raises(SpendAdmissionContractError):
        replace(journal, closed=True, closure_fence="closure-fence")
    with pytest.raises(SpendAdmissionContractError):
        replace(closed, closure_fence=None)
    with pytest.raises(SpendAdmissionContractError):
        _invalid(journal, closed=1)


def test_identical_control_values_correlate_without_proving_backend_idempotency_or_issuance() -> (
    None
):
    assert _request() == _request()
    assert _dispatch() == _dispatch()
    assert _settlement() == _settlement()
    assert replace(_request(), owner_id="another-owner") != _request()
    assert replace(_request(), policy_epoch=8) != _request()
    assert replace(_dispatch(), dispatch_fence="another-fence") != _dispatch()
    assert replace(_settlement(), usage_evidence_id="another-usage") != _settlement()


def _values() -> tuple[object, ...]:
    return (
        _scope(),
        _request().limits[0],
        SpendBudgetSnapshot(_request().limits[0], 0, 0),
        _allocation(),
        _request(),
        _reservation(),
        _dispatch(),
        _settlement(),
        SpendSettlementReceipt(_settlement(), "settlement-fence-private"),
        _journal().attempts[0],
        _journal(),
    )


@pytest.mark.parametrize("value", _values())
def test_private_values_are_frozen_slotted_and_do_not_expose_control_identity_in_repr(
    value: object,
) -> None:
    assert not hasattr(value, "__dict__")
    for descriptor in fields(cast(type, type(value))):
        with pytest.raises(FrozenInstanceError):
            setattr(value, descriptor.name, getattr(value, descriptor.name))
    rendered = repr(value)
    for marker in (
        "client-private-marker",
        "execution-private-marker",
        "owner-private-marker",
        "deployment-private-marker",
        "fallback-private-marker",
        "bound-private",
        "usage-private-marker",
        "owner-fence-private",
        "dispatch-fence-private",
        "settlement-fence-private",
        _DIGEST,
    ):
        assert marker not in rendered


@pytest.mark.parametrize("code", list(SpendControlErrorCode))
def test_control_errors_have_allowlisted_categories_and_generic_safe_messages(
    code: SpendControlErrorCode,
) -> None:
    error = SpendControlError(code)
    assert error.code is code
    assert error.args == ("spend admission control failed",)
    assert "private-marker" not in repr(error)
    with pytest.raises(SpendAdmissionContractError) as refused:
        SpendControlError(cast(SpendControlErrorCode, "raw-provider-private-marker"))
    assert "raw-provider-private-marker" not in str(refused.value)


def test_read_and_mutation_ports_are_async_and_keep_concrete_implementations_out() -> None:
    reads = {"budget": SpendBudgetSnapshot, "journal": SpendJournalSnapshot}
    writes = {
        "reserve": SpendReservation | None,
        "is_current": bool,
        "dispatch": SpendDispatchReceipt,
        "settle": SpendSettlementReceipt,
        "close": SpendJournalSnapshot,
    }
    for method, result in {**reads, **writes}.items():
        function = getattr(SpendReservationPort, method)
        assert inspect.iscoroutinefunction(function)
        assert get_type_hints(function)["return"] == result
    assert not any(hasattr(SpendReservationReadPort, method) for method in writes)
    assert not hasattr(SpendReservationPort, "publish")
    assert not hasattr(SpendReservationPort, "reset")
    assert not hasattr(SpendReservationPort, "renew")


@pytest.mark.parametrize("value", [None, True, -1, 1.0, "1", MAX_SPEND_MICROS + 1])
@pytest.mark.parametrize("field", ["settled_micros", "held_micros"])
def test_budget_projection_rejects_missing_untyped_or_invalid_amounts(
    field: str, value: object
) -> None:
    snapshot = SpendBudgetSnapshot(_request().limits[0], 0, 0)
    with pytest.raises(SpendAdmissionContractError):
        _invalid(snapshot, **{field: value})


@pytest.mark.parametrize(
    ("fixture", "field"),
    [
        (_request().limits[0], "scope"),
        (SpendBudgetSnapshot(_request().limits[0], 0, 0), "limit"),
        (_reservation(), "request"),
        (_dispatch(), "reservation"),
        (_dispatch(), "allocation"),
        (_settlement(), "dispatch"),
        (SpendSettlementReceipt(_settlement(), "settlement-fence"), "settlement"),
        (_journal().attempts[0], "allocation"),
        (_journal(), "reservation"),
    ],
)
def test_nested_contracts_cannot_be_replaced_by_unvalidated_lookalikes(
    fixture: object, field: str
) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _invalid(fixture, **{field: object()})


def test_unparsed_attempt_state_and_invalid_finality_are_refused_without_echoing_input() -> None:
    slot = _journal().attempts[0]
    for changes in ({"state": "reserved-private-marker"}, {"state": 7}):
        with pytest.raises(SpendAdmissionContractError) as refused:
            _invalid(slot, **changes)
        assert "reserved-private-marker" not in str(refused.value)
    settled = SpendAttemptSnapshot(
        _allocation(), SpendAttemptState.SETTLED, "dispatch-fence", 1, "usage"
    )
    with pytest.raises(SpendAdmissionContractError):
        replace(settled, usage_evidence_id=None)
    with pytest.raises(SpendAdmissionContractError):
        replace(_settlement(), usage_evidence_id="raw-provider-private-marker/invalid")


def test_mutable_subclasses_of_scalar_or_collection_types_are_not_private_contract_values() -> None:
    class CustomText(str):
        pass

    class CustomTuple(tuple[object, ...]):
        pass

    class CustomDecimal(Decimal):
        pass

    with pytest.raises(SpendAdmissionContractError):
        replace(_request(), execution_id=CustomText("execution-private-marker"))
    with pytest.raises(SpendAdmissionContractError):
        _invalid(_request(), allocations=CustomTuple(_request().allocations))
    with pytest.raises(SpendAdmissionContractError):
        to_reservation_micros(CustomDecimal("1"))


@pytest.mark.parametrize(
    "field", ["policy_digest", "plan_digest", "registry_digest", "retry_policy_digest"]
)
def test_request_equality_binds_each_captured_provenance_dimension(field: str) -> None:
    assert _invalid(_request(), **{field: _OTHER_DIGEST}) != _request()


def test_single_attempt_plan_values_do_not_grant_replay() -> None:
    request = replace(_request(), allocations=(_allocation(),))
    assert request.reserved_micros == 200_000
    names = {descriptor.name for descriptor in fields(SpendReservationRequest)}
    assert not names.intersection(
        {"request_id", "tenant_id", "messages", "credentials", "authorization"}
    )
    assert (
        get_type_hints(SpendReservationRequest)["allocations"] == tuple[SpendAttemptAllocation, ...]
    )
