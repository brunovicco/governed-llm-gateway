"""Phase 0 client boundary without HTTP/runtime dependencies."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GatewayClientConfig:
    """Connection configuration owned by a future concrete client implementation."""

    base_url: str
    api_key: str


class GatewayClient:
    """Reserved public SDK surface.

    Network behavior intentionally starts in Phase 12. Phase 0 establishes ownership only.
    """

    def __init__(self, config: GatewayClientConfig) -> None:
        """Initialize the client boundary with connection configuration."""
        self._config = config

    @property
    def base_url(self) -> str:
        """Return the configured gateway base URL without exposing credentials."""
        return self._config.base_url
