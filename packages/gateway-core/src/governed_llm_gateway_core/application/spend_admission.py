"""Private ADR-0021 consumer-owned ports, without backend or serving integration.

Atomicity, trusted attribution/bounds/issuance, complete plan/policy coverage, clock,
durability, control idempotency and dispatch ownership are adapter/caller obligations,
not guarantees supplied by Protocols. Infrastructure failures cannot become permission
to infer, replay, release unknown exposure, or fall back to permissive local state.
"""

from enum import StrEnum
from typing import Protocol

from governed_llm_gateway_core.domain.spend_admission import (
    SpendAdmissionContractError,
    SpendAttemptAllocation,
    SpendBudgetScope,
    SpendBudgetSnapshot,
    SpendDispatchReceipt,
    SpendJournalSnapshot,
    SpendReservation,
    SpendReservationRequest,
    SpendSettlement,
    SpendSettlementReceipt,
)


class SpendControlErrorCode(StrEnum):
    """Allowlisted budget-control failures, not transient provider classifications."""

    UNAVAILABLE = "unavailable"
    INVALID_STATE = "invalid_state"
    CONFLICT = "conflict"
    EXPIRED = "expired"


class SpendControlError(RuntimeError):
    """Sanitized failure with no backend message, private receipt or payload."""

    def __init__(self, code: SpendControlErrorCode) -> None:
        """Retain only an explicitly closed error category."""
        if not isinstance(code, SpendControlErrorCode):
            raise SpendAdmissionContractError("spend control failure needs a closed category")
        self.code = code
        super().__init__("spend admission control failed")


class SpendReservationReadPort(Protocol):
    """Known-state reads for inspection; cannot admit, acquire, renew or dispatch."""

    async def budget(self, scope: SpendBudgetScope, *, policy_epoch: int) -> SpendBudgetSnapshot:
        """Read initialized authoritative state at the exact policy fence.

        Unknown/missing known buckets or invalid/unavailable state raise SpendControlError,
        never a zero/default balance. A projection predicate grants no reservation.
        """
        ...

    async def journal(self, reservation: SpendReservation) -> SpendJournalSnapshot:
        """Read the complete exact journal without acquiring execution rights.

        Verify receipt issuance/binding; missing/lost/corrupt state fails closed.
        Expired owner lifetime cannot erase held or settled exposure.
        """
        ...


class SpendReservationPort(SpendReservationReadPort, Protocol):
    """Owned worker transitions; no policy publishing/reset or recovery-owner capability."""

    async def reserve(self, request: SpendReservationRequest) -> SpendReservation | None:
        """Admit every applicable scope plus complete journal/fence, or mutate none.

        Independently verify complete trusted policy/plan/pricing/bound metadata, not caller
        ceilings or a self-issued receipt. Frozen admitted_on must match authoritative UTC
        time for first admission. Require S+H<L and S+H+R<=L everywhere. Exact same execution/
        owner/intent retries resolve their original result without renewing the lease or
        reattributing windows; changed bindings/conflicting IDs raise a control error.
        None means authoritative insufficient capacity, not an unavailable/unknown backend.
        Control timeout is ambiguous: reconcile exact journal, never dispatch optimistically.
        """
        ...

    async def is_current(self, reservation: SpendReservation) -> bool:
        """Check trusted issuance, current owner/fences/lease without reacquiring capacity.

        False denies new dispatch; it does not release possibly executed allocations.
        """
        ...

    async def dispatch(
        self, reservation: SpendReservation, allocation: SpendAttemptAllocation
    ) -> SpendDispatchReceipt:
        """Atomically claim this exact reserved slot as MAY_HAVE_EXECUTED before provider I/O.

        Reject expired/stale/conflicting/closed owners. Exact control retries resolve the
        same fence but cannot permit a second dispatch; caller owns one actual opening.
        Recovery never reopens a possibly dispatched slot. Existing authorization,
        preflight, health and no-replay rules remain independent prerequisites.
        """
        ...

    async def settle(self, settlement: SpendSettlement) -> SpendSettlementReceipt:
        """Persist the exact owned outcome atomically in all original buckets and journal.

        Trusted complete usage transfers allocation H to estimate S; unknown usage keeps H.
        Exact duplicates return the same receipt without double accounting; conflicts or
        stale owners fail without mutation. A cost above its bound is retained truthfully
        and suspends affected-model admissions, never clamped. Ambiguous acknowledgement
        requires journal reconciliation, not compensating release or inference replay.
        Future executors require validated acknowledgement before terminal success.
        """
        ...

    async def close(self, reservation: SpendReservation) -> SpendJournalSnapshot:
        """Atomically fence dispatch and close all slots, idempotently under the exact owner.

        Release only slots whose journal proves no dispatch claim; convert possibly executed
        unresolved slots to UNKNOWN with their holds intact. Settled amounts stay retained.
        Return complete closed coverage and its closure fence, not a blanket release receipt.
        Cancelled/failed cleanup cannot default to zero or undo another owner. Caller lifecycle
        includes failed HTTP construction and an execution iterator never consumed; recovery
        ownership, retention/pruning and policy publication require separate capabilities.
        """
        ...
