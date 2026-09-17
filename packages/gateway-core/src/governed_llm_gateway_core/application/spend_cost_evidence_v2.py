"""Private pure v2 evidence lookup contracts; no implementation or serving hook."""

from typing import Protocol

from governed_llm_gateway_core.domain.spend_cost_evidence_v2 import (
    SpendCacheCostBound,
    SpendCachePreparedBinding,
    SpendCacheUsageFinality,
    SpendCacheUsageFinalityRequest,
)


class SpendCacheCostBoundPort(Protocol):
    """Pure lookup of independently issued native bounds, never remote acquisition."""

    def bound(self, binding: SpendCachePreparedBinding) -> SpendCacheCostBound:
        """Resolve exact retained preparation and independently validate source authority.

        Verify exact native bytes/model/options/endpoint/configuration/profile and
        original plan/policy/registry/retry provenance against trusted issued facts.
        Qualify complete category partition, both whole-request bands, verified input
        expansion and enforceable inclusive output. Require unchanged qualified prices,
        fixed validity and current nonrevoked epoch under a trusted fresh control snapshot.
        No constructor, parser observation, public ID/digest or Boolean flag qualifies
        a source. Return binding must equal the supplied one; callers also check it.
        Closed sanitized SpendCostEvidenceError rejects missing/foreign/expired/changed/
        unsupported facts. No implicit zero or legacy fallback. No provider/storage I/O,
        registration, refresh, clock acquisition, authorization, reservation or dispatch.
        """
        ...


class SpendCacheUsageFinalityPort(Protocol):
    """Pure exact-attempt finality validation over independently retained native sources."""

    def finalize(self, request: SpendCacheUsageFinalityRequest) -> SpendCacheUsageFinality | None:
        """Verify original bound/schedule and exact claimed execution/owner/slot/fences.

        Independently verify report issuance, native mandatory categories/total/reasoning,
        actual model/profile and qualified complete usage/lifecycle semantics. Normalized
        usage, terminal names, status, EOF or cancellation are not complete-zero evidence.
        None is only an independently inspected supported but incomplete source; retain
        its full hold. Missing/foreign/corrupt/unqualified/conflicting sources raise closed
        sanitized SpendCostEvidenceError, never zero. Preserve original prices/holds after
        drift/expiry; do not revive evidence or accept late reconciliation without its own
        reviewed fence. Return request must equal the supplied request. Keep truthful excess
        and token/cost flags even at zero price; consumers must invalidate violated models
        before new admissions/claims. No generic projection may silently discard these flags.
        No I/O, clock acquisition, registration, recovery, journal ack, release or replay.
        """
        ...
