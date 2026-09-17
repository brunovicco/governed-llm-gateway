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

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from math import ceil
from typing import Any, Protocol, cast
from uuid import uuid4

from governed_llm_gateway_core.application.health import health_attempt_id
from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderErrorCode,
    is_transient_provider_error,
)
from governed_llm_gateway_core.domain.resilience import (
    CircuitBreakerPolicy,
    CircuitState,
    DeploymentHealthSnapshot,
    HealthAdmission,
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

# Common ARGV: injected now (empty means server TIME), cooldown ms, key TTL,
# probe lease ms, fresh generation. All operations use one hash/key.
_TRANSITION = """
local now = tonumber(ARGV[1])
if now == nil then
  local stamp = redis.call('TIME')
  now = tonumber(stamp[1]) * 1000 + math.floor(tonumber(stamp[2]) / 1000)
end
local state = redis.call('HGET', KEYS[1], 'circuit_state') or 'closed'
if state ~= 'closed' and state ~= 'open' and state ~= 'half_open' then
  error('invalid circuit state')
end
local function retire()
  redis.call('HSET', KEYS[1], 'generation', ARGV[5],
    'probe_owner', '', 'probe_expires_at_ms', '')
  redis.call('EXPIRE', KEYS[1], ARGV[3])
end
if state == 'open' then
  local opened = tonumber(redis.call('HGET', KEYS[1], 'opened_at_ms'))
  if opened ~= nil and (now - opened) >= tonumber(ARGV[2]) then
    state = 'half_open'
    redis.call('HSET', KEYS[1], 'circuit_state', state)
    redis.call('EXPIRE', KEYS[1], ARGV[3])
  end
end
local owner = redis.call('HGET', KEYS[1], 'probe_owner') or ''
local expires = tonumber(redis.call('HGET', KEYS[1], 'probe_expires_at_ms'))
if state == 'half_open' and owner ~= '' then
  if expires == nil then error('invalid probe lease') end
  if now >= expires then
    retire()
    owner = ''
  end
end
local function controls()
  if ARGV[6] == '' then return state == 'closed' end
  if redis.call('HGET', KEYS[1], 'generation') ~= ARGV[6] then return false end
  if ARGV[8] == '1' then
    return state == 'half_open' and owner == ARGV[7]
  end
  return state == 'closed'
end
"""

_ALLOW_SCRIPT = (
    _TRANSITION
    + """
if state == 'open' then return {} end
if state == 'closed' then
  redis.call('HSETNX', KEYS[1], 'generation', ARGV[5])
  redis.call('EXPIRE', KEYS[1], ARGV[3])
  return {redis.call('HGET', KEYS[1], 'generation'), ''}
end
if owner ~= '' and owner ~= ARGV[6] then return {} end
if owner == '' then
  expires = now + tonumber(ARGV[4])
  redis.call('HSET', KEYS[1], 'generation', ARGV[5],
    'probe_owner', ARGV[6], 'probe_expires_at_ms', expires)
  redis.call('EXPIRE', KEYS[1], ARGV[3])
end
return {redis.call('HGET', KEYS[1], 'generation'), tostring(expires - now)}
"""
)

# Outcome ARGV: generation (empty for uncorrelated report), owner, probe flag,
# latency. Uncorrelated reports cannot demonstrate recovery.
_SUCCESS_SCRIPT = (
    _TRANSITION
    + """
local valid = controls()
if ARGV[8] == '1' and not valid then return 0 end
redis.call('HINCRBY', KEYS[1], 'request_count', 1)
redis.call('HINCRBY', KEYS[1], 'success_count', 1)
redis.call('HSET', KEYS[1], 'last_latency_ms', ARGV[9])
if valid then
  redis.call('HSET', KEYS[1], 'consecutive_transient_failures', 0,
    'circuit_state', 'closed', 'opened_at_ms', '')
  if ARGV[8] == '1' then retire() end
end
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 1
"""
)

# Additional failure ARGV: transient, timeout, rate-limit, server-error, threshold.
_FAILURE_SCRIPT = (
    _TRANSITION
    + """
local valid = controls()
if ARGV[8] == '1' and not valid then return 0 end
redis.call('HINCRBY', KEYS[1], 'request_count', 1)
redis.call('HSET', KEYS[1], 'last_latency_ms', ARGV[9])
if ARGV[10] ~= '1' then
  if valid then
    redis.call('HSET', KEYS[1], 'consecutive_transient_failures', 0)
    if ARGV[8] == '1' then retire() end
  end
  redis.call('EXPIRE', KEYS[1], ARGV[3])
  return 1
end
redis.call('HINCRBY', KEYS[1], 'transient_failure_count', 1)
if ARGV[11] == '1' then redis.call('HINCRBY', KEYS[1], 'timeout_count', 1) end
if ARGV[12] == '1' then redis.call('HINCRBY', KEYS[1], 'rate_limit_count', 1) end
if ARGV[13] == '1' then redis.call('HINCRBY', KEYS[1], 'server_error_count', 1) end
if valid then
  local consecutive = redis.call('HINCRBY', KEYS[1], 'consecutive_transient_failures', 1)
  if state == 'half_open' or consecutive >= tonumber(ARGV[14]) then
    redis.call('HSET', KEYS[1], 'circuit_state', 'open', 'opened_at_ms', now)
    retire()
  end
end
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 1
"""
)

_RELEASE_SCRIPT = (
    _TRANSITION
    + """
if ARGV[8] == '1' and controls() then retire() end
return 1
"""
)

_CHECK_SCRIPT = (
    _TRANSITION
    + """
if controls() then return 1 end
return 0
"""
)

# Reading is a transition too: an expired open circuit becomes half-open when observed,
# so a replica that only reads still sees the same state machine as one that executes.
_SNAPSHOT_SCRIPT = (
    _TRANSITION
    + """
return redis.call('HMGET', KEYS[1],
  'request_count', 'success_count', 'transient_failure_count', 'timeout_count',
  'rate_limit_count', 'server_error_count', 'consecutive_transient_failures',
  'last_latency_ms', 'circuit_state', 'opened_at_ms')
"""
)


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
        clock: Callable[[], float] | None = None,
    ) -> None:
        """Bind a RESP client and the same circuit policy the in-process tracker uses."""
        self._client = client
        self._policy = policy or CircuitBreakerPolicy()
        self._keyspace = keyspace or RedisHealthKeyspace()
        self._clock = clock
        if self._keyspace.ttl_seconds <= max(
            self._policy.cooldown_seconds, self._policy.probe_lease_seconds
        ):
            raise ValueError("health key TTL must outlive cooldown and probe lease")

    async def allow_request(
        self, deployment_id: str, *, attempt_id: str | None = None
    ) -> HealthAdmission | None:
        """Atomically claim one probe or recheck its owner without renewing the lease."""
        key = self._keyspace.health_key(_require_deployment_id(deployment_id))
        owner = health_attempt_id(attempt_id)
        result = await self._client.eval(_ALLOW_SCRIPT, 1, key, *self._transition_args(), owner)
        values = cast(Sequence[object], result)
        if not values:
            return None
        remaining = _as_text(values[1])
        return HealthAdmission(
            deployment_id,
            owner,
            _as_text(values[0]) or "",
            None if remaining == "" else _as_int(values[1]) / 1000,
        )

    async def release_request(self, admission: HealthAdmission) -> None:
        """Release a matching owner only; retired owners cannot release a replacement."""
        if not admission.is_probe:
            return
        key = self._keyspace.health_key(_require_deployment_id(admission.deployment_id))
        await self._client.eval(
            _RELEASE_SCRIPT, 1, key, *self._transition_args(), *self._admission_args(admission)
        )

    async def is_admitted(self, admission: HealthAdmission) -> bool:
        """Check a generation atomically without claiming or renewing a lease."""
        key = self._keyspace.health_key(_require_deployment_id(admission.deployment_id))
        result = await self._client.eval(
            _CHECK_SCRIPT, 1, key, *self._transition_args(), *self._admission_args(admission)
        )
        return _as_int(result) == 1

    async def record_success(
        self, deployment_id: str, *, latency_ms: int, admission: HealthAdmission | None = None
    ) -> bool:
        """Fence circuit recovery and reject a retired probe's late success."""
        key = self._keyspace.health_key(_require_deployment_id(deployment_id))
        _check_admission_deployment(deployment_id, admission)
        result = await self._client.eval(
            _SUCCESS_SCRIPT,
            1,
            key,
            *self._transition_args(),
            *self._admission_args(admission),
            str(max(0, latency_ms)),
        )
        return _as_int(result) == 1

    async def record_failure(
        self,
        deployment_id: str,
        error: ProviderError,
        *,
        latency_ms: int,
        admission: HealthAdmission | None = None,
    ) -> None:
        """Record sanitized failure metadata and open the circuit on bounded transients."""
        key = self._keyspace.health_key(_require_deployment_id(deployment_id))
        _check_admission_deployment(deployment_id, admission)
        transient = is_transient_provider_error(error)
        server_error = error.code is ProviderErrorCode.UNAVAILABLE and (
            error.status_code is None or error.status_code >= 500
        )
        await self._client.eval(
            _FAILURE_SCRIPT,
            1,
            key,
            *self._transition_args(),
            *self._admission_args(admission),
            str(max(0, latency_ms)),
            "1" if transient else "0",
            "1" if error.code is ProviderErrorCode.TIMEOUT else "0",
            "1" if error.code is ProviderErrorCode.RATE_LIMIT else "0",
            "1" if server_error else "0",
            str(self._policy.failure_threshold),
        )

    async def snapshot(self, deployment_id: str) -> DeploymentHealthSnapshot:
        """Return current shared health, moving an expired open circuit to half-open."""
        key = self._keyspace.health_key(_require_deployment_id(deployment_id))
        raw = await self._client.eval(
            _SNAPSHOT_SCRIPT,
            1,
            key,
            *self._transition_args(),
        )
        return _snapshot_from(deployment_id, cast(Sequence[object] | None, raw))

    async def snapshots(self, deployment_ids: Sequence[str]) -> dict[str, DeploymentHealthSnapshot]:
        """Return deterministic snapshots for all requested deployments."""
        return {
            deployment_id: await self.snapshot(deployment_id) for deployment_id in deployment_ids
        }

    def _transition_args(self) -> tuple[str, ...]:
        return (
            "" if self._clock is None else str(int(self._clock() * 1000)),
            str(ceil(self._policy.cooldown_seconds * 1000)),
            str(self._keyspace.ttl_seconds),
            str(ceil(self._policy.probe_lease_seconds * 1000)),
            uuid4().hex,
        )

    @staticmethod
    def _admission_args(admission: HealthAdmission | None) -> tuple[str, str, str]:
        if admission is None:
            return ("", "", "0")
        return (admission.generation, admission.attempt_id, "1" if admission.is_probe else "0")


def _check_admission_deployment(deployment_id: str, admission: HealthAdmission | None) -> None:
    if admission is not None and admission.deployment_id != deployment_id:
        raise ValueError("health admission belongs to another deployment")


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
    if circuit_state is CircuitState.HALF_OPEN:
        return HealthStatus.DEGRADED
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
