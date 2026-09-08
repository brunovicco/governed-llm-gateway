"""Explicit authenticated authorization boundary for read-only operations surfaces."""

from dataclasses import dataclass
from typing import Protocol

from .client_auth import GatewayClientIdentity


class OperationsReadAccessConfigurationError(ValueError):
    """Raised when an operations-read access policy is structurally invalid."""


class OperationsReadAuthorizationError(PermissionError):
    """Sanitized rejection for an authenticated principal without operations-read access."""

    def __init__(self) -> None:
        """Reject without exposing principal or configured grant metadata."""
        super().__init__("operations read access denied")


class GatewayClientIdentityAuthenticator(Protocol):
    """Authenticate one Gateway credential without assigning workload authority."""

    async def authenticate(self, *, api_key: str) -> GatewayClientIdentity:
        """Return the authenticated Gateway client identity or fail closed."""
        ...


@dataclass(frozen=True, slots=True)
class OperationsReadAccessPolicy:
    """Secret-free immutable allowlist for descriptive operations metadata."""

    principals: tuple[GatewayClientIdentity, ...] = ()

    def __post_init__(self) -> None:
        """Require deterministic unique typed principals while allowing deny-all policy."""
        if not isinstance(self.principals, tuple):
            raise OperationsReadAccessConfigurationError("principals must use a tuple")
        if any(not isinstance(principal, GatewayClientIdentity) for principal in self.principals):
            raise OperationsReadAccessConfigurationError(
                "principals must contain GatewayClientIdentity values"
            )
        if len(set(self.principals)) != len(self.principals):
            raise OperationsReadAccessConfigurationError("principals must not contain duplicates")
        expected = tuple(
            sorted(
                self.principals,
                key=lambda principal: (principal.client_id, principal.environment),
            )
        )
        if self.principals != expected:
            raise OperationsReadAccessConfigurationError(
                "principals must use deterministic client_id/environment order"
            )

    def allows(self, identity: GatewayClientIdentity) -> bool:
        """Return exact principal membership without wildcard or inferred role semantics."""
        if not isinstance(identity, GatewayClientIdentity):
            raise TypeError("identity must use GatewayClientIdentity")
        return identity in self.principals


class OperationsReadAccessService:
    """Authenticate one Gateway principal and require an explicit operations-read grant."""

    def __init__(
        self,
        *,
        authenticator: GatewayClientIdentityAuthenticator,
        policy: OperationsReadAccessPolicy,
    ) -> None:
        """Bind the existing Gateway authenticator to a secret-free operations policy."""
        if not isinstance(policy, OperationsReadAccessPolicy):
            raise TypeError("policy must use OperationsReadAccessPolicy")
        self._authenticator = authenticator
        self._policy = policy

    async def authorize(self, *, api_key: str) -> GatewayClientIdentity:
        """Return an explicitly granted authenticated principal or fail closed."""
        identity = await self._authenticator.authenticate(api_key=api_key)
        if not self._policy.allows(identity):
            raise OperationsReadAuthorizationError()
        return identity
