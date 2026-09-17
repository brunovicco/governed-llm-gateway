"""Private v2 shape/arithmetic/correlation proof, never verified provider facts."""

import inspect
from collections.abc import Callable
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, Inexact, Rounded, localcontext
from fractions import Fraction
from typing import cast, get_type_hints

import pytest
from governed_llm_gateway_core.application.spend_cost_evidence import SpendCostEvidenceError
from governed_llm_gateway_core.application.spend_cost_evidence_v2 import (
    SpendCacheCostBoundPort,
    SpendCacheUsageFinalityPort,
)
from governed_llm_gateway_core.domain.spend import SpendWindow
from governed_llm_gateway_core.domain.spend_admission import (
    MAX_SPEND_MICROS,
    SpendAdmissionContractError,
    SpendBudgetLimit,
    SpendBudgetScope,
    SpendDispatchReceipt,
    SpendReservation,
    SpendReservationRequest,
    SpendSettlement,
)
from governed_llm_gateway_core.domain.spend_cost_evidence import SpendCostShape
from governed_llm_gateway_core.domain.spend_cost_evidence_v2 import (
    SpendCacheCostBound,
    SpendCacheCostModel,
    SpendCacheCostShape,
    SpendCachePreparedBinding,
    SpendCacheRates,
    SpendCacheSettlementProjection,
    SpendCacheUsageFinality,
    SpendCacheUsageFinalityRequest,
)

_DIGEST = "sha256:" + "a" * 64
_OTHER = "sha256:" + "b" * 64
_START = datetime(2026, 9, 17, tzinfo=UTC)
_END = _START + timedelta(hours=1)
_RATE_FIELDS = tuple(f.name for f in fields(SpendCacheRates) if f.name != "schema_version")
_COUNT_FIELDS = (
    "input_tokens",
    "cache_read_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


class _IntSubclass(int):
    pass


class _DecimalSubclass(Decimal):
    pass


def _change[T](value: T, **changes: object) -> T:
    return cast(Callable[..., T], replace)(value, **changes)


def _rates(a: str = "0.3", b: str = "0.1", c: str = "0.5", d: str = "0.7") -> SpendCacheRates:
    return SpendCacheRates(Decimal(a), Decimal(b), Decimal(c), Decimal(d))


def _binding() -> SpendCachePreparedBinding:
    return SpendCachePreparedBinding(
        "preparation-private",
        "deployment-private",
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


def _model() -> SpendCacheCostModel:
    return SpendCacheCostModel(
        "synthetic-text-v2",
        "fixture-model",
        "fixture-profile",
        _DIGEST,
        _DIGEST,
        10,
        _rates(),
        _rates("0.6", "0.2", "1.1", "0.9"),
        _DIGEST,
        3,
        _START,
        _END,
    )


def _bound() -> SpendCacheCostBound:
    return SpendCacheCostBound(
        _binding(), _model(), 10, _DIGEST, _DIGEST, "bound-private", _START, _END
    )


def _request(bound: SpendCacheCostBound | None = None) -> SpendCacheUsageFinalityRequest:
    cost = bound if bound is not None else _bound()
    binding = cost.binding
    allocation = cost.allocation(fallback_index=0, attempt_number=1)
    intent = SpendReservationRequest(
        "execution-private",
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
                SpendBudgetScope("client-private", SpendWindow.DAILY, date(2026, 9, 17)),
                MAX_SPEND_MICROS,
            ),
        ),
        (allocation,),
    )
    return SpendCacheUsageFinalityRequest(
        cost,
        SpendDispatchReceipt(
            SpendReservation(intent, "owner-fence-private", 30),
            allocation,
            "dispatch-fence-private",
        ),
        "report-private",
    )


def _usage(
    i: int = 10,
    c: int = 2,
    w: int = 3,
    o: int = 5,
    q: int = 4,
    *,
    bound: SpendCacheCostBound | None = None,
) -> SpendCacheUsageFinality:
    return SpendCacheUsageFinality(_request(bound), i, c, w, o, q, i + o, "usage-evidence-private")


def _values() -> tuple[object, ...]:
    finality = _usage()
    return _binding(), _rates(), _model(), _bound(), _request(), finality, finality.settlement()


@pytest.mark.parametrize("obj", _values())
@pytest.mark.parametrize("version", [None, True, 2, "1.0", "2", "2.1", " 2.0", "2.0\n"])
def test_all_values_require_exact_version(obj: object, version: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(obj, schema_version=version)


@pytest.mark.parametrize(
    "obj,name", [(obj, name) for obj in _values() for name in get_type_hints(type(obj))]
)
def test_all_values_are_private_frozen_slotted_declarations(obj: object, name: str) -> None:
    assert repr(obj) == type(obj).__name__ + "()"
    assert not hasattr(obj, "__dict__")
    assert "private" not in repr(obj)
    with pytest.raises(FrozenInstanceError):
        setattr(obj, name, "1.0")


@pytest.mark.parametrize("name", _RATE_FIELDS)
@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        1,
        0.1,
        "0.1",
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        Decimal("-1"),
        Decimal("1e-13"),
        Decimal("0e-1000000"),
        Decimal("1e1000000"),
        Decimal(MAX_SPEND_MICROS + 1),
        Decimal("1.000000000000000000000000000000000"),
        _DecimalSubclass("0"),
    ],
)
def test_every_rate_is_explicit_exact_finite_and_bounded(name: str, value: object) -> None:
    with pytest.raises(SpendAdmissionContractError) as caught:
        _change(_rates(), **{name: value})
    assert str(value) not in str(caught.value)


@pytest.mark.parametrize("name", ["short_context", "long_context"])
@pytest.mark.parametrize("value", [None, (), {}, Decimal(0), 0, True])
def test_both_whole_request_bands_are_mandatory(name: str, value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_model(), **{name: value})


@pytest.mark.parametrize("name", ["input_threshold", "qualification_epoch"])
@pytest.mark.parametrize("value", [None, True, 0, -1, 1.0, "1", MAX_SPEND_MICROS + 1])
def test_threshold_and_epoch_are_positive_bounded_plain_ints(name: str, value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_model(), **{name: value})


@pytest.mark.parametrize(
    "shape", [None, "text_cache_partitioned_v2", SpendCostShape.TEXT_INPUT_OUTPUT]
)
def test_v2_shape_never_reinterprets_v1(shape: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_binding(), shape=shape)
    assert list(SpendCostShape) == [SpendCostShape.TEXT_INPUT_OUTPUT]


@pytest.mark.parametrize(
    "name", ["prepared_request_id", "deployment_id", "api_family", "model_id", "pricing_profile_id"]
)
@pytest.mark.parametrize("value", [None, True, "", " padded", "a/b", "a:b", "á", "x" * 129])
def test_binding_identities_are_bounded_private_metadata(name: str, value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_binding(), **{name: value})


@pytest.mark.parametrize(
    "name",
    [
        "configuration_digest",
        "policy_digest",
        "plan_digest",
        "registry_digest",
        "retry_policy_digest",
    ],
)
@pytest.mark.parametrize("value", [None, "", "unversioned", "sha256:" + "A" * 64])
def test_binding_provenance_is_canonical(name: str, value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_binding(), **{name: value})


@pytest.mark.parametrize("name", ["policy_epoch", "max_output_tokens"])
@pytest.mark.parametrize("value", [None, True, 0, -1, 1.0, MAX_SPEND_MICROS + 1])
def test_binding_fences_and_output_are_positive_plain_ints(name: str, value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_binding(), **{name: value})


@pytest.mark.parametrize("obj", [_model(), _bound()])
@pytest.mark.parametrize("name", ["valid_from", "valid_until"])
@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        "2026-09-17",
        date(2026, 9, 17),
        datetime(2026, 9, 17),
        datetime(2026, 9, 17, tzinfo=timezone(timedelta(hours=1))),
    ],
)
def test_windows_require_plain_utc_datetimes(obj: object, name: str, value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(obj, **{name: value})


@pytest.mark.parametrize("obj", [_model(), _bound()])
def test_windows_are_finite_ordered_and_bound_is_contained(obj: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(obj, valid_until=_START)
    with pytest.raises(SpendAdmissionContractError):
        _change(obj, valid_from=_END)
    with pytest.raises(SpendAdmissionContractError):
        replace(_bound(), valid_from=_START - timedelta(seconds=1))
    with pytest.raises(SpendAdmissionContractError):
        replace(_bound(), valid_until=_END + timedelta(seconds=1))
    # Pure declarations do not claim current clock/expiry validation.
    assert replace(_bound(), valid_until=_START + timedelta(seconds=1)).valid_until < _END


@pytest.mark.parametrize(
    "name", ["api_family", "model_id", "pricing_profile_id", "configuration_digest"]
)
def test_bound_correlates_exact_model_profile_configuration(name: str) -> None:
    model = _change(_model(), **{name: _OTHER if name.endswith("digest") else "foreign"})
    with pytest.raises(SpendAdmissionContractError):
        replace(_bound(), model=model)


@pytest.mark.parametrize("name", ["binding", "model"])
def test_bound_rejects_foreign_value_types(name: str) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_bound(), **{name: object()})


@pytest.mark.parametrize("value", [None, True, -1, 1.0, MAX_SPEND_MICROS + 1])
def test_input_cap_is_explicit_nonnegative_bounded_plain_int(value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_bound(), input_token_bound=value)


def test_envelope_uses_independent_maxima_across_both_bands() -> None:
    assert _bound().bound_micros == 20  # 10 * 1.1 + 10 * 0.9; not short band/cache guess.
    model = replace(
        _model(), short_context=_rates("2", "3", "1", "4"), long_context=_rates("0", "0", "0", "0")
    )
    assert (
        replace(_bound(), model=model).bound_micros == 70
    )  # nonmonotone rates still conservative.


@pytest.mark.parametrize("i,expected", [(9, 7), (10, 7), (11, 12)])
def test_observed_input_selects_whole_request_band(i: int, expected: int) -> None:
    assert _usage(i=i).estimated_micros == expected


@pytest.mark.parametrize(
    "i,c,w,o,q",
    [(0, 0, 0, 0, 0), (10, 0, 0, 5, 5), (10, 10, 0, 5, 0), (10, 0, 10, 5, 4), (11, 2, 3, 5, 4)],
)
def test_complete_partition_estimate_matches_exact_oracle(
    i: int, c: int, w: int, o: int, q: int
) -> None:
    finality = _usage(i, c, w, o, q)
    band = (
        finality.request.bound.model.long_context
        if i > 10
        else finality.request.bound.model.short_context
    )
    total = sum(
        (
            Fraction(rate) * count
            for rate, count in zip(
                (
                    band.ordinary_input_usd_per_million,
                    band.cache_read_usd_per_million,
                    band.cache_write_usd_per_million,
                    band.output_usd_per_million,
                ),
                (i - c - w, c, w, o),
                strict=True,
            )
        ),
        start=Fraction(0),
    )
    assert finality.estimated_micros == -(-total.numerator // total.denominator)
    assert (
        _change(finality, reasoning_output_tokens=o).estimated_micros == finality.estimated_micros
    )


@pytest.mark.parametrize("name", _COUNT_FIELDS)
@pytest.mark.parametrize(
    "value", [None, True, False, -1, 1.0, "1", MAX_SPEND_MICROS + 1, _IntSubclass(0)]
)
def test_all_usage_counts_are_mandatory_plain_bounded_integers(name: str, value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_usage(), **{name: value})


@pytest.mark.parametrize(
    "changes",
    [
        {"cache_read_input_tokens": 11},
        {"cache_write_input_tokens": 11},
        {"cache_read_input_tokens": 6, "cache_write_input_tokens": 5},
        {"reasoning_output_tokens": 6},
        {"total_tokens": 19},
    ],
)
def test_impossible_partition_reasoning_or_total_refuses(changes: dict[str, object]) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_usage(), **changes)


def test_fractional_rates_round_the_whole_sum_once_under_hostile_decimal_context() -> None:
    rates = _rates("0.1", "0.2", "0.3", "0.4")
    model = replace(_model(), short_context=rates, long_context=rates)
    bound = replace(
        _bound(), model=model, input_token_bound=3, binding=replace(_binding(), max_output_tokens=1)
    )
    usage = _usage(3, 1, 1, 1, 1, bound=bound)
    with localcontext() as context:
        context.prec = 1
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        assert usage.estimated_micros == 1  # Four separate ceils would be four.
        assert bound.bound_micros == 2
        assert usage.settlement().settlement.estimated_micros == 1


def test_truthful_token_excess_survives_free_pricing_in_projection() -> None:
    free = _rates("0", "0", "0", "0")
    bound = replace(_bound(), model=replace(_model(), short_context=free, long_context=free))
    usage = _usage(11, 2, 3, 11, 11, bound=bound)
    projection = usage.settlement()
    assert type(projection) is SpendCacheSettlementProjection
    assert type(projection.settlement) is SpendSettlement
    assert projection.finality is usage
    assert projection.finality.input_bound_exceeded
    assert projection.finality.output_bound_exceeded
    assert projection.finality.token_bound_exceeded
    assert not projection.finality.cost_bound_exceeded
    assert projection.settlement.estimated_micros == 0
    assert not hasattr(projection, "suspend")
    assert not hasattr(projection, "release")


def test_truthful_cost_excess_is_not_clamped_and_normal_case_has_no_violations() -> None:
    usage = _usage(100, 0, 100, 100, 100)
    assert usage.estimated_micros == 200
    assert usage.cost_bound_exceeded
    assert usage.token_bound_exceeded
    assert usage.settlement().settlement.estimated_micros == 200
    assert not _usage().token_bound_exceeded
    assert not _usage().cost_bound_exceeded


@pytest.mark.parametrize(
    "i,o,input_excess,output_excess", [(11, 5, True, False), (10, 11, False, True)]
)
def test_independent_violation_dimensions(
    i: int, o: int, input_excess: bool, output_excess: bool
) -> None:
    finality = _usage(i, 2, 3, o, o)
    assert finality.input_bound_exceeded is input_excess
    assert finality.output_bound_exceeded is output_excess
    assert finality.token_bound_exceeded


def test_conditional_envelope_covers_both_bands_and_all_small_partitions() -> None:
    for short, long in [
        (_rates(), _rates("0.6", "0.2", "1.1", "0.9")),
        (_rates("2", "3", "1", "4"), _rates()),
    ]:
        model = replace(_model(), input_threshold=3, short_context=short, long_context=long)
        bound = replace(
            _bound(),
            model=model,
            input_token_bound=6,
            binding=replace(_binding(), max_output_tokens=3),
        )
        request = _request(bound)
        for i in range(7):
            for c in range(i + 1):
                for w in range(i - c + 1):
                    for o in range(4):
                        finality = SpendCacheUsageFinality(
                            request, i, c, w, o, o, i + o, "toy-usage"
                        )
                        assert finality.estimated_micros <= bound.bound_micros
                        assert not finality.token_bound_exceeded


@pytest.mark.parametrize(
    "obj,name",
    [
        (_bound(), "estimator_digest"),
        (_bound(), "usage_contract_digest"),
        (_model(), "pricing_digest"),
        (_model(), "qualification_digest"),
        (_model(), "configuration_digest"),
    ],
)
def test_schedule_and_evidence_provenance_cannot_be_missing(obj: object, name: str) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(obj, **{name: "unversioned"})


@pytest.mark.parametrize(
    "obj,name",
    [
        (_bound(), "bound_evidence_id"),
        (_request(), "usage_report_id"),
        (_usage(), "usage_evidence_id"),
    ],
)
def test_private_evidence_handles_are_mandatory(obj: object, name: str) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(obj, **{name: ""})


def test_exact_integer_limit_and_unrepresentable_bound_usage_fail_closed() -> None:
    rates = _rates("1", "1", "1", "0")
    bound = replace(
        _bound(),
        model=replace(_model(), short_context=rates, long_context=rates),
        input_token_bound=MAX_SPEND_MICROS,
    )
    assert bound.bound_micros == MAX_SPEND_MICROS
    finality = _usage(MAX_SPEND_MICROS, 0, 0, 0, 0, bound=bound)
    assert finality.estimated_micros == MAX_SPEND_MICROS
    expensive = _rates("2", "2", "2", "0")
    with pytest.raises(SpendAdmissionContractError):
        replace(bound, model=replace(_model(), short_context=expensive, long_context=expensive))
    with pytest.raises(SpendAdmissionContractError):
        _usage(MAX_SPEND_MICROS, 0, MAX_SPEND_MICROS, 0, 0)


@pytest.mark.parametrize(
    "name",
    ["policy_epoch", "policy_digest", "plan_digest", "registry_digest", "retry_policy_digest"],
)
def test_finality_request_checks_original_intent(name: str) -> None:
    request = _request()
    reservation = request.dispatch.reservation
    changed = _change(reservation.request, **{name: 8 if name == "policy_epoch" else _OTHER})
    dispatch = replace(request.dispatch, reservation=replace(reservation, request=changed))
    with pytest.raises(SpendAdmissionContractError):
        replace(request, dispatch=dispatch)


@pytest.mark.parametrize(
    "name", ["deployment_id", "bound_micros", "pricing_digest", "bound_evidence_id"]
)
def test_finality_request_checks_exact_allocated_bound(name: str) -> None:
    request = _request()
    dispatch = request.dispatch
    changed = _change(
        dispatch.allocation,
        **{
            name: 21
            if name == "bound_micros"
            else _OTHER
            if name == "pricing_digest"
            else "foreign"
        },
    )
    intent = replace(dispatch.reservation.request, allocations=(changed,))
    foreign = replace(
        dispatch, allocation=changed, reservation=replace(dispatch.reservation, request=intent)
    )
    with pytest.raises(SpendAdmissionContractError):
        replace(request, dispatch=foreign)


@pytest.mark.parametrize(
    "obj,name",
    [
        (_request(), "bound"),
        (_request(), "dispatch"),
        (_usage(), "request"),
        (_usage().settlement(), "finality"),
    ],
)
def test_nested_values_reject_foreign_objects(obj: object, name: str) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(obj, **{name: object()})


def test_projections_preserve_exact_dispatch_and_private_evidence() -> None:
    bound = _bound()
    allocation = bound.allocation(fallback_index=0, attempt_number=1)
    assert allocation.bound_micros == 20
    assert allocation.pricing_digest == bound.model.pricing_digest
    assert allocation.bound_evidence_id == bound.bound_evidence_id
    usage = _usage()
    projection = usage.settlement()
    assert projection.settlement.dispatch is usage.request.dispatch
    assert projection.settlement.usage_evidence_id == usage.usage_evidence_id
    assert projection.settlement.estimated_micros == usage.estimated_micros


def test_v2_ports_are_sync_pure_without_registration_or_control_authority() -> None:
    assert get_type_hints(SpendCacheCostBoundPort.bound)["return"] is SpendCacheCostBound
    assert (
        get_type_hints(SpendCacheUsageFinalityPort.finalize)["return"]
        == SpendCacheUsageFinality | None
    )
    assert not inspect.iscoroutinefunction(SpendCacheCostBoundPort.bound)
    assert not inspect.iscoroutinefunction(SpendCacheUsageFinalityPort.finalize)
    for cls in (SpendCacheCostBoundPort, SpendCacheUsageFinalityPort):
        for forbidden in (
            "register",
            "refresh",
            "issue",
            "dispatch",
            "reserve",
            "settle",
            "release",
            "recover",
        ):
            # ABCMeta.register changes class metadata, not retained evidence sources.
            assert forbidden not in cls.__dict__
    assert issubclass(SpendCostEvidenceError, RuntimeError)
