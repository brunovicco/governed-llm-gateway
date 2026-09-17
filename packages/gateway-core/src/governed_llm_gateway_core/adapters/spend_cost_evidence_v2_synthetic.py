"""Finite synthetic-only v2 lookups; no trusted native evidence or serving hook.

Immutable canonical text, schedules, dispatches and explicit reports are supplied at
test bootstrap. Control time/models are explicit fixture snapshots, not a live clock,
configuration loader or revocation authority. Construction/equality is not authentication.
"""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from math import isfinite

from governed_llm_gateway_contracts import Message, MessageRole, TextBlock

from governed_llm_gateway_core.application.provider import ProviderRequest
from governed_llm_gateway_core.application.spend_cost_evidence import (
    SpendCostEvidenceError,
    SpendCostEvidenceErrorCode,
)
from governed_llm_gateway_core.domain.spend_admission import (
    SpendAdmissionContractError,
    SpendAttemptAllocation,
    SpendBudgetLimit,
    SpendBudgetScope,
    SpendDispatchReceipt,
    SpendReservation,
    SpendReservationRequest,
)
from governed_llm_gateway_core.domain.spend_cost_evidence_v2 import (
    SpendCacheCostBound,
    SpendCacheCostModel,
    SpendCachePreparedBinding,
    SpendCacheRates,
    SpendCacheUsageFinality,
    SpendCacheUsageFinalityRequest,
)

_FAMILY = "synthetic-text-v2"


def _check(condition: bool) -> None:
    if not condition:
        raise SpendAdmissionContractError("synthetic cache evidence needs consistent fixtures")


def _model_key(value: SpendCacheCostModel) -> tuple[str, str, str]:
    return value.api_family, value.model_id, value.pricing_profile_id


def _model(value: SpendCacheCostModel) -> None:
    _check(type(value) is SpendCacheCostModel)
    for band in (value.short_context, value.long_context):
        _check(type(band) is SpendCacheRates)
        replace(band)
    replace(value)


def _models(values: tuple[SpendCacheCostModel, ...]) -> None:
    _check(type(values) is tuple)
    identities: dict[tuple[str, str, str], SpendCacheCostModel] = {}
    prices: dict[str, SpendCacheCostModel] = {}
    for value in values:
        _model(value)
        _check(value.api_family == _FAMILY)
        _check(identities.setdefault(_model_key(value), value) == value)
        _check(prices.setdefault(value.pricing_digest, value) == value)


def _bound(value: SpendCacheCostBound, *, synthetic_only: bool = True) -> None:
    _check(type(value) is SpendCacheCostBound)
    _check(type(value.binding) is SpendCachePreparedBinding)
    replace(value.binding)
    _model(value.model)
    replace(value)
    if synthetic_only:
        _check(value.binding.api_family == _FAMILY)


def _bounds(values: tuple[SpendCacheCostBound, ...]) -> None:
    _check(type(values) is tuple and bool(values))
    for value in values:
        _bound(value)
    _check(len({v.binding.prepared_request_id for v in values}) == len(values))
    _check(len({v.bound_evidence_id for v in values}) == len(values))
    _models(tuple(v.model for v in values))


def _dispatch(value: SpendDispatchReceipt) -> None:
    _check(type(value) is SpendDispatchReceipt)
    _check(type(value.reservation) is SpendReservation)
    _check(type(value.reservation.request) is SpendReservationRequest)
    _check(type(value.allocation) is SpendAttemptAllocation)
    intent = value.reservation.request
    _check(type(intent.limits) is tuple and bool(intent.limits))
    _check(type(intent.allocations) is tuple and bool(intent.allocations))
    for limit in intent.limits:
        _check(type(limit) is SpendBudgetLimit and type(limit.scope) is SpendBudgetScope)
        replace(limit.scope)
        replace(limit)
    for allocation in intent.allocations:
        _check(type(allocation) is SpendAttemptAllocation)
        replace(allocation)
    replace(value.allocation)
    replace(intent)
    replace(value.reservation)
    replace(value)


def _request(value: SpendCacheUsageFinalityRequest, *, synthetic_only: bool = True) -> None:
    _check(type(value) is SpendCacheUsageFinalityRequest)
    _bound(value.bound, synthetic_only=synthetic_only)
    _dispatch(value.dispatch)
    replace(value)


@dataclass(frozen=True, slots=True)
class SyntheticSpendCachePreparation:
    """Retained canonical text fixture, NOT native bytes or input-token proof."""

    request: ProviderRequest = field(repr=False)
    bound: SpendCacheCostBound = field(repr=False)

    def __post_init__(self) -> None:
        """Require an exact immutable text subset, matching fixture model/output cap."""
        _bound(self.bound)
        request = self.request
        _check(type(request) is ProviderRequest)
        _check(type(request.model) is str and request.model == self.bound.binding.model_id)
        _check(type(request.max_output_tokens) is int)
        _check(request.max_output_tokens == self.bound.binding.max_output_tokens)
        _check(type(request.timeout_seconds) in (int, float))
        try:
            timeout_ok = isfinite(request.timeout_seconds) and request.timeout_seconds > 0
        except OverflowError:
            timeout_ok = False
        _check(timeout_ok)
        _check(request.structured_output is None)
        _check(type(request.tools) is tuple and not request.tools)
        _check(request.parallel_tool_calling is False)
        _check(type(request.messages) is tuple and bool(request.messages))
        for message in request.messages:
            _check(type(message) is Message)
            _check(
                type(message.role) is MessageRole
                and message.role in {MessageRole.SYSTEM, MessageRole.USER, MessageRole.ASSISTANT}
            )
            _check(type(message.content) is str)
            _check(type(message.images) is tuple and not message.images)
            _check(type(message.blocks) is tuple)
            if message.blocks:
                _check(not message.content)
                for block in message.blocks:
                    if not isinstance(block, TextBlock):
                        raise SpendAdmissionContractError(
                            "synthetic cache evidence needs consistent fixtures"
                        )
                    _check(type(block) is TextBlock)
                    _check(type(block.text) is str and bool(block.text))
            else:
                _check(bool(message.content))


@dataclass(frozen=True, slots=True)
class SyntheticSpendCacheControlSnapshot:
    """Explicit fixture time and retained current models; NOT trusted live control."""

    observed_at: datetime = field(repr=False)
    models: tuple[SpendCacheCostModel, ...] = field(repr=False)

    def __post_init__(self) -> None:
        """Freeze canonical UTC and unambiguous fixture versions; empty means unavailable."""
        _check(type(self.observed_at) is datetime and self.observed_at.tzinfo is UTC)
        _models(self.models)
        _check(len({_model_key(v) for v in self.models}) == len(self.models))


@dataclass(frozen=True, slots=True)
class SyntheticSpendCacheBounds:
    """Read-only finite bound lookup under one declared synthetic control snapshot."""

    preparations: tuple[SyntheticSpendCachePreparation, ...] = field(repr=False)
    control: SyntheticSpendCacheControlSnapshot = field(repr=False)

    def __post_init__(self) -> None:
        """Register finite independent fixtures only at construction, never by lookup."""
        _check(type(self.preparations) is tuple and bool(self.preparations))
        for preparation in self.preparations:
            _check(type(preparation) is SyntheticSpendCachePreparation)
            replace(preparation)
        _bounds(tuple(p.bound for p in self.preparations))
        _check(type(self.control) is SyntheticSpendCacheControlSnapshot)
        replace(self.control)

    def bound(self, binding: SpendCachePreparedBinding) -> SpendCacheCostBound:
        """Read registered facts without renewal, issuance, I/O or dispatch permission."""
        if type(binding) is not SpendCachePreparedBinding:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.INVALID_STATE)
        try:
            replace(binding)
            self.__post_init__()
        except SpendAdmissionContractError:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.INVALID_STATE) from None
        if binding.api_family != _FAMILY:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.UNSUPPORTED)
        preparation = next(
            (
                p
                for p in self.preparations
                if p.bound.binding.prepared_request_id == binding.prepared_request_id
            ),
            None,
        )
        if preparation is None:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.UNAVAILABLE)
        value = preparation.bound
        if value.binding != binding:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.CONFLICT)
        current = next(
            (m for m in self.control.models if _model_key(m) == _model_key(value.model)), None
        )
        if current is None:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.UNAVAILABLE)
        if current != value.model:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.CONFLICT)
        if not value.valid_from <= self.control.observed_at < value.valid_until:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.UNAVAILABLE)
        return value


@dataclass(frozen=True, slots=True)
class SyntheticSpendCacheUsageReport:
    """Explicit fixture source: None is inspected incomplete, not an absent-report default."""

    request: SpendCacheUsageFinalityRequest = field(repr=False)
    finality: SpendCacheUsageFinality | None = field(repr=False)

    def __post_init__(self) -> None:
        """Validate the full original bound/dispatch and any complete explicit counters."""
        _request(self.request)
        if self.finality is not None:
            _check(type(self.finality) is SpendCacheUsageFinality)
            _request(self.finality.request)
            _check(self.finality.request == self.request)
            replace(self.finality)


@dataclass(frozen=True, slots=True)
class SyntheticSpendCacheFinality:
    """Original fixture bound/dispatch/report lookup; no journal, suspension or release."""

    issued_bounds: tuple[SpendCacheCostBound, ...] = field(repr=False)
    approved_dispatches: tuple[SpendDispatchReceipt, ...] = field(repr=False)
    reports: tuple[SyntheticSpendCacheUsageReport, ...] = field(repr=False)

    def __post_init__(self) -> None:
        """Refuse ambiguous versions, owners, slots and complete/incomplete fixture sources."""
        _bounds(self.issued_bounds)
        _check(type(self.approved_dispatches) is tuple and type(self.reports) is tuple)
        owners: dict[str, SpendReservation] = {}
        for dispatch in self.approved_dispatches:
            _dispatch(dispatch)
            candidates = tuple(
                b
                for b in self.issued_bounds
                if b.bound_evidence_id == dispatch.allocation.bound_evidence_id
            )
            _check(len(candidates) == 1)
            SpendCacheUsageFinalityRequest(candidates[0], dispatch, "synthetic-validation")
            _check(
                owners.setdefault(dispatch.reservation.request.execution_id, dispatch.reservation)
                == dispatch.reservation
            )
        _check(
            len({d.dispatch_fence for d in self.approved_dispatches})
            == len(self.approved_dispatches)
        )
        slots = tuple(
            (
                d.reservation.request.execution_id,
                d.allocation.fallback_index,
                d.allocation.attempt_number,
            )
            for d in self.approved_dispatches
        )
        _check(len(set(slots)) == len(slots))
        for report in self.reports:
            _check(type(report) is SyntheticSpendCacheUsageReport)
            replace(report)
            _check(report.request.bound in self.issued_bounds)
            _check(report.request.dispatch in self.approved_dispatches)
        _check(len({r.request.usage_report_id for r in self.reports}) == len(self.reports))
        _check(len({r.request.dispatch for r in self.reports}) == len(self.reports))
        known = tuple(r.finality for r in self.reports if r.finality is not None)
        _check(len({f.usage_evidence_id for f in known}) == len(known))

    def finalize(self, request: SpendCacheUsageFinalityRequest) -> SpendCacheUsageFinality | None:
        """Return the original explicit source; no repricing, expiry release or reconciliation."""
        if type(request) is not SpendCacheUsageFinalityRequest:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.INVALID_STATE)
        try:
            _request(request, synthetic_only=False)
            self.__post_init__()
        except SpendAdmissionContractError:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.INVALID_STATE) from None
        if request.bound.binding.api_family != _FAMILY:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.UNSUPPORTED)
        value = next(
            (
                b
                for b in self.issued_bounds
                if b.bound_evidence_id == request.bound.bound_evidence_id
            ),
            None,
        )
        dispatch = next(
            (
                d
                for d in self.approved_dispatches
                if d.dispatch_fence == request.dispatch.dispatch_fence
            ),
            None,
        )
        if value is None or dispatch is None:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.UNAVAILABLE)
        if value != request.bound or dispatch != request.dispatch:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.CONFLICT)
        report = next(
            (r for r in self.reports if r.request.usage_report_id == request.usage_report_id), None
        )
        if report is None:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.UNAVAILABLE)
        if report.request != request:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.CONFLICT)
        return report.finality
