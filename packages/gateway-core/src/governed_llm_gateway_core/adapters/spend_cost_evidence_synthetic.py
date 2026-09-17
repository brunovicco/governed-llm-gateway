"""Finite read-only synthetic cost evidence; never a verified provider capability.

Fixtures independently register canonical preparations, dispatches and inspected reports.
They test correlation only: no tokenizer, native payload, provider finality, configuration
loader, evidence authentication, admission authority, persistence or serving integration.
The synthetic-only API family deliberately rejects real provider families.
"""

from dataclasses import dataclass, field, replace
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
from governed_llm_gateway_core.domain.spend_cost_evidence import (
    SpendPreparedTextBinding,
    SpendTextCostBound,
    SpendTextCostModel,
    SpendTextUsageFinality,
    SpendUsageFinalityRequest,
)

_FAMILY = "synthetic_text_v1"


def _check(condition: bool) -> None:
    if not condition:
        raise SpendAdmissionContractError("synthetic spend evidence needs consistent fixtures")


def _bound(value: SpendTextCostBound, *, synthetic_only: bool = True) -> None:
    _check(type(value) is SpendTextCostBound)
    _check(type(value.binding) is SpendPreparedTextBinding)
    _check(type(value.model) is SpendTextCostModel)
    replace(value.binding)
    replace(value.model)
    replace(value)
    if synthetic_only:
        _check(value.binding.api_family == _FAMILY)


def _bounds(values: tuple[SpendTextCostBound, ...]) -> None:
    _check(type(values) is tuple and bool(values))
    for value in values:
        _bound(value)
    _check(len({b.binding.prepared_request_id for b in values}) == len(values))
    _check(len({b.bound_evidence_id for b in values}) == len(values))
    prices: dict[str, SpendTextCostModel] = {}
    for value in values:
        prior = prices.setdefault(value.model.pricing_digest, value.model)
        _check(prior == value.model)


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
        replace(limit)
        replace(limit.scope)
    for allocation in intent.allocations:
        _check(type(allocation) is SpendAttemptAllocation)
        replace(allocation)
    replace(value.allocation)
    replace(intent)
    replace(value.reservation)
    replace(value)


@dataclass(frozen=True, slots=True)
class SyntheticSpendPreparedText:
    """Private retained canonical text fixture, NOT a native request or tokenization proof."""

    request: ProviderRequest = field(repr=False)
    bound: SpendTextCostBound = field(repr=False)

    def __post_init__(self) -> None:
        """Accept only exact immutable text representations and the synthetic family."""
        _bound(self.bound)
        request = self.request
        _check(type(request) is ProviderRequest)
        _check(type(request.model) is str and bool(request.model))
        _check(request.model.strip() == request.model)
        _check(type(request.max_output_tokens) is int)
        _check(request.max_output_tokens == self.bound.binding.max_output_tokens)
        _check(type(request.timeout_seconds) in (int, float))
        try:
            finite_timeout = isfinite(request.timeout_seconds) and request.timeout_seconds > 0
        except OverflowError:
            finite_timeout = False
        _check(finite_timeout)
        _check(request.structured_output is None and type(request.tools) is tuple)
        _check(not request.tools and request.parallel_tool_calling is False)
        _check(type(request.messages) is tuple and bool(request.messages))
        for message in request.messages:
            _check(type(message) is Message)
            _check(
                type(message.role) is MessageRole
                and message.role in {MessageRole.SYSTEM, MessageRole.USER, MessageRole.ASSISTANT}
            )
            _check(type(message.content) is str and type(message.images) is tuple)
            _check(not message.images and type(message.blocks) is tuple)
            if message.blocks:
                _check(not message.content)
                for block in message.blocks:
                    if not isinstance(block, TextBlock):
                        raise SpendAdmissionContractError(
                            "synthetic spend evidence needs consistent fixtures"
                        )
                    _check(
                        type(block) is TextBlock and type(block.text) is str and bool(block.text)
                    )
            else:
                _check(bool(message.content))


@dataclass(frozen=True, slots=True)
class SyntheticSpendCostBounds:
    """Read-only finite fixture lookup; structurally matches the port only for synthetic tests."""

    preparations: tuple[SyntheticSpendPreparedText, ...] = field(repr=False)

    def __post_init__(self) -> None:
        """Freeze independent fixtures; no caller-supplied preparation is registered by lookup."""
        _check(type(self.preparations) is tuple and bool(self.preparations))
        for preparation in self.preparations:
            _check(type(preparation) is SyntheticSpendPreparedText)
            replace(preparation)
        _bounds(tuple(preparation.bound for preparation in self.preparations))

    def bound(self, binding: SpendPreparedTextBinding) -> SpendTextCostBound:
        """Resolve exact retained facts, without issuing execution permission or new evidence."""
        if type(binding) is not SpendPreparedTextBinding:
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
        if preparation.bound.binding != binding:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.CONFLICT)
        return preparation.bound


@dataclass(frozen=True, slots=True)
class SyntheticSpendUsageReport:
    """Explicit inspected source: None is incomplete, never a missing-report default."""

    request: SpendUsageFinalityRequest = field(repr=False)
    finality: SpendTextUsageFinality | None = field(repr=False)

    def __post_init__(self) -> None:
        """Require exact correlation and explicit complete counts or explicit unknown."""
        _check(type(self.request) is SpendUsageFinalityRequest)
        _bound(self.request.bound)
        _dispatch(self.request.dispatch)
        replace(self.request)
        if self.finality is not None:
            _check(type(self.finality) is SpendTextUsageFinality)
            _check(type(self.finality.request) is SpendUsageFinalityRequest)
            _check(self.finality.request == self.request)
            replace(self.finality)


@dataclass(frozen=True, slots=True)
class SyntheticSpendUsageFinality:
    """Read-only independent bound/dispatch/report inventory, NOT provider finality proof."""

    issued_bounds: tuple[SpendTextCostBound, ...] = field(repr=False)
    approved_dispatches: tuple[SpendDispatchReceipt, ...] = field(repr=False)
    reports: tuple[SyntheticSpendUsageReport, ...] = field(repr=False)

    def __post_init__(self) -> None:
        """Refuse ambiguous identities, unregistered facts or replacement reports at bootstrap."""
        _bounds(self.issued_bounds)
        _check(type(self.approved_dispatches) is tuple and type(self.reports) is tuple)
        for dispatch in self.approved_dispatches:
            _dispatch(dispatch)
            candidates = tuple(
                b
                for b in self.issued_bounds
                if b.bound_evidence_id == dispatch.allocation.bound_evidence_id
            )
            _check(len(candidates) == 1)
            SpendUsageFinalityRequest(candidates[0], dispatch, "synthetic-validation")
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
            _check(type(report) is SyntheticSpendUsageReport)
            replace(report)
            _check(report.request.bound in self.issued_bounds)
            _check(report.request.dispatch in self.approved_dispatches)
        _check(len({r.request.usage_report_id for r in self.reports}) == len(self.reports))
        _check(len({r.request.dispatch for r in self.reports}) == len(self.reports))
        known = tuple(r.finality for r in self.reports if r.finality is not None)
        _check(len({f.usage_evidence_id for f in known}) == len(known))

    def finalize(self, request: SpendUsageFinalityRequest) -> SpendTextUsageFinality | None:
        """Read the exact registered source; missing/foreign/conflicting evidence raises."""
        if type(request) is not SpendUsageFinalityRequest:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.INVALID_STATE)
        try:
            _bound(request.bound, synthetic_only=False)
            _dispatch(request.dispatch)
            replace(request)
            self.__post_init__()
        except SpendAdmissionContractError:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.INVALID_STATE) from None
        if request.bound.binding.api_family != _FAMILY:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.UNSUPPORTED)
        bound = next(
            (
                b
                for b in self.issued_bounds
                if b.bound_evidence_id == request.bound.bound_evidence_id
            ),
            None,
        )
        if bound is None:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.UNAVAILABLE)
        dispatch = next(
            (
                d
                for d in self.approved_dispatches
                if d.dispatch_fence == request.dispatch.dispatch_fence
            ),
            None,
        )
        if dispatch is None:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.UNAVAILABLE)
        if bound != request.bound or dispatch != request.dispatch:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.CONFLICT)
        report = next(
            (r for r in self.reports if r.request.usage_report_id == request.usage_report_id), None
        )
        if report is None:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.UNAVAILABLE)
        if report.request != request:
            raise SpendCostEvidenceError(SpendCostEvidenceErrorCode.CONFLICT)
        return report.finality
