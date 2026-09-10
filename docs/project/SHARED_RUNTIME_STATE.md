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

## Response cache

The same server can hold an exact-match response cache. It is off by default and a
workload must opt in; an enabled policy that names no workload is rejected rather than
treated as "cache everything".

### A cache hit is not an authorization shortcut

Lookup happens **after** the Policy Model Router has already authorized the request. The
key binds the whole authorization context — workload, effective risk level and data
classification, authorized model group, model-registry digest, ranking-policy digest,
output budget, and a digest of the exact messages — so an entry produced under one
authority is unreachable from another. Changing the registry or the ranking policy
changes the key, because a different configuration may route elsewhere and a pre-change
answer is no longer a current one.

### Only public data is ever stored

Caching writes prompt-derived material and model output to a server outside the gateway
process. That is a data-residency decision, not a performance one, so `public` is a
ceiling **in code**: no configuration raises it. Raising it would be a deliberate
contract change with its own review. For a deployment under LGPD or BCB scrutiny, this
is the difference between a cache that can be explained in review and one that cannot.

The stored key is the content-addressed identity digest, never the prompt: someone
reading the keyspace learns which authorized contexts were served, not what was asked.
Entries always carry a TTL, bounded at 24 hours, because an unbounded store of model
output is a retention decision nobody made deliberately.

### Exact match, deliberately

A hit requires the normalized messages to match exactly. Semantic caching over
embeddings would save more and is not offered here: an approximate hit returns the answer
to a *different* question, and introducing a probabilistic false positive into a path
whose entire claim is determinism trades away the property the gateway exists to provide.
That is a non-claim, not an oversight.

### What a served hit reports

A cache hit produces the same event lifecycle a provider call would, and terminal
evidence names the deployment that **originally produced the content**, because that is
what generated it. `ProviderExecution.cached` is what keeps that from reading as a fresh
call — without it the operational record would claim a provider was called when it was
not, which is a worse failure than not caching at all.

Two details follow from that:

- **Latency is this request's, not the original's.** A stored latency would misreport
  what just happened, so a hit reports the cache read.
- **Usage is the original call's.** It describes the answer's size, and the `cached`
  marker is what tells spend accounting not to count those tokens a second time.

A stored answer is served only when ranking would have selected the **same deployment**
anyway. The identity already binds the registry and ranking digests, so a divergence
means runtime health moved the selection — and replaying a decision that no longer holds
would contradict the routing provenance in the same event. The gateway executes instead.

A cache write that fails is swallowed: the caller already has the complete answer, and
losing it to a storage error would trade a future optimisation for a present failure.

### Shapes that never cache

Requests carrying images, tool definitions or a structured-output schema are not cached.
Each changes what a provider returns without being represented in the digest, so rather
than widen the key to shapes this cache has not been reviewed for, those requests simply
execute normally.

## Testing

| Level | What runs | Where |
| --- | --- | --- |
| Contract | Full circuit lifecycle against a RESP emulator with Lua | default gate, serverless |
| Integration | The same expectations against real Valkey **and** real Redis | `redis-health` workflow |

The emulator keeps the default gate credential-free and serverless. It proves the logic,
not the protocol, which is why the real-server matrix exists.
