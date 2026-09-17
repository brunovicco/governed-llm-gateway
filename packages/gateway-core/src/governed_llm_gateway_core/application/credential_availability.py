"""Consumer-owned ADR-0019 ports, with no serving integration.

Atomicity, trusted publication, durable material tombstones, and worker permissions
are adapter obligations, not guarantees supplied by a Protocol or value constructor.
Infrastructure failures must raise sanitized errors, never permissive local defaults.
"""

from enum import StrEnum
from typing import Protocol

from governed_llm_gateway_core.domain.credential_availability import (
    CredentialAdmission,
    CredentialAvailabilitySnapshot,
    CredentialBindingRejection,
    CredentialCompletionReceipt,
    CredentialContractError,
    CredentialGeneration,
    CredentialGenerationPublication,
)


class CredentialAvailabilityErrorCode(StrEnum):
    """Closed control failures, distinct from transient provider errors."""

    UNAVAILABLE = "unavailable"
    INVALID_STATE = "invalid_state"


class CredentialAvailabilityError(RuntimeError):
    """Sanitized fail-closed control failure; carries no backend message or token."""

    def __init__(self, code: CredentialAvailabilityErrorCode) -> None:
        """Retain only an allowlisted failure category."""
        if not isinstance(code, CredentialAvailabilityErrorCode):
            raise CredentialContractError("credential control failure needs a closed category")
        self.code = code
        super().__init__("credential availability control failed")


class CredentialAvailabilityReadPort(Protocol):
    """Read projection for narrowing only; cannot claim an owner or publish a token."""

    async def snapshot(self, binding_id: str) -> CredentialAvailabilitySnapshot:
        """Read validated state without claiming/renewing validation ownership.

        Missing authoritative evidence is UNKNOWN/deny. Corrupt/unavailable control
        raises CredentialAvailabilityError; no AVAILABLE default or local fallback.
        """
        ...


class CredentialAvailabilityPort(CredentialAvailabilityReadPort, Protocol):
    """Worker observations and attempt admission, with no generation publication right."""

    async def admit(
        self, generation: CredentialGeneration, *, attempt_id: str
    ) -> CredentialAdmission | None:
        """Atomically admit this exact active token, never a newer local substitute.

        AVAILABLE admits ordinary concurrent attempts. PENDING_VALIDATION claims
        one configured finite lease and enters VALIDATING. Only its same live owner
        can recheck; the returned remaining lifetime cannot renew that lease. Unknown,
        quarantined, mismatched, or another owner's token has no admission.
        """
        ...

    async def is_admitted(self, admission: CredentialAdmission) -> bool:
        """Check current token/material state and owner/fence/expiry without reacquiring.

        Retired/released/expired owners and quarantined or rotated material fail.
        """
        ...

    async def release(self, admission: CredentialAdmission) -> None:
        """Idempotently release only this matching validation owner in finally.

        Ordinary admission, retired handles, and cancellation cannot clear history
        or quarantine, prove recovery, or release a replacement's owner.
        """
        ...

    async def complete_validation(
        self, admission: CredentialAdmission
    ) -> CredentialCompletionReceipt | None:
        """Accept complete locally validated provider success from the live owner only.

        Atomically promote and issue a fenced receipt before retiring ownership.
        Ordinary AVAILABLE success cannot promote or undo quarantine. Unaccepted
        retired/expired or rotated validation returns no receipt. An accepted duplicate
        may return its same receipt only while that token/completion remains current;
        it cannot create a new activation or erase material history.
        """
        ...

    async def is_completion_current(self, receipt: CredentialCompletionReceipt) -> bool:
        """Validate store-issued completion, current AVAILABLE token, and quarantine.

        This checks the completed receipt, not the already-retired owner's lease.
        Receipt construction/correlation is not proof of trusted issuance or liveness.
        """
        ...

    async def record_rejection(self, rejection: CredentialBindingRejection) -> None:
        """Idempotently quarantine the observed binding/material, including retired tokens.

        Retain tombstones for all activatable versions. A different newer material
        is unaffected; reactivation of the same rejected material must be blocked
        even under a new epoch/alias. Failure to persist raises a sanitized control
        error; caller reconciliation/local deny is required, not best-effort telemetry.
        """
        ...


class CredentialGenerationPublisher(Protocol):
    """Trusted controller-only capability, separately permissioned from workers."""

    async def publish(self, publication: CredentialGenerationPublication) -> bool:
        """CAS the complete expected token and activate only authority-verified metadata.

        New material starts PENDING_VALIDATION, never immediately AVAILABLE. Material
        tombstones survive publication, restart, relabeling, and rollback. A matching
        already-published intent is idempotent; conflicting current tokens return false.
        expected_generation=None means first authoritative activation, not permission
        to reset missing/corrupt/lost state; reconcile known history first or fail closed.
        The adapter must preserve exact bounded-integer epochs without numeric rounding.
        """
        ...
