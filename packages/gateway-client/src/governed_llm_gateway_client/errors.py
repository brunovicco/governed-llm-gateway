"""Sanitized errors exposed by the thin gateway client."""


class GatewayClientError(RuntimeError):
    """Base error for client configuration, transport, HTTP, or protocol failures."""


class GatewayConfigurationError(GatewayClientError):
    """Raised when local client configuration is missing or unsafe."""


class GatewayTransportError(GatewayClientError):
    """Raised after the single gateway transport attempt fails."""


class GatewayProtocolError(GatewayClientError):
    """Raised when the gateway response violates the normalized client protocol."""


class GatewayHTTPError(GatewayClientError):
    """Sanitized non-success HTTP response from the gateway."""

    def __init__(self, *, status_code: int, code: str) -> None:
        """Store stable HTTP metadata without retaining a raw response body."""
        self.status_code = status_code
        self.code = code
        super().__init__(f"gateway request failed: status={status_code} code={code}")
