"""Synthetic lookup/manual composition proof, not real provider capability or serving."""

import asyncio
import inspect
import traceback
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

import pytest
from governed_llm_gateway_contracts import (
    AudioBlock,
    AudioMediaType,
    Base64Source,
    DocumentBlock,
    DocumentMediaType,
    HttpsUrlSource,
    ImageBlock,
    ImageInput,
    ImageMediaType,
    Message,
    MessageRole,
    StructuredOutputSchema,
    TextBlock,
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolResultBlock,
    ToolUseBlock,
)
from governed_llm_gateway_core.adapters.spend_admission_memory import (
    InMemorySpendAdmissionReader,
    InMemorySpendAdmissionState,
    InMemorySpendAdmissionWorker,
)
from governed_llm_gateway_core.adapters.spend_cost_evidence_synthetic import (
    SyntheticSpendCostBounds,
    SyntheticSpendPreparedText,
    SyntheticSpendUsageFinality,
    SyntheticSpendUsageReport,
)
from governed_llm_gateway_core.application.provider import ProviderRequest, ProviderUsage
from governed_llm_gateway_core.application.spend_admission import SpendControlError
from governed_llm_gateway_core.application.spend_cost_evidence import (
    SpendCostBoundPort,
    SpendCostEvidenceError,
    SpendCostEvidenceErrorCode,
    SpendUsageFinalityPort,
)
from governed_llm_gateway_core.domain.spend import SpendWindow
from governed_llm_gateway_core.domain.spend_admission import (
    SpendAdmissionContractError,
    SpendAttemptState,
    SpendBudgetLimit,
    SpendBudgetScope,
    SpendBudgetSnapshot,
    SpendDispatchReceipt,
    SpendReservation,
    SpendReservationRequest,
    SpendSettlement,
)
from governed_llm_gateway_core.domain.spend_cost_evidence import (
    SpendCostShape,
    SpendPreparedTextBinding,
    SpendTextCostBound,
    SpendTextCostModel,
    SpendTextUsageFinality,
    SpendUsageFinalityRequest,
)

_DAY = date(2026, 9, 17)
_DIGEST = "sha256:" + "a" * 64
_OTHER = "sha256:" + "b" * 64
_PRIVATE = "private-payload-marker"


def _run[T](coroutine: Coroutine[object, object, T]) -> T:
    return asyncio.run(coroutine)


def _change[T](value: T, **changes: object) -> T:
    return cast(Callable[..., T], replace)(value, **changes)


def _bound(index: int = 0) -> SpendTextCostBound:
    binding = SpendPreparedTextBinding(
        f"preparation-private-{index}",
        f"deployment-private-{index}",
        "synthetic_text_v1",
        7,
        _DIGEST,
        _DIGEST,
        _DIGEST,
        _DIGEST,
        100,
        SpendCostShape.TEXT_INPUT_OUTPUT,
    )
    model = SpendTextCostModel("synthetic_text_v1", _DIGEST, Decimal("0.15"), Decimal("0.60"))
    return SpendTextCostBound(binding, model, 1000, _DIGEST, _DIGEST, f"bound-private-{index}")


def _preparation(bound: SpendTextCostBound | None = None) -> SyntheticSpendPreparedText:
    value = bound if bound is not None else _bound()
    request = ProviderRequest(
        "model-private",
        (Message(MessageRole.USER, _PRIVATE),),
        max_output_tokens=value.binding.max_output_tokens,
    )
    return SyntheticSpendPreparedText(request, value)


def _intent(bound: SpendTextCostBound, *, index: int = 0) -> SpendReservationRequest:
    binding = bound.binding
    scopes = tuple(
        SpendBudgetScope(
            "client-private",
            window,
            _DAY if window is SpendWindow.DAILY else _DAY.replace(day=1),
            workload,
        )
        for workload in (None, "rag.answer")
        for window in (SpendWindow.DAILY, SpendWindow.MONTHLY)
    )
    return SpendReservationRequest(
        f"execution-private-{index}",
        f"owner-private-{index}",
        "client-private",
        "rag.answer",
        _DAY,
        binding.policy_epoch,
        binding.policy_digest,
        binding.plan_digest,
        binding.registry_digest,
        binding.retry_policy_digest,
        tuple(SpendBudgetLimit(scope, 10_000) for scope in scopes),
        tuple(bound.allocation(fallback_index=0, attempt_number=n) for n in (1, 2)),
    )


def _dispatch(bound: SpendTextCostBound | None = None, *, attempt: int = 1) -> SpendDispatchReceipt:
    value = bound if bound is not None else _bound()
    intent = _intent(value)
    return SpendDispatchReceipt(
        SpendReservation(intent, "owner-fence-private", 30.0),
        intent.allocations[attempt - 1],
        f"dispatch-fence-private-{attempt}",
    )


def _report(
    counts: tuple[int, int] | None = (250, 50),
    *,
    bound: SpendTextCostBound | None = None,
    dispatch: SpendDispatchReceipt | None = None,
) -> SyntheticSpendUsageReport:
    value = bound if bound is not None else _bound()
    claim = dispatch if dispatch is not None else _dispatch(value)
    request = SpendUsageFinalityRequest(value, claim, "report-private")
    finality = (
        SpendTextUsageFinality(request, *counts, "usage-private") if counts is not None else None
    )
    return SyntheticSpendUsageReport(request, finality)


def _finality(report: SyntheticSpendUsageReport | None = None) -> SyntheticSpendUsageFinality:
    value = report if report is not None else _report()
    return SyntheticSpendUsageFinality((value.request.bound,), (value.request.dispatch,), (value,))


def _failure(code: SpendCostEvidenceErrorCode, call: Callable[[], object]) -> None:
    with pytest.raises(SpendCostEvidenceError) as caught:
        call()
    assert caught.value.code is code
    assert str(caught.value) == "spend cost evidence failed"
    assert _PRIVATE not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("role", [MessageRole.SYSTEM, MessageRole.USER, MessageRole.ASSISTANT])
@pytest.mark.parametrize("blocks", [False, True])
def test_exact_text_preparations_are_retained_without_counting(
    role: MessageRole, blocks: bool
) -> None:
    message = (
        Message(role, "", blocks=(TextBlock(_PRIVATE), TextBlock("second")))
        if blocks
        else Message(role, _PRIVATE)
    )
    request = ProviderRequest("model-private", (message,), max_output_tokens=100)
    preparation = SyntheticSpendPreparedText(request, _bound())
    capability: SpendCostBoundPort = SyntheticSpendCostBounds((preparation,))
    assert preparation.request is request
    assert capability.bound(replace(preparation.bound.binding)) is preparation.bound
    assert preparation.bound.input_token_bound == 1000  # Explicit fixture, not inferred from text.


@pytest.mark.parametrize(
    "block",
    [
        ImageBlock(ImageMediaType.PNG, HttpsUrlSource("https://example.com/image.png")),
        AudioBlock(AudioMediaType.WAV, Base64Source("eA==")),
        DocumentBlock(DocumentMediaType.PDF, Base64Source("eA==")),
        ToolUseBlock(ToolCall("call-private", "lookup", {})),
        ToolResultBlock(ToolResult("call-private", _PRIVATE)),
    ],
)
def test_nontext_canonical_blocks_are_refused(block: object) -> None:
    role = MessageRole.ASSISTANT if isinstance(block, ToolUseBlock) else MessageRole.USER
    message = _change(Message(role, ""), blocks=(block,))
    request = ProviderRequest("model-private", (message,), max_output_tokens=100)
    with pytest.raises(SpendAdmissionContractError):
        SyntheticSpendPreparedText(request, _bound())


def test_legacy_images_schema_and_declared_tools_are_refused() -> None:
    preparation = _preparation()
    changes = (
        {
            "messages": (
                Message(
                    MessageRole.USER,
                    _PRIVATE,
                    (ImageInput(ImageMediaType.PNG, "https://example.com/image.png"),),
                ),
            )
        },
        {
            "structured_output": StructuredOutputSchema(
                "record", {"type": "object", "properties": {}, "additionalProperties": False}
            )
        },
        {
            "tools": (
                ToolDefinition(
                    "lookup",
                    "lookup",
                    {"type": "object", "properties": {}, "additionalProperties": False},
                ),
            )
        },
    )
    for change in changes:
        request = _change(preparation.request, **change)
        with pytest.raises(SpendAdmissionContractError):
            SyntheticSpendPreparedText(request, preparation.bound)


@pytest.mark.parametrize(
    "changes",
    [
        {"max_output_tokens": 99},
        {"max_output_tokens": 100.0},
        {"timeout_seconds": True},
        {"timeout_seconds": float("inf")},
        {"timeout_seconds": float("nan")},
        {"tools": []},
        {"messages": []},
        {"model": True},
    ],
)
def test_malformed_or_mismatched_canonical_preparations_refuse(changes: dict[str, object]) -> None:
    preparation = _preparation()
    request = replace(preparation.request)
    for name, value in changes.items():
        object.__setattr__(request, name, value)
    with pytest.raises(SpendAdmissionContractError):
        SyntheticSpendPreparedText(request, preparation.bound)


@pytest.mark.parametrize(
    "changes",
    [
        {"role": "user"},
        {"role": MessageRole.TOOL},
        {"content": ""},
        {"content": True},
        {"images": []},
        {"blocks": []},
    ],
)
def test_malformed_messages_do_not_pass_text_only_guards(changes: dict[str, object]) -> None:
    preparation = _preparation()
    message = replace(preparation.request.messages[0])
    for name, value in changes.items():
        object.__setattr__(message, name, value)
    request = replace(preparation.request)
    object.__setattr__(request, "messages", (message,))
    with pytest.raises(SpendAdmissionContractError):
        SyntheticSpendPreparedText(request, preparation.bound)


def test_no_real_provider_family_can_be_bootstrapped_or_resolved() -> None:
    value = _bound()
    real = replace(
        value,
        binding=replace(value.binding, api_family="real-provider"),
        model=replace(value.model, api_family="real-provider"),
    )
    with pytest.raises(SpendAdmissionContractError):
        _preparation(real)
    capability = SyntheticSpendCostBounds((_preparation(value),))
    _failure(SpendCostEvidenceErrorCode.UNSUPPORTED, lambda: capability.bound(real.binding))
    report = _report()
    allocation = real.allocation(fallback_index=0, attempt_number=1)
    intent = _intent(real)
    dispatch = replace(
        report.request.dispatch,
        reservation=replace(report.request.dispatch.reservation, request=intent),
        allocation=allocation,
    )
    request = SpendUsageFinalityRequest(real, dispatch, "report-private")
    _failure(SpendCostEvidenceErrorCode.UNSUPPORTED, lambda: _finality().finalize(request))


@pytest.mark.parametrize(
    "changes",
    [
        {"deployment_id": "other-private"},
        {"policy_epoch": 8},
        {"policy_digest": _OTHER},
        {"plan_digest": _OTHER},
        {"registry_digest": _OTHER},
        {"retry_policy_digest": _OTHER},
        {"max_output_tokens": 101},
    ],
)
def test_same_preparation_handle_with_changed_binding_conflicts(changes: dict[str, object]) -> None:
    preparation = _preparation()
    capability = SyntheticSpendCostBounds((preparation,))
    supplied = _change(preparation.bound.binding, **changes)
    _failure(SpendCostEvidenceErrorCode.CONFLICT, lambda: capability.bound(supplied))
    assert capability.bound(preparation.bound.binding) is preparation.bound


def test_unknown_preparation_handle_is_not_implicitly_registered() -> None:
    capability = SyntheticSpendCostBounds((_preparation(),))
    _failure(SpendCostEvidenceErrorCode.UNAVAILABLE, lambda: capability.bound(_bound(1).binding))
    assert len(capability.preparations) == 1


@pytest.mark.parametrize("value", [None, True, "private-payload-marker", ProviderUsage()])
def test_invalid_inputs_never_become_evidence(value: object) -> None:
    capability = SyntheticSpendCostBounds((_preparation(),))
    _failure(
        SpendCostEvidenceErrorCode.INVALID_STATE,
        lambda: capability.bound(cast(SpendPreparedTextBinding, value)),
    )
    _failure(
        SpendCostEvidenceErrorCode.INVALID_STATE,
        lambda: _finality().finalize(cast(SpendUsageFinalityRequest, value)),
    )


@pytest.mark.parametrize("counts", [None, (0, 0), (250, 50), (1200, 150)])
def test_explicit_unknown_zero_known_and_excess_sources_are_distinct(
    counts: tuple[int, int] | None,
) -> None:
    report = _report(counts)
    capability: SpendUsageFinalityPort = _finality(report)
    result = capability.finalize(replace(report.request))
    assert result is report.finality
    assert capability.finalize(report.request) is result
    if counts is None:
        assert result is None
    else:
        assert result is not None
        assert (result.input_tokens, result.output_tokens) == counts
        assert result.token_bound_exceeded is (counts == (1200, 150))


def test_usage_defaults_missing_report_and_unapproved_dispatch_do_not_mean_zero() -> None:
    report = _report(None)
    empty = SyntheticSpendUsageFinality((report.request.bound,), (), ())
    _failure(SpendCostEvidenceErrorCode.UNAVAILABLE, lambda: empty.finalize(report.request))
    no_reports = replace(empty, approved_dispatches=(report.request.dispatch,))
    _failure(SpendCostEvidenceErrorCode.UNAVAILABLE, lambda: no_reports.finalize(report.request))
    missing = replace(report.request, usage_report_id="absent-private")
    _failure(SpendCostEvidenceErrorCode.UNAVAILABLE, lambda: _finality(report).finalize(missing))
    assert _finality(report).finalize(report.request) is None
    with pytest.raises(SpendAdmissionContractError):
        _change(report, finality=ProviderUsage())


@pytest.mark.parametrize(
    "field", ["input_token_bound", "estimator_digest", "usage_contract_digest", "model"]
)
def test_same_bound_evidence_with_changed_fact_is_not_trusted(field: str) -> None:
    report = _report()
    bound = report.request.bound
    value: object = {
        "input_token_bound": 999,
        "estimator_digest": _OTHER,
        "usage_contract_digest": _OTHER,
        "model": replace(bound.model, input_usd_per_million_tokens=Decimal("0.1499")),
    }[field]
    changed = _change(bound, **{field: value})
    assert changed.bound_micros == bound.bound_micros
    request = replace(report.request, bound=changed)
    _failure(SpendCostEvidenceErrorCode.CONFLICT, lambda: _finality(report).finalize(request))


@pytest.mark.parametrize("field", ["execution_id", "owner_id", "client_id", "admitted_on"])
def test_foreign_execution_identity_cannot_borrow_a_report(field: str) -> None:
    report = _report()
    intent = report.request.dispatch.reservation.request
    changes: dict[str, object] = {field: "foreign-private"}
    if field == "client_id":
        changes["limits"] = tuple(
            replace(limit, scope=replace(limit.scope, client_id="foreign-private"))
            for limit in intent.limits
        )
    elif field == "admitted_on":
        changes[field] = date(2026, 9, 18)
        changes["limits"] = tuple(
            replace(
                limit,
                scope=replace(
                    limit.scope,
                    window_start=date(2026, 9, 18)
                    if limit.scope.window is SpendWindow.DAILY
                    else date(2026, 9, 1),
                ),
            )
            for limit in intent.limits
        )
    changed = _change(intent, **changes)
    dispatch = replace(
        report.request.dispatch,
        reservation=replace(report.request.dispatch.reservation, request=changed),
    )
    request = replace(report.request, dispatch=dispatch)
    _failure(SpendCostEvidenceErrorCode.CONFLICT, lambda: _finality(report).finalize(request))


@pytest.mark.parametrize(
    "field", ["owner_fence", "owner_timeout_seconds", "attempt", "dispatch_fence"]
)
def test_exact_owner_slot_and_dispatch_fences_are_required(field: str) -> None:
    report = _report()
    dispatch = report.request.dispatch
    if field in ("owner_fence", "owner_timeout_seconds"):
        value: object = "other-fence-private" if field == "owner_fence" else 29.0
        dispatch = replace(dispatch, reservation=_change(dispatch.reservation, **{field: value}))
    elif field == "attempt":
        dispatch = replace(dispatch, allocation=dispatch.reservation.request.allocations[1])
    else:
        dispatch = replace(dispatch, dispatch_fence="absent-fence-private")
    request = replace(report.request, dispatch=dispatch)
    code = (
        SpendCostEvidenceErrorCode.UNAVAILABLE
        if field == "dispatch_fence"
        else SpendCostEvidenceErrorCode.CONFLICT
    )
    _failure(code, lambda: _finality(report).finalize(request))


def test_report_cannot_be_reassigned_between_independently_registered_attempts() -> None:
    report = _report()
    second = _dispatch(attempt=2)
    capability = SyntheticSpendUsageFinality(
        (report.request.bound,), (report.request.dispatch, second), (report,)
    )
    request = replace(report.request, dispatch=second)
    _failure(SpendCostEvidenceErrorCode.CONFLICT, lambda: capability.finalize(request))


@pytest.mark.parametrize(
    "kind",
    [
        "preparation",
        "bound-evidence",
        "pricing",
        "dispatch-fence",
        "slot",
        "report-id",
        "report-slot",
        "usage-evidence",
    ],
)
def test_ambiguous_fixture_inventories_refuse_bootstrap(kind: str) -> None:
    report = _report()
    bound = report.request.bound
    first = report.request.dispatch
    if kind in ("preparation", "bound-evidence", "pricing"):
        other_bound = _bound(1)
        if kind == "preparation":
            other_bound = replace(
                other_bound,
                binding=replace(
                    other_bound.binding, prepared_request_id=bound.binding.prepared_request_id
                ),
            )
        elif kind == "bound-evidence":
            other_bound = replace(other_bound, bound_evidence_id=bound.bound_evidence_id)
        else:
            other_bound = replace(
                other_bound,
                model=replace(other_bound.model, output_usd_per_million_tokens=Decimal("0.61")),
            )
        with pytest.raises(SpendAdmissionContractError):
            SyntheticSpendCostBounds((_preparation(bound), _preparation(other_bound)))
        return
    second = _dispatch(attempt=2)
    if kind == "dispatch-fence":
        second = replace(second, dispatch_fence=first.dispatch_fence)
    elif kind == "slot":
        second = replace(first, dispatch_fence="other-fence-private")
    other_request = replace(report.request, dispatch=second, usage_report_id="other-report-private")
    if kind == "report-id":
        other_request = replace(other_request, usage_report_id=report.request.usage_report_id)
    elif kind == "report-slot":
        other_request = replace(other_request, dispatch=first)
    other = SyntheticSpendUsageReport(
        other_request,
        SpendTextUsageFinality(
            other_request,
            1,
            1,
            "usage-private" if kind == "usage-evidence" else "other-usage-private",
        ),
    )
    with pytest.raises(SpendAdmissionContractError):
        SyntheticSpendUsageFinality((bound,), (first, second), (report, other))


def test_reports_require_independent_registration_and_matching_finality() -> None:
    report = _report()
    with pytest.raises(SpendAdmissionContractError):
        SyntheticSpendUsageFinality((_bound(1),), (report.request.dispatch,), (report,))
    with pytest.raises(SpendAdmissionContractError):
        SyntheticSpendUsageFinality((report.request.bound,), (), (report,))
    with pytest.raises(SpendAdmissionContractError):
        _change(report, request=replace(report.request, usage_report_id="other-private"))


def test_token_violation_hidden_by_free_pricing_survives_lookup() -> None:
    bound = _bound()
    free = replace(
        bound,
        model=replace(
            bound.model,
            input_usd_per_million_tokens=Decimal(0),
            output_usd_per_million_tokens=Decimal(0),
        ),
    )
    report = _report((1001, 101), bound=free)
    result = _finality(report).finalize(report.request)
    assert result is not None
    assert result.estimated_micros == 0
    assert result.token_bound_exceeded and not result.cost_bound_exceeded
    # No generic settlement can convey this flag; model suspension integration is not supplied.


def test_fixtures_and_capabilities_are_private_frozen_and_have_no_mutating_permissions() -> None:
    preparation = _preparation()
    report = _report()
    values = (preparation, report, SyntheticSpendCostBounds((preparation,)), _finality(report))
    for value in values:
        assert _PRIVATE not in repr(value)
        assert "private" not in repr(value)
        assert all(not field.repr for field in fields(value))
        name = fields(value)[0].name
        with pytest.raises(FrozenInstanceError):
            setattr(value, name, None)
    for capability, method in ((values[2], "bound"), (values[3], "finalize")):
        public = {
            name
            for name, fn in inspect.getmembers(type(capability), inspect.isfunction)
            if not name.startswith("_")
        }
        assert public == {method}
        assert not inspect.iscoroutinefunction(getattr(capability, method))


def test_concurrent_reads_reuse_exact_facts_without_issuing_new_handles() -> None:
    preparation = _preparation()
    bounds = SyntheticSpendCostBounds((preparation,))
    report = _report()
    finality = _finality(report)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = tuple(
            pool.map(
                lambda _: (
                    bounds.bound(preparation.bound.binding),
                    finality.finalize(report.request),
                ),
                range(64),
            )
        )
    assert all(bound is preparation.bound and usage is report.finality for bound, usage in results)


def test_modeled_corruption_fails_closed_without_raw_exception_text() -> None:
    preparation = _preparation()
    capability = SyntheticSpendCostBounds((preparation,))
    object.__setattr__(preparation.request, "tools", [_PRIVATE])
    _failure(
        SpendCostEvidenceErrorCode.INVALID_STATE,
        lambda: capability.bound(preparation.bound.binding),
    )
    report = _report()
    finality = _finality(report)
    assert report.finality is not None
    object.__setattr__(report.finality, "input_tokens", True)
    _failure(SpendCostEvidenceErrorCode.INVALID_STATE, lambda: finality.finalize(report.request))


@pytest.mark.parametrize("values", [None, [], (), (_PRIVATE,)])
def test_cost_inventory_requires_exact_nonempty_typed_tuple(values: object) -> None:
    with pytest.raises(SpendAdmissionContractError):
        SyntheticSpendCostBounds(cast(tuple[SyntheticSpendPreparedText, ...], values))


@pytest.mark.parametrize("field", ["issued_bounds", "approved_dispatches", "reports"])
def test_finality_inventory_rejects_mutable_untyped_containers(field: str) -> None:
    capability = _finality()
    with pytest.raises(SpendAdmissionContractError):
        _change(capability, **{field: []})


def test_unknown_bound_handle_cannot_become_a_new_registered_fact() -> None:
    report = _report()
    foreign = replace(report.request.bound, bound_evidence_id="unregistered-bound-private")
    request = SpendUsageFinalityRequest(foreign, _dispatch(foreign), "report-private")
    _failure(SpendCostEvidenceErrorCode.UNAVAILABLE, lambda: _finality(report).finalize(request))


@pytest.mark.parametrize("kind", ["limit-scope", "slot-type", "finality-request"])
def test_invalid_nested_retained_metadata_is_sanitized(kind: str) -> None:
    report = _report()
    capability = _finality(report)
    intent = report.request.dispatch.reservation.request
    if kind == "limit-scope":
        object.__setattr__(intent.limits[0], "scope", _PRIVATE)
    elif kind == "slot-type":
        object.__setattr__(intent, "allocations", (_PRIVATE,))
    else:
        assert report.finality is not None
        object.__setattr__(report.finality, "request", _PRIVATE)
    _failure(SpendCostEvidenceErrorCode.INVALID_STATE, lambda: capability.finalize(report.request))


def test_exact_class_substitutions_do_not_extend_the_synthetic_supported_shape() -> None:
    class ExtendedText(TextBlock):
        pass

    class ExtendedRequest(ProviderRequest):
        pass

    request = ProviderRequest(
        "model-private",
        (Message(MessageRole.USER, "", blocks=(ExtendedText(_PRIVATE),)),),
        max_output_tokens=100,
    )
    with pytest.raises(SpendAdmissionContractError):
        SyntheticSpendPreparedText(request, _bound())
    extended = ExtendedRequest("model-private", (Message(MessageRole.USER, _PRIVATE),), 100)
    with pytest.raises(SpendAdmissionContractError):
        SyntheticSpendPreparedText(extended, _bound())


@pytest.mark.parametrize("counts", [None, (0, 0), (250, 50), (1200, 150)])
def test_manual_composition_settles_once_and_closes_only_unused_allocations(
    counts: tuple[int, int] | None,
) -> None:
    bound = SyntheticSpendCostBounds((_preparation(),)).bound(_bound().binding)
    intent = _intent(bound)
    approved: list[SpendSettlement] = []
    state = InMemorySpendAdmissionState(
        budgets=tuple(SpendBudgetSnapshot(limit, 0, 0) for limit in intent.limits),
        approved_requests=(intent, _intent(bound, index=1)),
        owner_lease_seconds=30.0,
        usage_validator=lambda outcome: outcome in approved,
        clock=lambda: 100.0,
        utc_clock=lambda: datetime(2026, 9, 17, tzinfo=UTC),
    )
    worker, reader = InMemorySpendAdmissionWorker(state), InMemorySpendAdmissionReader(state)
    reservation = _run(worker.reserve(intent))
    assert reservation is not None
    dispatch = _run(worker.dispatch(reservation, intent.allocations[0]))
    report = _report(counts, bound=bound, dispatch=dispatch)
    finality = _finality(report).finalize(report.request)
    outcome = finality.settlement() if finality is not None else SpendSettlement(dispatch, None)
    if finality is not None:
        approved.append(outcome)
    before = tuple(_run(reader.budget(limit.scope, policy_epoch=7)) for limit in intent.limits)
    assert all(b.held_micros == 2 * bound.bound_micros and b.settled_micros == 0 for b in before)
    receipt = _run(worker.settle(outcome))
    assert _run(worker.settle(outcome)) == receipt
    journal = _run(worker.close(reservation))
    assert _run(worker.close(reservation)) == journal
    expected_state = SpendAttemptState.UNKNOWN if counts is None else SpendAttemptState.SETTLED
    assert tuple(slot.state for slot in journal.attempts) == (
        expected_state,
        SpendAttemptState.CLOSED_UNUSED,
    )
    after = tuple(_run(reader.budget(limit.scope, policy_epoch=7)) for limit in intent.limits)
    assert all(
        b.settled_micros == (outcome.estimated_micros or 0)
        and b.held_micros == (bound.bound_micros if counts is None else 0)
        for b in after
    )
    if counts is None:
        late = SpendSettlement(dispatch, 0, "late-usage-private")
        approved.append(late)
        with pytest.raises(SpendControlError):
            _run(worker.settle(late))
        assert (
            tuple(_run(reader.budget(limit.scope, policy_epoch=7)) for limit in intent.limits)
            == after
        )
    if finality is not None and finality.cost_bound_exceeded:
        assert receipt.bound_exceeded
        with pytest.raises(SpendControlError):
            _run(worker.reserve(_intent(bound, index=1)))
