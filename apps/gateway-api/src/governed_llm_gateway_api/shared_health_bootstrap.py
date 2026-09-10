"""Composition of shared deployment health from a deployment-owned server URL.

Isolated here because it is the one place the gateway process names a concrete RESP
client. `RedisDeploymentHealthTracker` speaks a Protocol, so which client and which
server a deployment uses stay operator decisions.

Absent configuration, the process keeps the in-process tracker. That is a real
limitation with more than one replica rather than a default to be silent about, so
enabling shared state is explicit and its absence is visible in operations output.
"""

from dataclasses import dataclass

from governed_llm_gateway_core.adapters.health_redis import (
    RedisDeploymentHealthTracker,
    RedisHealthKeyspace,
)
from governed_llm_gateway_core.application.health import DeploymentHealthPort
from governed_llm_gateway_core.application.resilience import InMemoryHealthTracker
from governed_llm_gateway_core.domain.resilience import CircuitBreakerPolicy


class SharedHealthConfigurationError(ValueError):
    """Raised when shared runtime state is requested but cannot be composed safely."""


@dataclass(frozen=True, slots=True)
class SharedHealthSettings:
    """Deployment-owned inputs for shared circuit state."""

    url: str
    key_prefix: str = "governed-llm-gateway"
    ttl_seconds: int = 86_400

    def __post_init__(self) -> None:
        """Validate the shape of the server URL without contacting it."""
        if not self.url or self.url.strip() != self.url:
            raise SharedHealthConfigurationError("shared health url must be normalized")
        if not self.url.startswith(("redis://", "rediss://", "valkey://", "valkeys://", "unix://")):
            raise SharedHealthConfigurationError(
                "shared health url must use a RESP scheme: redis, rediss, valkey, valkeys or unix"
            )


def build_health_tracker(
    settings: SharedHealthSettings | None,
    *,
    circuit_policy: CircuitBreakerPolicy | None = None,
) -> DeploymentHealthPort:
    """Return shared health when configured, and the in-process tracker otherwise."""
    if settings is None:
        return InMemoryHealthTracker(circuit_policy)

    try:
        import redis.asyncio as redis_asyncio
    except ImportError as exc:  # pragma: no cover - exercised by the import guard test
        raise SharedHealthConfigurationError(
            "shared health requires a RESP client; install the 'redis' extra"
        ) from exc

    # rediss:// keeps TLS; the scheme is the operator's transport decision, not ours.
    client = redis_asyncio.from_url(
        settings.url.replace("valkey://", "redis://").replace("valkeys://", "rediss://"),
        decode_responses=True,
    )
    return RedisDeploymentHealthTracker(
        client,
        circuit_policy,
        keyspace=RedisHealthKeyspace(
            prefix=settings.key_prefix,
            ttl_seconds=settings.ttl_seconds,
        ),
    )
