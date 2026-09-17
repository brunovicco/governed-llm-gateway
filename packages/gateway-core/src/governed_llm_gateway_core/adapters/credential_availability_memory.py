"""Process-local ADR-0019 reference adapter, deliberately absent from serving.

Inputs represent trusted synthetic controller/worker facts, not proof of authority.
Retained state has no TTL, persistence, recovery, secret reads, or provider execution.
Separate wrapper capabilities are not authentication or an ACL security boundary.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from math import isfinite
from threading import Lock
from time import monotonic
from uuid import UUID, uuid4

from governed_llm_gateway_core.application.credential_availability import (
    CredentialAvailabilityError,
    CredentialAvailabilityErrorCode,
)
from governed_llm_gateway_core.domain.credential_availability import (
    CredentialAdmission,
    CredentialAvailabilitySnapshot,
    CredentialAvailabilityState,
    CredentialBindingRejection,
    CredentialCompletionReceipt,
    CredentialContractError,
    CredentialGeneration,
    CredentialGenerationPublication,
)


@dataclass(frozen=True, slots=True, repr=False)
class _ValidationOwner:
    admission: CredentialAdmission
    expires_at: float


@dataclass(frozen=True, slots=True, repr=False)
class _BindingRecord:
    generation: CredentialGeneration
    publication: CredentialGenerationPublication
    state: CredentialAvailabilityState
    owner: _ValidationOwner | None = None
    receipt: CredentialCompletionReceipt | None = None


class InMemoryCredentialAvailabilityState:
    """Explicit shared object for same-process reference clients, not a durable authority.

    A fresh object is for previously unseen synthetic bindings only. Recreating it
    loses history; it cannot safely reconcile/restore real activatable credentials.
    Clock callbacks must be synchronous, side-effect-free, and non-reentrant.
    """

    def __init__(
        self, *, validation_lease_seconds: float, clock: Callable[[], float] = monotonic
    ) -> None:
        """Configure a finite non-renewing lease without creating any active generation."""
        if not _finite_number(validation_lease_seconds) or validation_lease_seconds <= 0:
            raise CredentialContractError("credential lease must be finite and positive")
        if not callable(clock):
            raise CredentialContractError("credential clock must be callable")
        self._lease_seconds = float(validation_lease_seconds)
        self._clock = clock
        self._last_now: float | None = None
        self._lock = Lock()
        self._records: dict[str, _BindingRecord] = {}
        self._seen_bindings: set[str] = set()
        self._published: set[CredentialGeneration] = set()
        self._rejected: set[tuple[str, str]] = set()
        self._used_fences: set[str] = set()

    def _now(self) -> float:
        """Deny malformed/regressing clocks without renewing or reviving an old lease."""
        try:
            value = self._clock()
        except Exception:
            raise CredentialAvailabilityError(CredentialAvailabilityErrorCode.UNAVAILABLE) from None
        if (
            not _finite_number(value)
            or value < 0
            or (self._last_now is not None and value < self._last_now)
        ):
            raise CredentialAvailabilityError(CredentialAvailabilityErrorCode.INVALID_STATE)
        self._last_now = float(value)
        return self._last_now

    def _new_fence(self) -> str:
        """Mint ownership/completion fencing only, never material identity or activation."""
        try:
            value = uuid4()
        except Exception:
            raise CredentialAvailabilityError(CredentialAvailabilityErrorCode.UNAVAILABLE) from None
        if not isinstance(value, UUID) or value.hex in self._used_fences:
            raise CredentialAvailabilityError(CredentialAvailabilityErrorCode.INVALID_STATE)
        self._used_fences.add(value.hex)
        return value.hex

    def _record(self, binding_id: str) -> _BindingRecord | None:
        """Never confuse loss of a known active record with first activation."""
        record = self._records.get(binding_id)
        if record is None:
            if binding_id in self._seen_bindings:
                raise CredentialAvailabilityError(CredentialAvailabilityErrorCode.INVALID_STATE)
            return None
        valid = (
            isinstance(record, _BindingRecord)
            and isinstance(record.generation, CredentialGeneration)
            and record.generation.binding_id == binding_id
            and record.generation in self._published
            and isinstance(record.publication, CredentialGenerationPublication)
            and record.publication.generation == record.generation
            and isinstance(record.state, CredentialAvailabilityState)
            and record.state is not CredentialAvailabilityState.UNKNOWN
        )
        if not valid:
            raise CredentialAvailabilityError(CredentialAvailabilityErrorCode.INVALID_STATE)
        rejected = (binding_id, record.generation.material_id) in self._rejected
        if rejected != (record.state is CredentialAvailabilityState.QUARANTINED):
            raise CredentialAvailabilityError(CredentialAvailabilityErrorCode.INVALID_STATE)
        if record.state is CredentialAvailabilityState.VALIDATING:
            owner = record.owner
            if (
                not isinstance(owner, _ValidationOwner)
                or not isinstance(owner.admission, CredentialAdmission)
                or not owner.admission.is_validation
                or owner.admission.generation != record.generation
                or owner.admission.validation_fence not in self._used_fences
                or not _finite_number(owner.expires_at)
                or owner.expires_at <= 0
            ):
                raise CredentialAvailabilityError(CredentialAvailabilityErrorCode.INVALID_STATE)
        elif record.owner is not None:
            raise CredentialAvailabilityError(CredentialAvailabilityErrorCode.INVALID_STATE)
        if record.state is CredentialAvailabilityState.AVAILABLE:
            receipt = record.receipt
            if (
                not isinstance(receipt, CredentialCompletionReceipt)
                or receipt.generation != record.generation
                or receipt.validation_fence not in self._used_fences
                or receipt.completion_fence not in self._used_fences
            ):
                raise CredentialAvailabilityError(CredentialAvailabilityErrorCode.INVALID_STATE)
        elif record.receipt is not None:
            raise CredentialAvailabilityError(CredentialAvailabilityErrorCode.INVALID_STATE)
        return record


class InMemoryCredentialAvailabilityReader:
    """Expose snapshots only; share no generation publication method."""

    def __init__(self, state: InMemoryCredentialAvailabilityState) -> None:
        """Retain an explicitly shared same-process state object."""
        if not isinstance(state, InMemoryCredentialAvailabilityState):
            raise CredentialContractError("credential adapter needs explicit local state")
        self._state = state

    async def snapshot(self, binding_id: str) -> CredentialAvailabilitySnapshot:
        """Project expiry without claiming, renewing, or mutating validation ownership."""
        unknown = CredentialAvailabilitySnapshot(binding_id, CredentialAvailabilityState.UNKNOWN)
        with self._state._lock:
            now = self._state._now()
            record = self._state._record(binding_id)
            if record is None:
                return unknown
            projected = record.state
            if (
                projected is CredentialAvailabilityState.VALIDATING
                and _live_owner(record, now) is None
            ):
                projected = CredentialAvailabilityState.PENDING_VALIDATION
            return CredentialAvailabilitySnapshot(binding_id, projected, record.generation)


class InMemoryCredentialAvailabilityWorker(InMemoryCredentialAvailabilityReader):
    """Worker admission and narrowing observations, with no publish capability.

    Critical sections contain no await or remote I/O. The state-owned thread lock
    serializes wrappers even across local threads/event loops, not remote replicas.
    """

    async def admit(
        self, generation: CredentialGeneration, *, attempt_id: str
    ) -> CredentialAdmission | None:
        """Admit AVAILABLE attempts or atomically claim/recheck one live validation owner."""
        ordinary = CredentialAdmission(generation, attempt_id)
        with self._state._lock:
            now = self._state._now()
            record = self._state._record(generation.binding_id)
            if record is None or record.generation != generation:
                return None
            if record.state is CredentialAvailabilityState.AVAILABLE:
                return ordinary
            if record.state is CredentialAvailabilityState.QUARANTINED:
                return None
            owner = _live_owner(record, now)
            if owner is not None:
                if owner.admission.attempt_id != attempt_id:
                    return None
                return replace(owner.admission, validation_timeout_seconds=owner.expires_at - now)
            deadline = now + self._state._lease_seconds
            if not isfinite(deadline) or deadline <= now:
                raise CredentialAvailabilityError(CredentialAvailabilityErrorCode.INVALID_STATE)
            admission = CredentialAdmission(
                generation, attempt_id, self._state._new_fence(), deadline - now
            )
            self._state._records[generation.binding_id] = replace(
                record,
                state=CredentialAvailabilityState.VALIDATING,
                owner=_ValidationOwner(admission, deadline),
            )
            return admission

    async def is_admitted(self, admission: CredentialAdmission) -> bool:
        """Check exact token and live validation fence without reacquiring/renewing."""
        with self._state._lock:
            now = self._state._now()
            record = self._state._record(admission.generation.binding_id)
            if record is None or record.generation != admission.generation:
                return False
            if not admission.is_validation:
                return record.state is CredentialAvailabilityState.AVAILABLE
            return _owns(record, admission, now)

    async def release(self, admission: CredentialAdmission) -> None:
        """Release only the matching validation fence; cleanup needs no working clock."""
        with self._state._lock:
            record = self._state._record(admission.generation.binding_id)
            if record is not None and _matches_owner(record, admission):
                self._state._records[admission.generation.binding_id] = replace(
                    record, state=CredentialAvailabilityState.PENDING_VALIDATION, owner=None
                )

    async def complete_validation(
        self, admission: CredentialAdmission
    ) -> CredentialCompletionReceipt | None:
        """Record caller-validated success once; duplicates return the same current receipt."""
        with self._state._lock:
            now = self._state._now()
            record = self._state._record(admission.generation.binding_id)
            if record is None or record.generation != admission.generation:
                return None
            if record.receipt is not None and record.receipt.matches_admission(admission):
                return record.receipt
            validation_fence = admission.validation_fence
            if validation_fence is None or not _owns(record, admission, now):
                return None
            receipt = CredentialCompletionReceipt(
                admission.generation,
                admission.attempt_id,
                validation_fence,
                self._state._new_fence(),
            )
            self._state._records[admission.generation.binding_id] = replace(
                record, state=CredentialAvailabilityState.AVAILABLE, owner=None, receipt=receipt
            )
            return receipt

    async def is_completion_current(self, receipt: CredentialCompletionReceipt) -> bool:
        """Check the store-issued current receipt, not its retired validation lease."""
        with self._state._lock:
            record = self._state._record(receipt.generation.binding_id)
            return (
                record is not None
                and record.state is CredentialAvailabilityState.AVAILABLE
                and record.receipt == receipt
            )

    async def record_rejection(self, rejection: CredentialBindingRejection) -> None:
        """Retain published binding/material history, including delayed retired-token facts."""
        with self._state._lock:
            generation = rejection.generation
            record = self._state._record(generation.binding_id)
            if record is None or generation not in self._state._published:
                raise CredentialAvailabilityError(CredentialAvailabilityErrorCode.INVALID_STATE)
            self._state._rejected.add((generation.binding_id, generation.material_id))
            if record.generation.material_id == generation.material_id:
                self._state._records[generation.binding_id] = replace(
                    record, state=CredentialAvailabilityState.QUARANTINED, owner=None, receipt=None
                )


class InMemoryCredentialGenerationPublisher:
    """Synthetic controller capability; cannot validate authority or secret-version mapping."""

    def __init__(self, state: InMemoryCredentialAvailabilityState) -> None:
        """Share the same explicit state as readers/workers, not a permissive fallback."""
        if not isinstance(state, InMemoryCredentialAvailabilityState):
            raise CredentialContractError("credential adapter needs explicit local state")
        self._state = state

    async def publish(self, publication: CredentialGenerationPublication) -> bool:
        """CAS the full token; first activation is pending, rejected material stays denied."""
        with self._state._lock:
            generation = publication.generation
            record = self._state._record(generation.binding_id)
            if record is not None and record.publication == publication:
                return True
            current = None if record is None else record.generation
            if current != publication.expected_generation:
                return False
            rejected = (generation.binding_id, generation.material_id) in self._state._rejected
            self._state._records[generation.binding_id] = _BindingRecord(
                generation,
                publication,
                CredentialAvailabilityState.QUARANTINED
                if rejected
                else CredentialAvailabilityState.PENDING_VALIDATION,
            )
            self._state._seen_bindings.add(generation.binding_id)
            self._state._published.add(generation)
            return True


def _finite_number(value: float) -> bool:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return False
    try:
        return isfinite(value)
    except OverflowError:
        return False


def _live_owner(record: _BindingRecord, now: float) -> _ValidationOwner | None:
    owner = record.owner
    if owner is not None and now < owner.expires_at:
        return owner
    return None


def _matches_owner(record: _BindingRecord, admission: CredentialAdmission) -> bool:
    owner = record.owner
    return (
        owner is not None
        and admission.is_validation
        and record.generation == admission.generation
        and owner.admission.attempt_id == admission.attempt_id
        and owner.admission.validation_fence == admission.validation_fence
    )


def _owns(record: _BindingRecord, admission: CredentialAdmission, now: float) -> bool:
    return _live_owner(record, now) is not None and _matches_owner(record, admission)
