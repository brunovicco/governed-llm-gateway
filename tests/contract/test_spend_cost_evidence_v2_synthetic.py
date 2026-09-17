"""Finite v2 fixture lookup conformance, not trusted issuance, accounting or serving."""

import asyncio
import inspect
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import cast, get_type_hints

import pytest
from governed_llm_gateway_contracts import Message, MessageRole, TextBlock
from governed_llm_gateway_core.adapters.spend_cost_evidence_v2_synthetic import (
    SyntheticSpendCacheBounds,
    SyntheticSpendCacheControlSnapshot,
    SyntheticSpendCacheFinality,
    SyntheticSpendCachePreparation,
    SyntheticSpendCacheUsageReport,
)
from governed_llm_gateway_core.application.provider import ProviderRequest, ProviderUsage
from governed_llm_gateway_core.application.spend_cost_evidence import (
    SpendCostEvidenceError,
    SpendCostEvidenceErrorCode,
)
from governed_llm_gateway_core.application.spend_cost_evidence_v2 import (
    SpendCacheCostBoundPort,
    SpendCacheUsageFinalityPort,
)
from governed_llm_gateway_core.domain.spend import SpendWindow
from governed_llm_gateway_core.domain.spend_admission import (
    SpendAdmissionContractError,
    SpendBudgetLimit,
    SpendBudgetScope,
    SpendDispatchReceipt,
    SpendReservation,
    SpendReservationRequest,
)
from governed_llm_gateway_core.domain.spend_cost_evidence_v2 import (
    SpendCacheCostBound,
    SpendCacheCostModel,
    SpendCacheCostShape,
    SpendCachePreparedBinding,
    SpendCacheRates,
    SpendCacheUsageFinality,
    SpendCacheUsageFinalityRequest,
)

_DIGEST = "sha256:" + "a" * 64
_OTHER = "sha256:" + "b" * 64
_PRIVATE = "private-payload-marker"
_START = datetime(2026, 9, 17, tzinfo=UTC)
_END = _START + timedelta(hours=1)


def _change[T](value: T, **changes: object) -> T:
    return cast(Callable[..., T], replace)(value, **changes)


def _cost(index: int = 0) -> SpendCacheCostBound:
    binding = SpendCachePreparedBinding(
        f"preparation-private-{index}",
        f"deployment-private-{index}",
        "synthetic-text-v2",
        "fixture-model",
        "fixture-profile",
        _DIGEST,
        7,
        _DIGEST,
        _DIGEST,
        _DIGEST,
        _DIGEST,
        10,
        SpendCacheCostShape.TEXT_CACHE_PARTITIONED,
    )
    model = SpendCacheCostModel(
        binding.api_family,
        binding.model_id,
        binding.pricing_profile_id,
        _DIGEST,
        _DIGEST,
        10,
        SpendCacheRates(Decimal("0.3"), Decimal("0.1"), Decimal("0.5"), Decimal("0.7")),
        SpendCacheRates(Decimal("0.6"), Decimal("0.2"), Decimal("1.1"), Decimal("0.9")),
        _DIGEST,
        3,
        _START,
        _END,
    )
    return SpendCacheCostBound(
        binding,
        model,
        10,
        _DIGEST,
        _DIGEST,
        f"bound-private-{index}",
        _START,
        _END,
    )


def _preparation(cost: SpendCacheCostBound | None = None) -> SyntheticSpendCachePreparation:
    value = cost if cost is not None else _cost()
    request = ProviderRequest(
        value.binding.model_id,
        (Message(MessageRole.USER, _PRIVATE),),
        max_output_tokens=value.binding.max_output_tokens,
    )
    return SyntheticSpendCachePreparation(request, value)


def _control(cost: SpendCacheCostBound | None = None) -> SyntheticSpendCacheControlSnapshot:
    value = cost if cost is not None else _cost()
    return SyntheticSpendCacheControlSnapshot(_START + timedelta(minutes=30), (value.model,))


def _bounds(cost: SpendCacheCostBound | None = None) -> SyntheticSpendCacheBounds:
    value = cost if cost is not None else _cost()
    return SyntheticSpendCacheBounds((_preparation(value),), _control(value))


def _dispatch(cost: SpendCacheCostBound | None = None, attempt: int = 1) -> SpendDispatchReceipt:
    value = cost if cost is not None else _cost()
    binding = value.binding
    allocations = tuple(value.allocation(fallback_index=0, attempt_number=n) for n in (1, 2))
    intent = SpendReservationRequest(
        f"execution-{binding.prepared_request_id}",
        "owner-private",
        "client-private",
        "rag.answer",
        date(2026, 9, 17),
        binding.policy_epoch,
        binding.policy_digest,
        binding.plan_digest,
        binding.registry_digest,
        binding.retry_policy_digest,
        (
            SpendBudgetLimit(
                SpendBudgetScope("client-private", SpendWindow.DAILY, date(2026, 9, 17)), 1000
            ),
        ),
        allocations,
    )
    return SpendDispatchReceipt(
        SpendReservation(intent, "owner-fence-private", 30),
        allocations[attempt - 1],
        f"dispatch-{binding.prepared_request_id}-{attempt}",
    )


def _report(
    counts: tuple[int, int, int, int, int, int] | None = (10, 2, 3, 5, 4, 15),
    *,
    cost: SpendCacheCostBound | None = None,
    attempt: int = 1,
) -> SyntheticSpendCacheUsageReport:
    value = cost if cost is not None else _cost()
    request = SpendCacheUsageFinalityRequest(
        value,
        _dispatch(value, attempt),
        f"report-{value.binding.prepared_request_id}-{attempt}",
    )
    finality = (
        SpendCacheUsageFinality(
            request,
            *counts,
            f"usage-{value.binding.prepared_request_id}-{attempt}",
        )
        if counts is not None
        else None
    )
    return SyntheticSpendCacheUsageReport(request, finality)


def _finality(report: SyntheticSpendCacheUsageReport | None = None) -> SyntheticSpendCacheFinality:
    value = report if report is not None else _report()
    return SyntheticSpendCacheFinality(
        (value.request.bound,),
        (value.request.dispatch,),
        (value,),
    )


def _failure(code: SpendCostEvidenceErrorCode, call: Callable[[], object]) -> None:
    with pytest.raises(SpendCostEvidenceError) as caught:
        call()
    assert caught.value.code is code
    assert str(caught.value) == "spend cost evidence failed"
    assert _PRIVATE not in "".join(traceback.format_exception(caught.value))
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("role", [MessageRole.SYSTEM, MessageRole.USER, MessageRole.ASSISTANT])
@pytest.mark.parametrize("blocks", [False, True])
def test_exact_canonical_text_is_retained_without_counting(role: MessageRole, blocks: bool) -> None:
    cost = _cost()
    message = (
        Message(role, "", blocks=(TextBlock(_PRIVATE), TextBlock("second")))
        if blocks
        else Message(role, _PRIVATE)
    )
    request = ProviderRequest(cost.binding.model_id, (message,), max_output_tokens=10)
    preparation = SyntheticSpendCachePreparation(request, cost)
    port: SpendCacheCostBoundPort = SyntheticSpendCacheBounds((preparation,), _control(cost))
    assert preparation.request is request
    assert port.bound(replace(cost.binding)) is cost
    assert port.bound(cost.binding).input_token_bound == 10  # Explicit fixture, not tokenization.
    assert cost.valid_until == _END


@pytest.mark.parametrize(
    "field,value",
    [
        ("model", "foreign-model"),
        ("model", None),
        ("max_output_tokens", True),
        ("max_output_tokens", 11),
        ("timeout_seconds", True),
        ("timeout_seconds", None),
        ("timeout_seconds", float("nan")),
        ("timeout_seconds", float("inf")),
        ("timeout_seconds", -1),
        ("timeout_seconds", 10**400),
        ("messages", []),
        ("messages", ()),
        ("messages", (object(),)),
        ("tools", []),
        ("tools", (object(),)),
        ("structured_output", object()),
        ("parallel_tool_calling", True),
        ("parallel_tool_calling", 0),
    ],
)
def test_foreign_mutable_or_unsupported_preparations_are_rejected(
    field: str, value: object
) -> None:
    preparation = _preparation()
    object.__setattr__(preparation.request, field, value)
    with pytest.raises(SpendAdmissionContractError):
        replace(preparation)


@pytest.mark.parametrize(
    "field,value",
    [
        ("role", "user"),
        ("role", MessageRole.TOOL),
        ("content", None),
        ("content", ""),
        ("images", []),
        ("images", (object(),)),
        ("blocks", []),
        ("blocks", (object(),)),
    ],
)
def test_exact_text_message_subset_is_required(field: str, value: object) -> None:
    preparation = _preparation()
    object.__setattr__(preparation.request.messages[0], field, value)
    with pytest.raises(SpendAdmissionContractError):
        replace(preparation)


def test_blocks_cannot_hide_other_content_or_nontext_values() -> None:
    preparation = _preparation()
    message = preparation.request.messages[0]
    object.__setattr__(message, "blocks", (TextBlock("text"),))
    with pytest.raises(SpendAdmissionContractError):
        replace(preparation)
    object.__setattr__(message, "content", "")
    object.__setattr__(message, "blocks", (object(),))
    with pytest.raises(SpendAdmissionContractError):
        replace(preparation)
    object.__setattr__(message, "blocks", (TextBlock("text"),))
    object.__setattr__(message.blocks[0], "text", False)
    with pytest.raises(SpendAdmissionContractError):
        replace(preparation)


@pytest.mark.parametrize("now", [None, True, _START.replace(tzinfo=None)])
def test_control_time_must_be_explicit_canonical_utc(now: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_control(), observed_at=now)


@pytest.mark.parametrize("models", [None, [], (object(),)])
def test_control_models_must_be_an_immutable_exact_inventory(models: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_control(), models=models)


@pytest.mark.parametrize(
    "family",
    [
        "openai_responses",
        "anthropic_messages",
        "gemini",
        "openai_compatible",
        "groq",
        "synthetic_text_v1",
    ],
)
def test_real_families_and_v1_cannot_be_enabled_by_a_label(family: str) -> None:
    cost = _cost()
    foreign = replace(
        cost,
        binding=replace(cost.binding, api_family=family),
        model=replace(cost.model, api_family=family),
    )
    with pytest.raises(SpendAdmissionContractError):
        _preparation(foreign)
    with pytest.raises(SpendAdmissionContractError):
        _control(foreign)
    with pytest.raises(SpendAdmissionContractError):
        _report(cost=foreign)
    _failure(SpendCostEvidenceErrorCode.UNSUPPORTED, lambda: _bounds().bound(foreign.binding))
    request = SpendCacheUsageFinalityRequest(foreign, _dispatch(foreign), "foreign-report")
    _failure(SpendCostEvidenceErrorCode.UNSUPPORTED, lambda: _finality().finalize(request))


@pytest.mark.parametrize(
    "now,available",
    [
        (_START - timedelta(microseconds=1), False),
        (_START, True),
        (_END - timedelta(microseconds=1), True),
        (_END, False),
        (_END + timedelta(days=1), False),
    ],
)
def test_fixed_bound_window_is_start_inclusive_end_exclusive(
    now: datetime, available: bool
) -> None:
    reader = _bounds()
    reader = replace(reader, control=replace(reader.control, observed_at=now))
    cost = reader.preparations[0].bound
    if available:
        assert reader.bound(cost.binding) is cost
    else:
        _failure(SpendCostEvidenceErrorCode.UNAVAILABLE, lambda: reader.bound(cost.binding))
    assert cost.valid_until == _END  # Reads never renew it.


@pytest.mark.parametrize(
    "name,value",
    [
        ("pricing_digest", _OTHER),
        ("configuration_digest", _OTHER),
        ("qualification_digest", _OTHER),
        ("qualification_epoch", 4),
        ("input_threshold", 11),
        ("short_context", SpendCacheRates(Decimal(0), Decimal(0), Decimal(0), Decimal(0))),
        ("valid_until", _END + timedelta(hours=1)),
    ],
)
def test_changed_current_fixture_schedule_denies_new_bounds(name: str, value: object) -> None:
    reader = _bounds()
    current = _change(reader.control.models[0], **{name: value})
    reader = replace(reader, control=replace(reader.control, models=(current,)))
    _failure(SpendCostEvidenceErrorCode.CONFLICT, lambda: reader.bound(_cost().binding))


def test_removed_or_foreign_fixture_model_is_unavailable_not_zero() -> None:
    reader = _bounds()
    for models in [(), (replace(reader.control.models[0], model_id="foreign-model"),)]:
        absent = replace(reader, control=replace(reader.control, models=models))
        _failure(SpendCostEvidenceErrorCode.UNAVAILABLE, partial(absent.bound, _cost().binding))


@pytest.mark.parametrize(
    "name,value",
    [
        ("deployment_id", "foreign"),
        ("model_id", "foreign"),
        ("pricing_profile_id", "foreign"),
        ("configuration_digest", _OTHER),
        ("policy_epoch", 8),
        ("policy_digest", _OTHER),
        ("plan_digest", _OTHER),
        ("registry_digest", _OTHER),
        ("retry_policy_digest", _OTHER),
        ("max_output_tokens", 11),
    ],
)
def test_changed_registered_binding_is_a_conflict(name: str, value: object) -> None:
    binding = _change(_cost().binding, **{name: value})
    _failure(SpendCostEvidenceErrorCode.CONFLICT, lambda: _bounds().bound(binding))


def test_absent_preparation_and_foreign_binding_types_do_not_register_themselves() -> None:
    _failure(SpendCostEvidenceErrorCode.UNAVAILABLE, lambda: _bounds().bound(_cost(1).binding))
    for value in [None, {}, _PRIVATE, object()]:
        _failure(
            SpendCostEvidenceErrorCode.INVALID_STATE,
            partial(_bounds().bound, cast(SpendCachePreparedBinding, value)),
        )


@pytest.mark.parametrize("case", ["preparation", "changed-text", "bound-id", "model", "control"])
def test_duplicate_or_conflicting_bound_inventories_refuse_at_bootstrap(case: str) -> None:
    first, second = _preparation(), _preparation(_cost(1))
    control = _control()
    if case == "preparation":
        second = first
    elif case == "changed-text":
        second = replace(
            first, request=replace(first.request, messages=(Message(MessageRole.USER, "changed"),))
        )
    elif case == "bound-id":
        second = replace(
            second, bound=replace(second.bound, bound_evidence_id=first.bound.bound_evidence_id)
        )
    elif case == "model":
        changed = replace(second.bound.model, qualification_epoch=4)
        second = replace(second, bound=replace(second.bound, model=changed))
    else:
        with pytest.raises(SpendAdmissionContractError):
            replace(control, models=(control.models[0], control.models[0]))
        return
    with pytest.raises(SpendAdmissionContractError):
        SyntheticSpendCacheBounds((first, second), control)


@pytest.mark.parametrize("counts", [(10, 2, 3, 5, 4, 15), (0, 0, 0, 0, 0, 0), None])
def test_registered_complete_zero_and_inspected_incomplete_sources_are_distinct(
    counts: tuple[int, int, int, int, int, int] | None,
) -> None:
    report = _report(counts)
    reader: SpendCacheUsageFinalityPort = _finality(report)
    assert reader.finalize(replace(report.request)) is report.finality
    if counts is None:
        assert reader.finalize(report.request) is None
    else:
        assert report.finality is not None
        assert report.finality.total_tokens == counts[5]
        assert report.finality.settlement().finality is report.finality
    missing = replace(_finality(report), reports=())
    _failure(SpendCostEvidenceErrorCode.UNAVAILABLE, lambda: missing.finalize(report.request))


def test_normalized_usage_cannot_be_registered_as_a_complete_source() -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_report(), finality=ProviderUsage())
    with pytest.raises(SpendAdmissionContractError):
        _change(_report(), request=object())


@pytest.mark.parametrize("case", ["report", "dispatch", "bound"])
def test_missing_report_dispatch_or_bound_is_unavailable(case: str) -> None:
    reader, report = _finality(), _report()
    if case == "report":
        request = replace(report.request, usage_report_id="missing-report")
    elif case == "dispatch":
        request = replace(
            report.request,
            dispatch=replace(report.request.dispatch, dispatch_fence="missing-dispatch"),
        )
    else:
        request = _report(cost=_cost(1)).request
    _failure(SpendCostEvidenceErrorCode.UNAVAILABLE, lambda: reader.finalize(request))


@pytest.mark.parametrize(
    "case", ["bound", "owner", "owner-fence", "lease", "slot", "client", "window"]
)
def test_changed_registered_dispatch_or_bound_is_a_conflict(case: str) -> None:
    report = _report()
    request, dispatch = report.request, report.request.dispatch
    reservation = dispatch.reservation
    if case == "bound":
        changed = replace(request.bound, estimator_digest=_OTHER)
        request = replace(request, bound=changed)
    elif case == "owner-fence":
        request = replace(
            request,
            dispatch=replace(dispatch, reservation=replace(reservation, owner_fence="foreign")),
        )
    elif case == "lease":
        request = replace(
            request,
            dispatch=replace(dispatch, reservation=replace(reservation, owner_timeout_seconds=31)),
        )
    elif case == "slot":
        request = replace(
            request, dispatch=replace(_dispatch(attempt=2), dispatch_fence=dispatch.dispatch_fence)
        )
    else:
        changes: dict[str, object] = (
            {"owner_id": "foreign"}
            if case == "owner"
            else {"client_id": "foreign"}
            if case == "client"
            else {"admitted_on": date(2026, 9, 18)}
        )
        if case in {"client", "window"}:
            limit = reservation.request.limits[0]
            scope = (
                replace(limit.scope, client_id="foreign")
                if case == "client"
                else replace(limit.scope, window_start=date(2026, 9, 18))
            )
            changes["limits"] = (replace(limit, scope=scope),)
        intent = _change(reservation.request, **changes)
        request = replace(
            request, dispatch=replace(dispatch, reservation=replace(reservation, request=intent))
        )
    _failure(SpendCostEvidenceErrorCode.CONFLICT, lambda: _finality(report).finalize(request))


def test_report_handle_cannot_cross_registered_attempts() -> None:
    first, second = _report(), _report(attempt=2)
    reader = SyntheticSpendCacheFinality(
        (first.request.bound,),
        (first.request.dispatch, second.request.dispatch),
        (first, second),
    )
    request = replace(second.request, usage_report_id=first.request.usage_report_id)
    _failure(SpendCostEvidenceErrorCode.CONFLICT, lambda: reader.finalize(request))
    assert reader.finalize(first.request) is first.finality
    assert reader.finalize(second.request) is second.finality


@pytest.mark.parametrize(
    "case",
    [
        "duplicate-bound",
        "duplicate-dispatch",
        "duplicate-slot",
        "owner-conflict",
        "foreign-bound",
        "foreign-dispatch",
        "duplicate-report",
        "duplicate-source",
        "duplicate-usage",
        "changed-report",
    ],
)
def test_ambiguous_or_unregistered_finality_inventory_refuses_at_bootstrap(case: str) -> None:
    first, second = _report(), _report(attempt=2)
    bounds: tuple[SpendCacheCostBound, ...] = (first.request.bound,)
    dispatches: tuple[SpendDispatchReceipt, ...] = (first.request.dispatch, second.request.dispatch)
    reports: tuple[SyntheticSpendCacheUsageReport, ...] = (first, second)
    if case == "duplicate-bound":
        bounds = (bounds[0], bounds[0])
    elif case == "duplicate-dispatch":
        dispatches = (dispatches[0], dispatches[0])
        reports = ()
    elif case == "duplicate-slot":
        dispatches = (dispatches[0], replace(dispatches[0], dispatch_fence="other-fence"))
        reports = ()
    elif case == "owner-conflict":
        dispatch = dispatches[1]
        dispatches = (
            dispatches[0],
            replace(dispatch, reservation=replace(dispatch.reservation, owner_fence="foreign")),
        )
        reports = ()
    elif case == "foreign-bound":
        bounds = (_cost(1),)
    elif case == "foreign-dispatch":
        dispatches = (dispatches[0],)
    elif case == "duplicate-report":
        second = replace(
            second,
            request=replace(second.request, usage_report_id=first.request.usage_report_id),
            finality=None,
        )
        reports = (first, second)
    elif case == "duplicate-source":
        reports = (
            first,
            replace(
                first, request=replace(first.request, usage_report_id="other-report"), finality=None
            ),
        )
    elif case == "duplicate-usage":
        assert first.finality is not None and second.finality is not None
        second = replace(
            second,
            finality=replace(second.finality, usage_evidence_id=first.finality.usage_evidence_id),
        )
        reports = (first, second)
    else:
        with pytest.raises(SpendAdmissionContractError):
            replace(first, request=second.request)
        return
    with pytest.raises(SpendAdmissionContractError):
        SyntheticSpendCacheFinality(bounds, dispatches, reports)


def test_truthful_excess_and_zero_price_token_flags_survive_lookup_without_control_writes() -> None:
    for free in (False, True):
        cost = _cost()
        if free:
            rates = SpendCacheRates(Decimal(0), Decimal(0), Decimal(0), Decimal(0))
            cost = replace(cost, model=replace(cost.model, short_context=rates, long_context=rates))
        report = _report((100, 0, 100, 100, 100, 200), cost=cost)
        reader = _finality(report)
        before = reader.issued_bounds, reader.approved_dispatches, reader.reports
        result = reader.finalize(report.request)
        assert result is report.finality and result is not None
        projection = result.settlement()
        assert projection.finality.token_bound_exceeded
        assert projection.finality.input_bound_exceeded
        assert projection.finality.output_bound_exceeded
        assert projection.finality.cost_bound_exceeded is not free
        assert projection.settlement.estimated_micros == (0 if free else 200)
        assert before == (reader.issued_bounds, reader.approved_dispatches, reader.reports)
        assert not hasattr(reader, "release") and not hasattr(reader, "invalidate")


def test_expired_or_changed_current_control_does_not_reprice_or_erase_original_sources() -> None:
    report = _report()
    original = _finality(report)
    reader = _bounds(report.request.bound)
    for control in [
        replace(reader.control, observed_at=_END),
        replace(reader.control, models=()),
        replace(
            reader.control, models=(replace(report.request.bound.model, qualification_epoch=4),)
        ),
    ]:
        denied = replace(reader, control=control)
        with pytest.raises(SpendCostEvidenceError):
            denied.bound(report.request.bound.binding)
        result = original.finalize(report.request)
        assert result is report.finality and result is not None
        assert result.estimated_micros == 7
        assert result.request.bound.model is report.request.bound.model
    incomplete = _report(None)
    assert _finality(incomplete).finalize(incomplete.request) is None


@pytest.mark.parametrize("case", ["binding", "rates", "control", "report", "scope", "allocations"])
def test_privileged_nested_fixture_corruption_is_sanitized_not_unknown(case: str) -> None:
    reader = _bounds()
    report = _report()
    finality = _finality(report)
    if case == "binding":
        object.__setattr__(reader.preparations[0].bound.binding, "model_id", _PRIVATE + "/")
    elif case == "rates":
        object.__setattr__(
            reader.preparations[0].bound.model.short_context,
            "cache_write_usd_per_million",
            Decimal("-1"),
        )
    elif case == "control":
        object.__setattr__(reader.control, "models", [])
    elif case == "report":
        object.__setattr__(report, "finality", ProviderUsage())
    elif case == "scope":
        object.__setattr__(report.request.dispatch.reservation.request.limits[0], "scope", object())
    else:
        object.__setattr__(report.request.dispatch.reservation.request, "allocations", [])
    call: Callable[[], object]
    if case in {"binding", "rates", "control"}:
        call = partial(reader.bound, _cost().binding)
    else:
        call = partial(finality.finalize, report.request)
    _failure(SpendCostEvidenceErrorCode.INVALID_STATE, call)


def test_foreign_finality_request_types_are_invalid_not_incomplete() -> None:
    for value in [None, {}, _PRIVATE, object()]:
        _failure(
            SpendCostEvidenceErrorCode.INVALID_STATE,
            partial(_finality().finalize, cast(SpendCacheUsageFinalityRequest, value)),
        )


def _values() -> tuple[object, ...]:
    return _preparation(), _control(), _bounds(), _report(), _finality()


@pytest.mark.parametrize(
    "obj,name,value",
    [
        (_preparation(), "request", object()),
        (_preparation(), "bound", object()),
        (_bounds(), "preparations", []),
        (_bounds(), "preparations", ()),
        (_bounds(), "preparations", (object(),)),
        (_bounds(), "control", object()),
        (_finality(), "issued_bounds", []),
        (_finality(), "issued_bounds", ()),
        (_finality(), "issued_bounds", (object(),)),
        (_finality(), "approved_dispatches", []),
        (_finality(), "approved_dispatches", (object(),)),
        (_finality(), "reports", []),
        (_finality(), "reports", (object(),)),
        (_report(), "finality", object()),
    ],
)
def test_bootstrap_rejects_foreign_types_and_mutable_or_empty_required_inventories(
    obj: object, name: str, value: object
) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(obj, **{name: value})


def test_one_price_digest_cannot_name_different_model_contents() -> None:
    model = _cost().model
    with pytest.raises(SpendAdmissionContractError):
        SyntheticSpendCacheControlSnapshot(
            _START, (model, replace(model, model_id="another-model"))
        )
    with pytest.raises(SpendAdmissionContractError):
        SyntheticSpendCacheControlSnapshot(
            _START, (model, replace(model, qualification_epoch=4, pricing_digest=_OTHER))
        )


@pytest.mark.parametrize(
    "value,name", [(v, name) for v in _values() for name in get_type_hints(type(v))]
)
def test_all_reference_fields_are_private_frozen_slotted(value: object, name: str) -> None:
    assert repr(value) == type(value).__name__ + "()"
    assert not hasattr(value, "__dict__")
    with pytest.raises(FrozenInstanceError):
        setattr(value, name, None)


def test_ports_have_only_synchronous_lookup_and_no_mutating_capability() -> None:
    bounds: SpendCacheCostBoundPort = _bounds()
    finality: SpendCacheUsageFinalityPort = _finality()
    assert not inspect.iscoroutinefunction(bounds.bound)
    assert not inspect.iscoroutinefunction(finality.finalize)
    for reference in _values():
        for name in (
            "register",
            "refresh",
            "issue",
            "dispatch",
            "reserve",
            "settle",
            "release",
            "recover",
            "reset",
            "invalidate",
        ):
            assert not hasattr(reference, name)


def test_threaded_pure_reads_keep_exact_objects_and_fixed_sources() -> None:
    cost, report = _cost(), _report()
    bounds, finality = _bounds(cost), _finality(report)
    before = (
        bounds.preparations,
        bounds.control,
        finality.issued_bounds,
        finality.approved_dispatches,
        finality.reports,
    )

    def read(_: int) -> tuple[SpendCacheCostBound, SpendCacheUsageFinality | None]:
        return bounds.bound(cost.binding), finality.finalize(report.request)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = tuple(executor.map(read, range(128)))
    assert all(b is cost and f is report.finality for b, f in results)
    assert before == (
        bounds.preparations,
        bounds.control,
        finality.issued_bounds,
        finality.approved_dispatches,
        finality.reports,
    )
    assert cost.valid_until == _END


def test_event_loop_pure_reads_preserve_known_and_incomplete_sources() -> None:
    known, unknown = _report(), _report(None, attempt=2)
    finality = SyntheticSpendCacheFinality(
        (known.request.bound,),
        (known.request.dispatch, unknown.request.dispatch),
        (known, unknown),
    )

    async def read() -> list[SpendCacheUsageFinality | None]:
        async def once(index: int) -> SpendCacheUsageFinality | None:
            return finality.finalize(known.request if index % 2 == 0 else unknown.request)

        return await asyncio.gather(*(once(index) for index in range(64)))

    results = asyncio.run(read())
    assert all(
        result is (known.finality if i % 2 == 0 else None) for i, result in enumerate(results)
    )
