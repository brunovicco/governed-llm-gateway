"""Response cache over a RESP server.

Like the shared health adapter, this imports no client library and speaks only core
commands, so the operator's choice of Redis Open Source, Valkey, ElastiCache or MemoryDB
stays theirs.

The stored key is the content-addressed identity digest, never the prompt: a key dump
reveals which authorized contexts were served, not what anyone asked. Entries always
carry a TTL, because an unbounded cache of model output is a data-retention decision
nobody made deliberately.
"""

import json
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from governed_llm_gateway_core.application.response_cache import CachedResponse
from governed_llm_gateway_core.domain.response_cache import (
    CACHE_SCHEMA_VERSION,
    ResponseCacheIdentity,
)

DEFAULT_KEY_PREFIX = "governed-llm-gateway"

_FIELDS = (
    "schema_version",
    "content",
    "input_tokens",
    "output_tokens",
    "provider",
    "model",
    "deployment",
    "api_family",
    "finish_reason",
    "cached_at",
    "source_request_id",
)


class RespCacheClient(Protocol):
    """The bounded slice of a RESP client this cache needs."""

    def get(self, name: str) -> Awaitable[Any]:
        """Return the stored value for one key, or None."""
        ...

    def set(
        self,
        name: str,
        value: str,
        *,
        ex: int,
    ) -> Awaitable[Any]:
        """Store one value with an expiry, in seconds."""
        ...


@dataclass(frozen=True, slots=True)
class RedisResponseCache:
    """Exact-match response cache keyed by governed cache identity."""

    client: RespCacheClient
    prefix: str = DEFAULT_KEY_PREFIX

    def __post_init__(self) -> None:
        """Reject a prefix that would let two deployments read each other's entries."""
        if not self.prefix or self.prefix.strip() != self.prefix:
            raise ValueError("key prefix must be a non-empty normalized string")

    def cache_key(self, identity: ResponseCacheIdentity) -> str:
        """Return the key holding one authorized context's stored completion."""
        return f"{self.prefix}:cache:{identity.digest.removeprefix('sha256:')}"

    async def get(self, identity: ResponseCacheIdentity) -> CachedResponse | None:
        """Return a stored completion, treating any malformed entry as a miss."""
        raw = await self.client.get(self.cache_key(identity))
        if raw is None:
            return None
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        # A stored entry written by another schema version is a miss, never a guess.
        if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None
        try:
            return CachedResponse(
                content=str(payload["content"]),
                input_tokens=int(payload["input_tokens"]),
                output_tokens=int(payload["output_tokens"]),
                provider=str(payload["provider"]),
                model=str(payload["model"]),
                deployment=str(payload["deployment"]),
                api_family=str(payload["api_family"]),
                finish_reason=str(payload["finish_reason"]),
                cached_at=datetime.fromisoformat(str(payload["cached_at"])),
                source_request_id=UUID(str(payload["source_request_id"])),
            )
        except (KeyError, TypeError, ValueError):
            return None

    async def put(
        self,
        identity: ResponseCacheIdentity,
        response: CachedResponse,
        *,
        ttl_seconds: int,
    ) -> None:
        """Store one completion under a bounded lifetime."""
        if ttl_seconds <= 0:
            raise ValueError("cache ttl_seconds must be positive")
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "content": response.content,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "provider": response.provider,
            "model": response.model,
            "deployment": response.deployment,
            "api_family": response.api_family,
            "finish_reason": response.finish_reason,
            "cached_at": response.cached_at.isoformat(),
            "source_request_id": str(response.source_request_id),
        }
        await self.client.set(
            self.cache_key(identity),
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            ex=ttl_seconds,
        )
