"""Response-cache port and the evidence a cached answer must carry.

A cached answer is still an answer, so it is reported as terminal evidence with the
execution identity that originally produced it and an explicit cached marker. Presenting
a stored completion as a fresh provider call would make the operational record lie, which
is a worse failure than not caching at all.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from governed_llm_gateway_core.domain.response_cache import ResponseCacheIdentity


@dataclass(frozen=True, slots=True)
class CachedResponse:
    """One stored completion plus the execution that originally produced it."""

    content: str
    input_tokens: int
    output_tokens: int
    provider: str
    model: str
    deployment: str
    api_family: str
    finish_reason: str
    cached_at: datetime
    source_request_id: UUID

    def __post_init__(self) -> None:
        """Require a usable answer and the identity that produced it."""
        if not self.content:
            raise ValueError("a cached response must carry content")
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("cached usage must be non-negative")
        for name in ("provider", "model", "deployment", "api_family", "finish_reason"):
            value = getattr(self, name)
            if not value or value.strip() != value:
                raise ValueError(f"cached {name} must be a normalized non-empty string")
        if self.cached_at.tzinfo is None or self.cached_at.utcoffset() is None:
            raise ValueError("cached_at must be timezone-aware")


class ResponseCachePort(Protocol):
    """Read and write completions for one exact authorized context."""

    async def get(self, identity: ResponseCacheIdentity) -> CachedResponse | None:
        """Return a stored completion for this identity, or None."""
        ...

    async def put(
        self,
        identity: ResponseCacheIdentity,
        response: CachedResponse,
        *,
        ttl_seconds: int,
    ) -> None:
        """Store one completion under this identity for a bounded lifetime."""
        ...
