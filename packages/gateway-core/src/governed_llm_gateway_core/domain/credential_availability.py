"""Internal, secret-free credential availability values from ADR-0019.

Construction checks shape, not trusted issuance, provider acceptance, or shared-state
integrity. These values are not public DTOs and must not be serialized into evidence.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite

_OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_MAX_EPOCH = 2**63 - 1


class CredentialContractError(ValueError):
    """Invalid internal metadata, without echoing private input."""


class CredentialAvailabilityState(StrEnum):
    """UNKNOWN is a deny-only read outcome, never a recovery state."""

    UNKNOWN = "unknown"
    PENDING_VALIDATION = "pending_validation"
    VALIDATING = "validating"
    AVAILABLE = "available"
    QUARANTINED = "quarantined"


class CredentialRejectionEvidence(StrEnum):
    """Facts from separately reviewed classifiers, not HTTP-status inference."""

    AUTHENTICATION_BOUNDARY_REJECTED = "authentication_boundary_rejected"
    EXPLICIT_INVALID_CREDENTIAL = "explicit_invalid_credential"


@dataclass(frozen=True, slots=True)
class CredentialGeneration:
    """Authority-issued token captured by an immutable local adapter bundle.

    secret_version_id is an opaque authority handle for an exact backend version;
    backend locators and secret values stay outside core. Material equality/history
    is established by the authority, never generated or inferred by this class.
    """

    binding_id: str = field(repr=False)
    epoch: int
    material_id: str = field(repr=False)
    secret_version_id: str = field(repr=False)
    runtime_digest: str = field(repr=False)
    auth_scope_digest: str = field(repr=False)

    def __post_init__(self) -> None:
        """Reject malformed identity, activation epoch, and secret-free provenance."""
        for value in (self.binding_id, self.material_id, self.secret_version_id):
            _require_opaque_id(value)
        if (
            not isinstance(self.epoch, int)
            or isinstance(self.epoch, bool)
            or not 1 <= self.epoch <= _MAX_EPOCH
        ):
            raise CredentialContractError("credential epoch must be a positive bounded integer")
        for value in (self.runtime_digest, self.auth_scope_digest):
            if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
                raise CredentialContractError("credential provenance must use a canonical digest")


@dataclass(frozen=True, slots=True)
class CredentialGenerationPublication:
    """Controller-only compare-and-set intent, not permission to clear quarantine."""

    generation: CredentialGeneration = field(repr=False)
    expected_generation: CredentialGeneration | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Require monotonic activation within one explicitly declared binding."""
        _require_generation(self.generation)
        if self.expected_generation is None:
            return
        _require_generation(self.expected_generation)
        if (
            self.generation.binding_id != self.expected_generation.binding_id
            or self.generation.epoch <= self.expected_generation.epoch
        ):
            raise CredentialContractError("credential publication must advance the same binding")


@dataclass(frozen=True, slots=True)
class CredentialAvailabilitySnapshot:
    """Read-only projection; no owner is acquired by reading or checking eligibility."""

    binding_id: str = field(repr=False)
    state: CredentialAvailabilityState
    generation: CredentialGeneration | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Reject missing, cross-binding, or contradictory active-token evidence."""
        _require_opaque_id(self.binding_id)
        if not isinstance(self.state, CredentialAvailabilityState):
            raise CredentialContractError("credential state must use the closed vocabulary")
        if self.state is CredentialAvailabilityState.UNKNOWN:
            if self.generation is not None:
                raise CredentialContractError("unknown credential state cannot prove a generation")
            return
        _require_generation(self.generation)
        if self.generation is None or self.generation.binding_id != self.binding_id:
            raise CredentialContractError("credential snapshot must describe the same binding")

    def is_candidate_eligible(self, generation: CredentialGeneration) -> bool:
        """Only narrow candidate selection, never authorize or grant admission.

        Pending material must remain rankable for an ordinary governed validation
        request. Execution still needs an atomic admission; VALIDATING owners use
        their handle, not this candidate-read predicate, to check continued admission.
        """
        _require_generation(generation)
        return self.generation == generation and self.state in {
            CredentialAvailabilityState.PENDING_VALIDATION,
            CredentialAvailabilityState.AVAILABLE,
        }


@dataclass(frozen=True, slots=True)
class CredentialAdmission:
    """Attempt-owned handle, with a fence and remaining lifetime only for validation."""

    generation: CredentialGeneration = field(repr=False)
    attempt_id: str = field(repr=False)
    validation_fence: str | None = field(default=None, repr=False)
    validation_timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        """Reject incomplete validation ownership or an unbounded numeric lifetime."""
        _require_generation(self.generation)
        _require_opaque_id(self.attempt_id)
        if (self.validation_fence is None) != (self.validation_timeout_seconds is None):
            raise CredentialContractError("credential validation needs a fence and lifetime")
        if self.validation_fence is not None:
            _require_opaque_id(self.validation_fence)
        if self.validation_timeout_seconds is not None:
            _require_lifetime(self.validation_timeout_seconds)

    @property
    def is_validation(self) -> bool:
        """Ordinary AVAILABLE attempts cannot claim recovery authority."""
        return self.validation_fence is not None


@dataclass(frozen=True, slots=True)
class CredentialCompletionReceipt:
    """Store-issued validation completion fence, usable after retiring its own lease."""

    generation: CredentialGeneration = field(repr=False)
    attempt_id: str = field(repr=False)
    validation_fence: str = field(repr=False)
    completion_fence: str = field(repr=False)

    def __post_init__(self) -> None:
        """Require bounded attribution; constructing a receipt cannot prove liveness."""
        _require_generation(self.generation)
        for value in (self.attempt_id, self.validation_fence, self.completion_fence):
            _require_opaque_id(value)

    def matches_admission(self, admission: CredentialAdmission) -> bool:
        """Correlate ownership only; the store must separately validate the receipt."""
        return (
            admission.is_validation
            and self.generation == admission.generation
            and self.attempt_id == admission.attempt_id
            and self.validation_fence == admission.validation_fence
        )


@dataclass(frozen=True, slots=True)
class CredentialBindingRejection:
    """Internal reviewed fact about the generation actually presented by an attempt.

    No classifier is implemented here. Neither a status nor a ProviderError alone
    can supply this fact; trusted adapter configuration must establish its semantics.
    """

    generation: CredentialGeneration = field(repr=False)
    evidence: CredentialRejectionEvidence
    classifier_id: str = field(repr=False)

    def __post_init__(self) -> None:
        """Retain a closed reason and bounded attribution, never provider error bodies."""
        _require_generation(self.generation)
        if not isinstance(self.evidence, CredentialRejectionEvidence):
            raise CredentialContractError("credential rejection needs reviewed evidence")
        _require_opaque_id(self.classifier_id)


def _require_opaque_id(value: str) -> None:
    if not isinstance(value, str) or _OPAQUE_ID.fullmatch(value) is None:
        raise CredentialContractError("credential metadata must be a bounded opaque identifier")


def _require_generation(value: CredentialGeneration | None) -> None:
    if not isinstance(value, CredentialGeneration):
        raise CredentialContractError("credential metadata needs a validated generation")


def _require_lifetime(value: float) -> None:
    valid = isinstance(value, int | float) and not isinstance(value, bool)
    if valid:
        try:
            valid = isfinite(value) and value > 0
        except OverflowError:
            valid = False
    if not valid:
        raise CredentialContractError("credential validation lifetime must be finite and positive")
