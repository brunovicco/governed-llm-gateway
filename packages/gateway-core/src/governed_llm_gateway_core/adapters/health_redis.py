"""Shared deployment health and circuit state over a RESP server.

`InMemoryHealthTracker` keeps circuit state per process, so with more than one replica
each worker learns independently that a provider is failing. The aggregate behaviour
stops being deterministic, which contradicts the property this gateway sells. This
adapter moves that state to a server every replica can see.

**Server neutrality is deliberate.** Only core data types and Lua are used — no modules,
no vendor commands — so the same adapter runs against Redis Open Source, Valkey,
ElastiCache or MemoryDB. The operator chooses; the gateway does not embed that choice.
Redis 8 folded the Stack modules into core, but nothing here needs them, and Redis 8 is
AGPLv3 while Valkey is BSD — a licensing decision that belongs to whoever deploys this,
not to a library.

Every transition is one Lua script, evaluated server-side, because read-modify-write
across replicas is exactly the race that makes a shared breaker worse than a local one.
The domain decision — is this error transient, which counter does it belong to — stays
in Python. Lua only moves state.
"""

import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderErrorCode,
    is_transient_provider_error,
)
from governed_llm_gateway_core.domain.resilience import (
    CircuitBreakerPolicy,
    CircuitState,
    DeploymentHealthSnapshot,
    HealthStatus,
)

DEFAULT_KEY_PREFIX = "governed-llm-gateway"
# Health is operational evidence with no value once a deployment stops reporting; an
# expiry keeps a retired deployment from leaving state behind forever.
DEFAULT_KEY_TTL_SECONDS = 86_400

_FIELDS = (
    "request_count",
    "success_count",
    "transient_failure_count",
    "timeout_count",
    "rate_limit_count",
    "server_error_count",
    "consecutive_transient_failures",
    "last_latency_ms",
    "circuit_state",
    "opened_at_ms",
)

# Move an expired open circuit to half-open and report whether a call may proceed.
_ALLOW_SCRIPT = """
local state = redis.call('HGET', KEYS[1], 'circuit_state')
if state ~= 'open' then
  return 1
end
local opened = tonumber(redis.call('HGET', KEYS[1], 'opened_at_ms'))
local now = tonumber(ARGV[1])
local cooldown = tonumber(ARGV[2])
if opened == nil or (now - opened) >= cooldown then
  redis.call('HSET', KEYS[1], 'circuit_state', 'half_open')
  redis.call('EXPIRE', KEYS[1], ARGV[3])
  return 1
end
return 0
"""

_SUCCESS_SCRIPT = """
redis.call('HINCRBY', KEYS[1], 'request_count', 1)
redis.call('HINCRBY', KEYS[1], 'success_count', 1)
redis.call('HSET', KEYS[1],
  'last_latency_ms', ARGV[1],
  'consecutive_transient_failures', 0,
  'circuit_state', 'closed',
  'opened_at_ms', '')
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""

# ARGV: latency, transient flag, timeout flag, rate-limit flag, server-error flag,
#       failure threshold, now (ms), key ttl.
_FAILURE_SCRIPT = """
redis.call('HINCRBY', KEYS[1], 'request_count', 1)
redis.call('HSET', KEYS[1], 'last_latency_ms', ARGV[1])
if ARGV[2] ~= '1' then
  redis.call('HSET', KEYS[1], 'consecutive_transient_failures', 0)
  redis.call('EXPIRE', KEYS[1], ARGV[8])
  return 'closed'
end
redis.call('HINCRBY', KEYS[1], 'transient_failure_count', 1)
local consecutive = redis.call('HINCRBY', KEYS[1], 'consecutive_transient_failures', 1)
if ARGV[3] == '1' then redis.call('HINCRBY', KEYS[1], 'timeout_count', 1) end
if ARGV[4] == '1' then redis.call('HINCRBY', KEYS[1], 'rate_limit_count', 1) end
if ARGV[5] == '1' then redis.call('HINCRBY', KEYS[1], 'server_error_count', 1) end
local state = redis.call('HGET', KEYS[1], 'circuit_state')
if state == 'half_open' or consecutive >= tonumber(ARGV[6]) then
  redis.call('HSET', KEYS[1], 'circuit_state', 'open', 'opened_at_ms', ARGV[7])
  redis.call('EXPIRE', KEYS[1], ARGV[8])
  return 'open'
end
redis.call('EXPIRE', KEYS[1], ARGV[8])
return state or 'closed'
"""

# Reading is a transition too: an expired open circuit becomes half-open when observed,
# so a replica that only reads still sees the same state machine as one that executes.
_SNAPSHOT_SCRIPT = """
local state = redis.call('HGET', KEYS[1], 'circuit_state')
if state == 'open' then
  local opened = tonumber(redis.call('HGET', KEYS[1], 'opened_at_ms'))
  local now = tonumber(ARGV[1])
  local cooldown = tonumber(ARGV[2])
  if opened == nil or (now - opened) >= cooldown then
    redis.call('HSET', KEYS[1], 'circuit_state', 'half_open')
    redis.call('EXPIRE', KEYS[1], ARGV[3])
  end
end
return redis.call('HMGET', KEYS[1],
  'request_count', 'success_count', 'transient_failure_count', 'timeout_count',
  'rate_limit_count', 'server_error_count', 'consecutive_transient_failures',
  'last_latency_ms', 'circuit_state', 'opened_at_ms')
"""


class RespClient(Protocol):
    """The bounded slice of a RESP client this adapter needs."""

    def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: Any,
    ) -> Awaitable[Any]:
        """Evaluate one Lua script server-side.

        Declared as returning an awaitable rather than as ``async def`` so a client whose
        ``eval`` is a plain method returning a coroutine still satisfies the port, and
        typed loosely on arguments because RESP clients accept any scalar there.
        """
        ...


@dataclass(frozen=True, slots=True)
class RedisHealthKeyspace:
    """Deployment-owned key naming so several gateways can share one server safely."""

    prefix: str = DEFAULT_KEY_PREFIX
    ttl_seconds: int = DEFAULT_KEY_TTL_SECONDS

    def __post_init__(self) -> None:
        """Reject a prefix or TTL that would let two deployments collide silently."""
        if not self.prefix or self.prefix.strip() != self.prefix:
            raise ValueError("key prefix must be a non-empty normalized string")
        if self.ttl_seconds <= 0:
            raise ValueError("key ttl_seconds must be positive")

    def health_key(self, deployment_id: str) -> str:
        """Return the key holding one deployment's shared health state."""
        return f"{self.prefix}:health:{deployment_id}"


class RedisDeploymentHealthTracker:
    """Deployment health and circuit state shared across gateway replicas."""

    def __init__(
        self,
        client: RespClient,
        policy: CircuitBreakerPolicy | None = None,
        *,
        keyspace: RedisHealthKeyspace | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Bind a RESP client and the same circuit policy the in-process tracker uses."""
        self._client = client
        self._policy = policy or CircuitBreakerPolicy()
        self._keyspace = keyspace or RedisHealthKeyspace()
        self._clock = clock

    async def allow_request(self, deployment_id: str) -> bool:
        """Reject while the circuit is open; allow one probe once cooldown has elapsed."""
        key = self._keyspace.health_key(_require_deployment_id(deployment_id))
        result = await self._client.eval(
            _ALLOW_SCRIPT,
            1,
            key,
            str(self._now_ms()),
            str(int(self._policy.cooldown_seconds * 1000)),
            str(self._keyspace.ttl_seconds),
        )
        return _as_int(result) == 1

    async def record_success(self, deployment_id: str, *, latency_ms: int) -> None:
        """Record success and close a half-open or degraded circuit."""
        key = self._keyspace.health_key(_require_deployment_id(deployment_id))
        await self._client.eval(
            _SUCCESS_SCRIPT,
            1,
            key,
            str(max(0, latency_ms)),
            str(self._keyspace.ttl_seconds),
        )

    async def record_failure(
        self,
        deployment_id: str,
        error: ProviderError,
        *,
        latency_ms: int,
    ) -> None:
        """Record sanitized failure metadata and open the circuit on bounded transients."""
        key = self._keyspace.health_key(_require_deployment_id(deployment_id))
        transient = is_transient_provider_error(error)
        server_error = error.code is ProviderErrorCode.UNAVAILABLE and (
            error.status_code is None or error.status_code >= 500
        )
        await self._client.eval(
            _FAILURE_SCRIPT,
            1,
            key,
            str(max(0, latency_ms)),
            "1" if transient else "0",
            "1" if error.code is ProviderErrorCode.TIMEOUT else "0",
            "1" if error.code is ProviderErrorCode.RATE_LIMIT else "0",
            "1" if server_error else "0",
            str(self._policy.failure_threshold),
            str(self._now_ms()),
            str(self._keyspace.ttl_seconds),
        )

    async def snapshot(self, deployment_id: str) -> DeploymentHealthSnapshot:
        """Return current shared health, moving an expired open circuit to half-open."""
        key = self._keyspace.health_key(_require_deployment_id(deployment_id))
        raw = await self._client.eval(
            _SNAPSHOT_SCRIPT,
            1,
            key,
            str(self._now_ms()),
            str(int(self._policy.cooldown_seconds * 1000)),
            str(self._keyspace.ttl_seconds),
        )
        return _snapshot_from(deployment_id, cast(Sequence[object] | None, raw))

    async def snapshots(self, deployment_ids: Sequence[str]) -> dict[str, DeploymentHealthSnapshot]:
        """Return deterministic snapshots for all requested deployments."""
        return {
            deployment_id: await self.snapshot(deployment_id) for deployment_id in deployment_ids
        }

    def _now_ms(self) -> int:
        return int(self._clock() * 1000)


def _snapshot_from(
    deployment_id: str,
    values: Sequence[object] | None,
) -> DeploymentHealthSnapshot:
    fields = dict(zip(_FIELDS, list(values or []), strict=False))
    request_count = _as_int(fields.get("request_count"))
    success_count = _as_int(fields.get("success_count"))
    transient = _as_int(fields.get("transient_failure_count"))
    circuit_raw = _as_text(fields.get("circuit_state")) or CircuitState.CLOSED.value
    last_latency = fields.get("last_latency_ms")
    return DeploymentHealthSnapshot(
        deployment_id=deployment_id,
        status=_status_for(request_count, success_count, CircuitState(circuit_raw)),
        request_count=request_count,
        success_count=success_count,
        transient_failure_count=transient,
        timeout_count=_as_int(fields.get("timeout_count")),
        rate_limit_count=_as_int(fields.get("rate_limit_count")),
        server_error_count=_as_int(fields.get("server_error_count")),
        consecutive_transient_failures=_as_int(fields.get("consecutive_transient_failures")),
        last_latency_ms=None if _as_text(last_latency) in (None, "") else _as_int(last_latency),
        circuit_state=CircuitState(circuit_raw),
    )


def _status_for(
    request_count: int,
    success_count: int,
    circuit_state: CircuitState,
) -> HealthStatus:
    if circuit_state is CircuitState.OPEN:
        return HealthStatus.UNHEALTHY
    if request_count == 0:
        return HealthStatus.HEALTHY
    if success_count == request_count:
        return HealthStatus.HEALTHY
    if success_count == 0:
        return HealthStatus.UNHEALTHY
    return HealthStatus.DEGRADED


def _require_deployment_id(deployment_id: str) -> str:
    if not deployment_id or deployment_id.strip() != deployment_id:
        raise ValueError("deployment_id must be a non-empty normalized string")
    return deployment_id


def _as_int(value: object) -> int:
    text = _as_text(value)
    if text is None or text == "":
        return 0
    return int(text)


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
