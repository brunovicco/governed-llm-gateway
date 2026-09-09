"""Shared structural validation for Gateway client credentials."""

from typing import TypeGuard

MAX_GATEWAY_API_KEY_LENGTH = 4096


def is_valid_gateway_api_key(value: object) -> TypeGuard[str]:
    """Return whether one credential satisfies the bounded normalized ASCII shape."""
    return (
        isinstance(value, str)
        and 0 < len(value) <= MAX_GATEWAY_API_KEY_LENGTH
        and value.isascii()
        and value.strip() == value
    )
