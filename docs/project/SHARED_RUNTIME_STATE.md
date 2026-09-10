# Shared Runtime State

Deployment health and circuit-breaker state can be shared across gateway replicas
instead of living in one process.

## Why

`InMemoryHealthTracker` keeps circuit state per process. With one replica that is
correct and cheap. With two or more, each worker independently learns that a provider is
failing: the first replica opens its circuit after N consecutive failures while the
others keep sending traffic to the same failing deployment, and the aggregate behaviour
stops being deterministic. That contradicts the property this gateway exists to provide.

Shared state fixes the aggregate, not the local view. It is operational evidence, never
authorization: a healthy deployment is still only reachable if the Policy Model Router
already authorized its model group, and an unhealthy one narrows the eligible set rather
than widening it.

## Which server

**Whichever one the operator already runs.** The adapter uses only core data types and
Lua — no modules, no vendor-specific commands — so the same code runs against Redis Open
Source, Valkey, ElastiCache or MemoryDB. That neutrality is deliberate, and it matters
more than it looks:

- **Redis 8** merged the former Stack modules (Search, JSON, TimeSeries, Bloom, Vector
  Sets) into core. None of them are needed here, so "Redis Stack vs Redis" is not a
  decision this workload has to make.
- **Licensing is the real difference.** Redis Open Source 8 is AGPLv3; Valkey is BSD
  under the Linux Foundation and is the default for new AWS ElastiCache and MemoryDB
  clusters. For a regulated deployment, AGPL in the runtime is a legal-review trigger
  even where the practical obligation is narrow. That decision belongs to whoever
  deploys this, not to a library, which is why nothing here pins a server.

The `redis-health` CI workflow runs the same contract against **both** Valkey 8 and
Redis 8. A divergence between them would be a defect in this repository.

The client is equally a deployment choice: `RedisDeploymentHealthTracker` takes a
`RespClient` Protocol and imports no client library at all. `gateway-core` therefore has
no Redis dependency; `gateway-api` declares an optional `redis` extra for the one place
that constructs a concrete client.

## Enabling it

```bash
uv run --frozen --package governed-llm-gateway-api governed-llm-gateway \
  --deployment-root "$PWD" \
  ... \
  --shared-health-url redis://127.0.0.1:6379/0 \
  --shared-health-key-prefix governed-llm-gateway
```

`rediss://` and `valkeys://` keep TLS. Absent `--shared-health-url` the process uses the
in-process tracker — correct for one replica, a real limitation for more than one, and
explicit rather than silent.

The key prefix keeps two deployments that share one server from colliding. Health keys
carry a TTL (24 hours by default) so a retired deployment leaves nothing behind.

## Correctness

Every transition is a single Lua script evaluated server-side. Read-modify-write across
replicas is precisely the race that would make a shared breaker worse than a local one:
two replicas reading `consecutive_failures = 1` and both writing `2` would lose a failure
and delay opening the circuit. An integration test drives ten concurrent replicas and
asserts no counter is lost.

The domain decision — is this error transient, which counter does it belong to — stays in
Python, in the one `is_transient_provider_error` classifier that retry, fallback and every
health tracker share. Lua only moves state.

## Testing

| Level | What runs | Where |
| --- | --- | --- |
| Contract | Full circuit lifecycle against a RESP emulator with Lua | default gate, serverless |
| Integration | The same expectations against real Valkey **and** real Redis | `redis-health` workflow |

The emulator keeps the default gate credential-free and serverless. It proves the logic,
not the protocol, which is why the real-server matrix exists.
