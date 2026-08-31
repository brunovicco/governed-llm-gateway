"""Typed provider-neutral gateway errors."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GatewayError:
    """Serializable error contract returned without leaking provider internals."""

    code: str
    message: str
    retryable: bool = False
