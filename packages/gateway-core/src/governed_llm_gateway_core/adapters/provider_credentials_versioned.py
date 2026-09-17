"""Unwired, adapter-only exact-generation secret boundary from ADR-0019.

Token correlation is not proof of trusted issuance or material equality. A concrete
authority adapter must verify those facts and exact-version mapping, never resolve
latest or mint metadata from an environment string. No backend is selected here.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from governed_llm_gateway_core.domain.credential_availability import (
    CredentialContractError,
    CredentialGeneration,
)


class VersionedProviderSecretErrorCode(StrEnum):
    """Closed local outcomes, never provider or backend diagnostic payloads."""

    INVALID_REQUEST = "invalid_request"
    UNAVAILABLE = "unavailable"
    INVALID_RESULT = "invalid_result"


class VersionedProviderSecretError(RuntimeError):
    """Sanitized failure without secret values, locators, or raw backend context."""

    def __init__(self, code: VersionedProviderSecretErrorCode) -> None:
        """Accept only bounded outcome metadata and a fixed message."""
        if not isinstance(code, VersionedProviderSecretErrorCode):
            raise CredentialContractError("versioned secret error needs a closed category")
        self.code = code
        super().__init__("versioned provider credential resolution failed")


@dataclass(frozen=True, slots=True, eq=False)
class VersionedProviderCredential:
    """Sensitive adapter-local result; neither a public DTO nor evidence.

    Default repr hides all fields. Equality/hash use object identity, not the secret.
    Frozen slots do not provide zeroization or prevent explicit serialization/access.
    Construction validates shape only, not that material belongs to this generation.
    """

    generation: CredentialGeneration = field(repr=False)
    credential: str = field(repr=False)

    def __post_init__(self) -> None:
        """Reject untyped metadata and empty/whitespace/control-bearing material."""
        if not isinstance(self.generation, CredentialGeneration):
            raise CredentialContractError("versioned secret needs a validated generation")
        _require_credential(self.credential)


class VersionedProviderSecretResolver(Protocol):
    """Infrastructure-owned exact-version retrieval, with no latest fallback.

    A concrete adapter privately maps the opaque authority handle to one backend
    version and verifies binding, epoch, stable material identity, and provenance.
    Missing history/mapping or unavailable authority must deny, not manufacture a
    token. It owns bounded I/O and resource lifecycle; it must propagate cancellation.
    """

    async def resolve_version(
        self, generation: CredentialGeneration
    ) -> VersionedProviderCredential:
        """Fetch only the supplied generation after secret-free validation succeeds."""
        ...


async def resolve_exact_provider_credential(
    generation: CredentialGeneration,
    secrets: VersionedProviderSecretResolver,
) -> VersionedProviderCredential:
    """Perform one fetch and enforce full-token correlation without a latest fallback.

    Only the injected resolver may perform I/O. This helper neither checks current
    availability nor constructs/swaps an adapter, publishes a token, or validates a
    provider response. Callers still need verified scope/config and authority state.
    Cancellation remains cancellation; ordinary failures suppress raw traceback
    chaining. Repr hiding is not permission to record locals or serialize the result.
    """
    if not isinstance(generation, CredentialGeneration):
        raise VersionedProviderSecretError(VersionedProviderSecretErrorCode.INVALID_REQUEST)
    try:
        result = await secrets.resolve_version(generation)
    except Exception:
        raise VersionedProviderSecretError(VersionedProviderSecretErrorCode.UNAVAILABLE) from None
    if not isinstance(result, VersionedProviderCredential) or result.generation != generation:
        raise VersionedProviderSecretError(VersionedProviderSecretErrorCode.INVALID_RESULT)
    try:
        _require_credential(result.credential)
    except CredentialContractError:
        raise VersionedProviderSecretError(
            VersionedProviderSecretErrorCode.INVALID_RESULT
        ) from None
    return result


def _require_credential(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or any(
            character.isspace() or ord(character) < 32 or 127 <= ord(character) < 160
            for character in value
        )
    ):
        raise CredentialContractError("versioned secret material is malformed")
