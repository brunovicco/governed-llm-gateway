"""Private no-I/O cost-bound/finality capability contracts, not serving integration."""

from enum import StrEnum
from typing import Protocol

from governed_llm_gateway_core.domain.spend_admission import SpendAdmissionContractError
from governed_llm_gateway_core.domain.spend_cost_evidence import (
    SpendPreparedTextBinding,
    SpendTextCostBound,
    SpendTextUsageFinality,
    SpendUsageFinalityRequest,
)


class SpendCostEvidenceErrorCode(StrEnum):
    """Cost capability failures never become provider-transient failures or permission."""

    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"
    INVALID_STATE = "invalid_state"
    CONFLICT = "conflict"


class SpendCostEvidenceError(RuntimeError):
    """Closed category only; no report, native preparation, price or raw provider error."""

    def __init__(self, code: SpendCostEvidenceErrorCode) -> None:
        """Reject arbitrary classifications without echoing their contents."""
        if type(code) is not SpendCostEvidenceErrorCode:
            raise SpendAdmissionContractError("spend cost failure needs a closed category")
        self.code = code
        super().__init__("spend cost evidence failed")


class SpendCostBoundPort(Protocol):
    """Synchronous pure preparation capability; cannot acquire budget or call a provider."""

    def bound(self, binding: SpendPreparedTextBinding) -> SpendTextCostBound:
        """Resolve trusted retained preparation and return its exact independently issued bound.

        Validate handle issuance, unchanged native payload/model/API/configuration and all
        provenance against trusted versioned configuration, never caller declarations alone.
        Verify all input expansion/tokenization, enforceable total charged output limit,
        pinned pricing and finality contract for explicitly reviewed API/model combinations.
        The text-only two-rate shape excludes schemas/tools/tool results, media, reasoning,
        cache tiers, server tools, flat fees and any other charged dimension. Naming a family
        or shape approves nothing. Unknown/missing/unsupported dimensions, pricing or evidence
        raise sanitized SpendCostEvidenceError; do not pad projections or return a zero bound.
        Return binding must equal the exact supplied binding; future caller verifies it too.
        No provider/storage/remote-tokenizer I/O, authorization, plan expansion or reservation.
        """
        ...


class SpendUsageFinalityPort(Protocol):
    """Synchronous no-I/O validation over privately retained exact-attempt usage facts."""

    def finalize(self, request: SpendUsageFinalityRequest) -> SpendTextUsageFinality | None:
        """Independently validate receipt/report issuance and finality under the pinned model.

        Correlate actual retained report to execution/owner/slot/dispatch fence, preparation,
        bound and its exact usage-contract/estimator/pricing versions. Constructors/equality,
        normalized usage defaults, public final usage, HTTP status, EOF, cancellation and
        absence of output do not establish complete usage or measured zero. Failed/partial
        attempts may have valid final counts only with separately proven provider finality.
        None means an inspected supported source cannot establish complete final usage;
        keep the whole hold as unknown. Missing/corrupt/foreign handles, configuration/adapter
        outage, unsupported dimensions or conflicting reports raise sanitized errors, not
        measured zero, silent fallback or a successful terminal response. Measured zero is
        an explicit complete value. Return request must equal the supplied request.
        Preserve truthful token/cost excess and signal violated models even for free pricing;
        overflow fails closed and requires reconciliation. No journal acknowledgement, late
        unknown-to-known recovery, hold release, inference replay, provider I/O or logging.
        """
        ...
