"""Thin provider-neutral client SDK boundary."""

from .client import GatewayClient, GatewayClientConfig
from .errors import (
    GatewayClientError,
    GatewayConfigurationError,
    GatewayHTTPError,
    GatewayProtocolError,
    GatewayRequestError,
    GatewayTransportError,
)

__all__ = [
    "GatewayClient",
    "GatewayClientConfig",
    "GatewayClientError",
    "GatewayConfigurationError",
    "GatewayHTTPError",
    "GatewayProtocolError",
    "GatewayRequestError",
    "GatewayTransportError",
]
