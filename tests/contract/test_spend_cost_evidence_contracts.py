"""Private shape/correlation/arithmetic proof, not verified provider cost or finality."""

import inspect
from collections.abc import Callable
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date
from decimal import Decimal, Inexact, Rounded, localcontext
from fractions import Fraction
from typing import cast, get_type_hints

import pytest
from governed_llm_gateway_core.application.spend_cost_evidence import (
    SpendCostBoundPort,
    SpendCostEvidenceError,
    SpendCostEvidenceErrorCode,
    SpendUsageFinalityPort,
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
    SpendSettlementReceipt,
    to_reservation_micros,
)
from governed_llm_gateway_core.domain.spend_cost_evidence import (
    SpendCostShape,
    SpendPreparedTextBinding,
    SpendTextCostBound,
    SpendTextCostModel,
    SpendTextUsageFinality,
    SpendUsageFinalityRequest,
)

_DIGEST = "sha256:" + "a" * 64
_OTHER_DIGEST = "sha256:" + "b" * 64


def _change[T](value: T, **changes: object) -> T:
    return cast(Callable[..., T], replace)(value, **changes)


def _binding() -> SpendPreparedTextBinding:
    return SpendPreparedTextBinding(
        "preparation-private",
        "deployment-private",
        "synthetic-text-family",
        7,
        _DIGEST,
        _DIGEST,
        _DIGEST,
        _DIGEST,
        100,
        SpendCostShape.TEXT_INPUT_OUTPUT,
    )


def _model() -> SpendTextCostModel:
    return SpendTextCostModel("synthetic-text-family", _DIGEST, Decimal("0.15"), Decimal("0.60"))


def _bound() -> SpendTextCostBound:
    return SpendTextCostBound(_binding(), _model(), 1000, _DIGEST, _DIGEST, "bound-private")


def _request(
    bound: SpendTextCostBound | None = None, *, retry: bool = False
) -> SpendUsageFinalityRequest:
    cost = bound if bound is not None else _bound()
    first = cost.allocation(fallback_index=0, attempt_number=1)
    allocations = (first, replace(first, attempt_number=2)) if retry else (first,)
    binding = cost.binding
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
        allocations,
    )
    reservation = SpendReservation(intent, "owner-fence-private", 30.0)
    return SpendUsageFinalityRequest(
        cost,
        SpendDispatchReceipt(reservation, allocations[-1], "dispatch-fence-private"),
        "usage-report-private",
    )


def _finality() -> SpendTextUsageFinality:
    return SpendTextUsageFinality(_request(), 250, 50, "usage-evidence-private")


def _values() -> tuple[object, ...]:
    return _binding(), _model(), _bound(), _request(), _finality()


@pytest.mark.parametrize("value", _values())
@pytest.mark.parametrize("version", [None, True, 1.0, "", "1", "1.1", "2.0", " 1.0", "1.0\n"])
def test_every_cost_value_requires_exact_supported_version(value: object, version: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(value, schema_version=version)


@pytest.mark.parametrize("field", ["prepared_request_id", "deployment_id", "api_family"])
@pytest.mark.parametrize(
    "value", [None, True, 7, "", " padded", "a/b", "a:b", "a\n", "á", "x" * 129]
)
def test_preparation_identity_is_bounded_private_metadata(field: str, value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_binding(), **{field: value})


@pytest.mark.parametrize(
    "field", ["policy_digest", "plan_digest", "registry_digest", "retry_policy_digest"]
)
@pytest.mark.parametrize("value", [None, "", "a" * 64, "sha256:" + "A" * 64, "sha256:" + "a" * 63])
def test_all_preparation_provenance_requires_canonical_digest(field: str, value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_binding(), **{field: value})


@pytest.mark.parametrize("field", ["policy_epoch", "max_output_tokens"])
@pytest.mark.parametrize("value", [None, True, False, 0, -1, 1.0, "1", MAX_SPEND_MICROS + 1])
def test_positive_preparation_fences_and_output_limits_are_plain_bounded_integers(
    field: str,
    value: object,
) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_binding(), **{field: value})


@pytest.mark.parametrize("shape", [None, "text_input_output_v1", "media", "tools", "reasoning", 1])
def test_cost_shape_uses_closed_vocabulary_not_unparsed_feature_claims(shape: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_binding(), shape=shape)


@pytest.mark.parametrize("field", ["input_usd_per_million_tokens", "output_usd_per_million_tokens"])
@pytest.mark.parametrize(
    "rate",
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
        Decimal("-0.1"),
        Decimal("1e-13"),
        Decimal("1e-1000000"),
        Decimal("0e-1000000"),
        Decimal("1e1000000"),
        Decimal("9223372036854775808"),
        Decimal("1.000000000000000000000000000000000"),
    ],
)
def test_pricing_is_explicit_exact_finite_nonnegative_and_bounded(field: str, rate: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_model(), **{field: rate})


def test_rates_keep_supported_precision_without_rounding_or_implicit_discounts() -> None:
    for rate in (
        Decimal("0"),
        Decimal("0.000000000001"),
        Decimal("1e18"),
        Decimal(MAX_SPEND_MICROS),
    ):
        model = replace(_model(), input_usd_per_million_tokens=rate)
        assert model.input_usd_per_million_tokens == rate
    with pytest.raises(SpendAdmissionContractError):
        replace(_model(), api_family="")
    with pytest.raises(SpendAdmissionContractError):
        replace(_model(), pricing_digest="unversioned-price")


def test_exact_cost_ceil_is_independent_of_decimal_precision_rounding_and_traps() -> None:
    bound, finality = _bound(), _finality()
    tiny = replace(
        bound,
        model=replace(
            _model(),
            input_usd_per_million_tokens=Decimal("1e-12"),
            output_usd_per_million_tokens=Decimal("0"),
        ),
        input_token_bound=1,
    )
    with localcontext() as context:
        context.prec = 1
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        assert bound.bound_micros == 210
        assert finality.estimated_micros == 68
        assert tiny.bound_micros == 1
        assert bound.allocation(fallback_index=0, attempt_number=1).bound_micros == 210
        assert finality.settlement().estimated_micros == 68
    assert bound.bound_micros == to_reservation_micros(Decimal("0.000210"))


def test_round_once_after_summing_all_dimensions_not_once_per_rate() -> None:
    bound = replace(
        _bound(),
        binding=replace(_binding(), max_output_tokens=1),
        input_token_bound=1,
        model=replace(
            _model(),
            input_usd_per_million_tokens=Decimal("0.5"),
            output_usd_per_million_tokens=Decimal("0.5"),
        ),
    )
    assert bound.bound_micros == 1
    assert SpendTextUsageFinality(_request(bound), 1, 1, "complete-usage").estimated_micros == 1


@pytest.mark.parametrize("input_rate", ["0", "0.000000000001", "0.15", "1234567.891234"])
@pytest.mark.parametrize("output_rate", ["0", "0.000000000001", "0.60", "9876543.210987"])
@pytest.mark.parametrize("input_count,output_count", [(0, 0), (1, 1), (7, 3), (9999, 100)])
def test_pricing_matches_independent_exact_rational_oracle(
    input_rate: str,
    output_rate: str,
    input_count: int,
    output_count: int,
) -> None:
    model = replace(
        _model(),
        input_usd_per_million_tokens=Decimal(input_rate),
        output_usd_per_million_tokens=Decimal(output_rate),
    )
    bound = replace(_bound(), model=model, input_token_bound=10_000)
    finality = SpendTextUsageFinality(_request(bound), input_count, output_count, "complete-usage")
    exact = Fraction(input_rate) * input_count + Fraction(output_rate) * output_count
    floor, remainder = divmod(exact.numerator, exact.denominator)
    assert finality.estimated_micros == floor + bool(remainder)


@pytest.mark.parametrize("value", [None, True, False, -1, 1.0, "1", MAX_SPEND_MICROS + 1])
def test_input_bound_is_explicit_nonnegative_bounded_integer(value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_bound(), input_token_bound=value)


@pytest.mark.parametrize("field", ["estimator_digest", "usage_contract_digest"])
@pytest.mark.parametrize("value", [None, "", "sha256:" + "A" * 64, "not-versioned"])
def test_estimator_and_usage_contract_provenance_are_required(field: str, value: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_bound(), **{field: value})


def test_bound_model_family_must_match_preparation_and_evidence_is_required() -> None:
    with pytest.raises(SpendAdmissionContractError):
        replace(_bound(), model=replace(_model(), api_family="other-family"))
    with pytest.raises(SpendAdmissionContractError):
        replace(_bound(), bound_evidence_id="")


def test_zero_pricing_and_zero_input_are_explicit_not_missing_evidence() -> None:
    model = replace(
        _model(),
        input_usd_per_million_tokens=Decimal("0"),
        output_usd_per_million_tokens=Decimal("0"),
    )
    bound = replace(_bound(), model=model, input_token_bound=0)
    assert bound.bound_micros == 0
    assert bound.allocation(fallback_index=0, attempt_number=1).bound_micros == 0
    finality = SpendTextUsageFinality(_request(bound), 1, 101, "complete-excess")
    assert finality.token_bound_exceeded
    assert not finality.cost_bound_exceeded
    assert finality.estimated_micros == 0


def test_micro_rounding_does_not_hide_a_token_bound_violation() -> None:
    model = replace(
        _model(),
        input_usd_per_million_tokens=Decimal("0.000000000001"),
        output_usd_per_million_tokens=Decimal("0"),
    )
    bound = replace(_bound(), model=model, input_token_bound=1)
    finality = SpendTextUsageFinality(_request(bound), 2, 0, "complete-excess")
    assert bound.bound_micros == finality.estimated_micros == 1
    assert finality.token_bound_exceeded
    assert not finality.cost_bound_exceeded


def test_maximum_token_count_stays_exact_with_fractional_pricing() -> None:
    model = replace(
        _model(),
        input_usd_per_million_tokens=Decimal("0.000000000001"),
        output_usd_per_million_tokens=Decimal("0"),
    )
    bound = replace(_bound(), model=model, input_token_bound=MAX_SPEND_MICROS)
    finality = SpendTextUsageFinality(_request(bound), MAX_SPEND_MICROS, 0, "complete-usage")
    assert bound.bound_micros == finality.estimated_micros == 9_223_373
    assert not finality.token_bound_exceeded
    assert not finality.cost_bound_exceeded


@pytest.mark.parametrize(
    "index,attempt", [(-1, 1), (0, 0), (True, 1), (0, True), (MAX_SPEND_MICROS + 1, 1)]
)
def test_slot_projection_keeps_existing_strict_allocation_numbers(index: int, attempt: int) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _bound().allocation(fallback_index=index, attempt_number=attempt)


def test_boundary_cost_and_overflow_refuse_instead_of_clamping_or_fabricating_zero() -> None:
    model = replace(
        _model(),
        input_usd_per_million_tokens=Decimal(MAX_SPEND_MICROS),
        output_usd_per_million_tokens=Decimal("0"),
    )
    bound = replace(_bound(), model=model, input_token_bound=1)
    assert bound.bound_micros == MAX_SPEND_MICROS
    assert (
        SpendTextUsageFinality(_request(bound), 1, 0, "complete-usage").estimated_micros
        == MAX_SPEND_MICROS
    )
    with pytest.raises(SpendAdmissionContractError):
        replace(bound, input_token_bound=2)
    with pytest.raises(SpendAdmissionContractError):
        SpendTextUsageFinality(_request(bound), 2, 0, "complete-overflow")
    assert _bound().bound_micros == 210


@pytest.mark.parametrize(
    "field",
    ["policy_epoch", "policy_digest", "plan_digest", "registry_digest", "retry_policy_digest"],
)
def test_finality_cannot_attach_to_a_different_reservation_provenance(field: str) -> None:
    request = _request()
    intent = request.dispatch.reservation.request
    changed = _change(intent, **{field: 8 if field == "policy_epoch" else _OTHER_DIGEST})
    dispatch = replace(
        request.dispatch, reservation=replace(request.dispatch.reservation, request=changed)
    )
    with pytest.raises(SpendAdmissionContractError):
        replace(request, dispatch=dispatch)


@pytest.mark.parametrize(
    "field", ["deployment_id", "bound_micros", "pricing_digest", "bound_evidence_id"]
)
def test_finality_cannot_reprice_rebound_or_substitute_a_reserved_candidate(field: str) -> None:
    request = _request()
    allocation = request.dispatch.allocation
    value: object = {
        "deployment_id": "other-deployment",
        "bound_micros": 211,
        "pricing_digest": _OTHER_DIGEST,
        "bound_evidence_id": "other-evidence",
    }[field]
    changed = _change(allocation, **{field: value})
    intent = replace(request.dispatch.reservation.request, allocations=(changed,))
    dispatch = replace(
        request.dispatch,
        allocation=changed,
        reservation=replace(request.dispatch.reservation, request=intent),
    )
    with pytest.raises(SpendAdmissionContractError):
        replace(request, dispatch=dispatch)


def test_finality_retains_exact_retry_slot_execution_owner_and_fences() -> None:
    request = _request(retry=True)
    finality = SpendTextUsageFinality(request, 250, 50, "complete-retry-usage")
    outcome = finality.settlement()
    assert outcome.dispatch is request.dispatch
    assert outcome.dispatch.allocation.attempt_number == 2
    assert outcome.dispatch.dispatch_fence == "dispatch-fence-private"
    assert outcome.dispatch.reservation.owner_fence == "owner-fence-private"
    assert outcome.usage_evidence_id == "complete-retry-usage"
    assert outcome.estimated_micros == 68


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
@pytest.mark.parametrize("value", [None, True, False, -1, 1.0, "0", MAX_SPEND_MICROS + 1])
def test_complete_usage_has_no_missing_zero_defaults_or_implicit_counts(
    field: str, value: object
) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(_finality(), **{field: value})


def test_known_zero_is_not_unknown_usage_or_a_provider_status_inference() -> None:
    request = _request()
    finality = SpendTextUsageFinality(request, 0, 0, "explicit-complete-zero")
    known = finality.settlement()
    unknown = SpendSettlement(request.dispatch, None)
    assert known.estimated_micros == 0 and unknown.estimated_micros is None
    assert known != unknown
    assert not finality.token_bound_exceeded and not finality.cost_bound_exceeded
    for field in ("input_tokens", "output_tokens"):
        assert get_type_hints(SpendTextUsageFinality)[field] is int
        assert (
            inspect.signature(SpendTextUsageFinality).parameters[field].default
            is inspect.Parameter.empty
        )


def test_truthful_usage_and_cost_excess_are_visible_and_never_clamped() -> None:
    request = _request()
    for input_count, output_count in ((2000, 100), (1000, 200)):
        finality = SpendTextUsageFinality(request, input_count, output_count, "complete-excess")
        assert finality.token_bound_exceeded and finality.cost_bound_exceeded
        outcome = finality.settlement()
        receipt = SpendSettlementReceipt(outcome, "settlement-fence")
        assert receipt.bound_exceeded
        assert outcome.estimated_micros == finality.estimated_micros
        assert outcome.estimated_micros > request.bound.bound_micros


@pytest.mark.parametrize(
    "value,field",
    [
        (_bound(), "binding"),
        (_bound(), "model"),
        (_request(), "bound"),
        (_request(), "dispatch"),
        (_finality(), "request"),
    ],
)
def test_nested_values_refuse_unvalidated_lookalikes(value: object, field: str) -> None:
    with pytest.raises(SpendAdmissionContractError):
        _change(value, **{field: object()})


@pytest.mark.parametrize(
    "value,field",
    [
        (_bound(), "bound_evidence_id"),
        (_request(), "usage_report_id"),
        (_finality(), "usage_evidence_id"),
    ],
)
@pytest.mark.parametrize("handle", [None, "", "a/b", "padded ", "x" * 129])
def test_evidence_handles_are_explicit_opaque_private_ids(
    value: object, field: str, handle: object
) -> None:
    with pytest.raises(SpendAdmissionContractError) as refused:
        _change(value, **{field: handle})
    assert "padded" not in str(refused.value)


@pytest.mark.parametrize("value", _values())
def test_cost_evidence_is_frozen_slotted_and_private_in_default_representation(
    value: object,
) -> None:
    assert not hasattr(value, "__dict__")
    for descriptor in fields(cast(type, type(value))):
        with pytest.raises(FrozenInstanceError):
            setattr(value, descriptor.name, getattr(value, descriptor.name))
    for marker in ("private", "synthetic-text-family", _DIGEST):
        assert marker not in repr(value)


def test_mutable_scalar_and_value_subclasses_cannot_masquerade_as_exact_contracts() -> None:
    class CustomText(str):
        pass

    class CustomDecimal(Decimal):
        pass

    class CustomBinding(SpendPreparedTextBinding):
        pass

    with pytest.raises(SpendAdmissionContractError):
        replace(_binding(), schema_version=CustomText("1.0"))
    with pytest.raises(SpendAdmissionContractError):
        replace(_binding(), api_family=CustomText("synthetic-text-family"))
    with pytest.raises(SpendAdmissionContractError):
        replace(_model(), input_usd_per_million_tokens=CustomDecimal("0.15"))
    subclass = CustomBinding(
        **{f.name: getattr(_binding(), f.name) for f in fields(SpendPreparedTextBinding)}
    )
    with pytest.raises(SpendAdmissionContractError):
        replace(_bound(), binding=subclass)


def test_equality_binds_issuance_and_capability_provenance_without_authentication() -> None:
    assert _bound() == _bound()
    for field in ("estimator_digest", "usage_contract_digest"):
        assert _change(_bound(), **{field: _OTHER_DIGEST}) != _bound()
    assert replace(_binding(), prepared_request_id="other-preparation") != _binding()
    assert replace(_request(), usage_report_id="other-report") != _request()
    assert replace(_finality(), usage_evidence_id="other-issued-evidence") != _finality()
    request = _request()
    forged = replace(
        request, dispatch=replace(request.dispatch, dispatch_fence="self-created-fence")
    )
    assert forged != request  # Shape can remain valid; only an adapter can verify actual issuance.


@pytest.mark.parametrize("code", list(SpendCostEvidenceErrorCode))
def test_cost_errors_are_closed_generic_and_not_provider_retry_classifications(
    code: SpendCostEvidenceErrorCode,
) -> None:
    error = SpendCostEvidenceError(code)
    assert error.code is code
    assert error.args == ("spend cost evidence failed",)
    assert not hasattr(error, "retryable")
    with pytest.raises(SpendAdmissionContractError) as refused:
        SpendCostEvidenceError(cast(SpendCostEvidenceErrorCode, "raw-provider-private-marker"))
    assert "raw-provider-private-marker" not in str(refused.value)


def test_cost_ports_are_synchronous_separate_no_mutation_or_authorization_capabilities() -> None:
    bound = SpendCostBoundPort.bound
    finalize = SpendUsageFinalityPort.finalize
    assert not inspect.iscoroutinefunction(bound)
    assert not inspect.iscoroutinefunction(finalize)
    assert get_type_hints(bound)["binding"] is SpendPreparedTextBinding
    assert get_type_hints(bound)["return"] is SpendTextCostBound
    assert get_type_hints(finalize)["request"] is SpendUsageFinalityRequest
    assert get_type_hints(finalize)["return"] == SpendTextUsageFinality | None
    assert not hasattr(SpendCostBoundPort, "finalize")
    assert not hasattr(SpendUsageFinalityPort, "bound")
    for port in (SpendCostBoundPort, SpendUsageFinalityPort):
        for method in (
            "reserve",
            "dispatch",
            "settle",
            "close",
            "renew",
            "publish",
            "reset",
            "recover",
            "authorize",
        ):
            assert not hasattr(port, method)
    names = {f.name for value in _values() for f in fields(cast(type, type(value)))}
    assert not names.intersection(
        {"messages", "credentials", "headers", "total_cost_usd", "tenant_id", "response_id"}
    )
