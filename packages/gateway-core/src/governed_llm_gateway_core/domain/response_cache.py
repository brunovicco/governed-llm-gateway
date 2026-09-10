"""Governed response-cache policy and cache identity.

A cache that serves a stored completion is answering on a provider's behalf, so it sits
inside the governed path and obeys the same rules. Three properties define it here.

**A cache hit is not an authorization shortcut.** The key binds the full authorization
context, so an entry produced for one authorized context can never be served into
another. Lookup happens after the Policy Model Router has already decided; the cache
narrows work, never authority.

**Only public data is ever stored.** Caching writes prompt-derived material and model
output to a server outside the gateway process. That is a data-residency decision, not a
performance one, so it is bounded at ``public`` in code rather than in configuration —
raising it would be a deliberate contract change with its own review, not a config edit.

**Caching is off unless a workload opts in.** An empty allowlist caches nothing.
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass

from governed_llm_gateway_contracts import DataClassification, Message, RiskLevel

CACHE_SCHEMA_VERSION = "1.0"
_MAX_TTL_SECONDS = 86_400


class ResponseCachePolicyError(ValueError):
    """Raised when a response-cache policy would permit something it must not."""


@dataclass(frozen=True, slots=True)
class ResponseCachePolicy:
    """Deployment-owned rules for what may be cached, and for how long."""

    enabled: bool = False
    allowed_workloads: frozenset[str] = frozenset()
    ttl_seconds: int = 300

    def __post_init__(self) -> None:
        """Reject a policy that is enabled without saying what it applies to."""
        if not isinstance(self.allowed_workloads, frozenset):
            raise ResponseCachePolicyError("allowed_workloads must be a frozenset")
        if self.ttl_seconds <= 0 or self.ttl_seconds > _MAX_TTL_SECONDS:
            raise ResponseCachePolicyError(f"ttl_seconds must be between 1 and {_MAX_TTL_SECONDS}")
        if self.enabled and not self.allowed_workloads:
            raise ResponseCachePolicyError(
                "an enabled response cache must name the workloads it applies to"
            )
        for workload in self.allowed_workloads:
            if not workload or workload.strip() != workload:
                raise ResponseCachePolicyError(
                    "allowed_workloads must contain normalized non-empty identifiers"
                )

    def permits(
        self,
        *,
        workload: str,
        data_classification: DataClassification,
    ) -> bool:
        """Return whether this exact request may read from or write to the cache.

        ``public`` is a hard ceiling rather than a configurable one: everything above it
        would leave the gateway process as stored prompt-derived material.
        """
        if not self.enabled:
            return False
        if data_classification is not DataClassification.PUBLIC:
            return False
        return workload in self.allowed_workloads


@dataclass(frozen=True, slots=True)
class ResponseCacheIdentity:
    """Everything a cached answer is only valid for."""

    workload: str
    risk_level: RiskLevel
    data_classification: DataClassification
    authorized_model_group: str
    model_registry_digest: str
    ranking_policy_digest: str
    max_output_tokens: int
    messages_digest: str

    def __post_init__(self) -> None:
        """Require every binding that makes a stored answer safe to reuse."""
        for name in (
            "workload",
            "authorized_model_group",
            "model_registry_digest",
            "ranking_policy_digest",
            "messages_digest",
        ):
            value = getattr(self, name)
            if not value or value.strip() != value:
                raise ResponseCachePolicyError(f"{name} must be a normalized non-empty string")
        if self.max_output_tokens <= 0:
            raise ResponseCachePolicyError("max_output_tokens must be positive")

    @property
    def digest(self) -> str:
        """Return the content-addressed cache key for this exact authorized context."""
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "workload": self.workload,
            "risk_level": self.risk_level.value,
            "data_classification": self.data_classification.value,
            "authorized_model_group": self.authorized_model_group,
            "model_registry_digest": self.model_registry_digest,
            "ranking_policy_digest": self.ranking_policy_digest,
            "max_output_tokens": self.max_output_tokens,
            "messages_digest": self.messages_digest,
        }
        canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def messages_digest(messages: Sequence[Message]) -> str:
    """Return a deterministic digest over exactly the content sent to a provider.

    Only role and text participate. Images are not represented, so a request carrying
    them can never collide with a text-only one — a caller of ``build_cache_identity``
    must refuse to cache those rather than hash around them.
    """
    payload = [{"role": message.role.value, "content": message.content} for message in messages]
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def is_cacheable_request(
    messages: Sequence[Message],
    *,
    structured_output_requested: bool,
    tools_requested: bool,
) -> bool:
    """Return whether a request's shape is representable as an exact cache entry.

    Images, tool definitions and structured-output schemas all change what a provider
    returns without being part of the digest above. Rather than widen the digest to cover
    shapes this cache has not been reviewed for, those requests simply do not cache.
    """
    if structured_output_requested or tools_requested:
        return False
    return not any(message.images for message in messages)
