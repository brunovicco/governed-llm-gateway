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

### Exclusive recovery probes

After cooldown, HALF_OPEN has one attempt-owned lease (60 seconds by default), not
permission for every replica to execute. Rechecks of the same live owner are idempotent
and do not renew that lease. Ranking snapshots never acquire a probe. Execution acquires
once per attempt and releases on cancellation, disconnect or local failure, without
counting those as provider failures. An abandoned lease expires without deleting health
history, allowing another probe. Generation fencing prevents late owners and earlier
CLOSED attempts from changing the current circuit. A permanent probe failure releases
the owner but neither proves recovery nor becomes transient.

Only probes get this lifetime bound. Normal provider timeouts and selection
`max_latency_ms` semantics are unchanged. Streaming checks ownership and bounds upstream
reads without leaving a task timeout active across public-event yields; backpressure
consumes probe lifetime. Once semantic output is visible, expiry still cannot cause
retry/fallback. Expiry/cancellation cannot guarantee that a remote provider physically
stopped; they revoke local/shared ownership and fence later events/results.

Redis uses server `TIME` for cooldown and lease expiry; the injectable clock is for
tests only. Key TTL must exceed both cooldown and probe lifetime. All replicas must use
the same policy/keyspace. Drain/stop old boolean-admission writers before the coordinated
upgrade; mixed old/new writers cannot guarantee exclusivity. Existing counters and OPEN
cooldown are retained. See [ADR-0018](../adr/ADR-0018-exclusive-half-open-admission.md).

## Response cache

The same server can hold an exact-match response cache. It is off by default and a
workload must opt in; an enabled policy that names no workload is rejected rather than
treated as "cache everything".

### A cache hit is not an authorization shortcut

Lookup happens **after** the Policy Model Router has already authorized the request. The
schema 2.0 key binds authenticated `EffectivePolicyContext.client_id`, the accepted
PDP `policy_digest`, workload, effective risk/data classification, authorized model
group, model-registry digest, ranking-policy digest, output budget, and exact messages.
Distinct clients or changed PDP policies therefore cannot share the same identity when
the other fields match. Caller-declared `agent_identity` never chooses a client's cache,
and API keys are not cache identities. There is no authorized tenant in the current
contract; tenant isolation is not invented or claimed.

Changing the PDP policy, registry, or ranking policy changes the key. This is answer
scoping, not cached authorization: every request still obtains a fresh PDP decision and
passes ranking and deterministic provider preflight before lookup. A stable policy digest
cannot bypass denial, expiry, single-use governance, revocation, or kill switch. A hit
reports the current routing decision, not the source request's policy decision.

### Versioned migration and rollout

Keys use `<deployment-prefix>:cache:2.0:<identity-hex-digest>`; stored payloads declare
schema `2.0` too. Readers never fall back to unversioned legacy keys, convert old entries,
or accept copied schema 1.0 payloads. Old entries remain untouched until their existing
TTL expires; no keyspace deletion is needed. The first post-upgrade request is a cold miss.

Drain or upgrade old workers before claiming isolation across a fleet. Namespace separation
does not fix legacy workers that still serve their old cross-client cache. Keep response
caching disabled if rolling back to legacy code. Deployment prefixes must still separate
independent deployments. See [ADR-0020](../adr/ADR-0020-authenticated-response-cache-identity.md).

### Only public data is ever stored

Caching writes prompt-derived material and model output to a server outside the gateway
process. That is a data-residency decision, not a performance one, so `public` is a
ceiling **in code**: no configuration raises it. Raising it would be a deliberate
contract change with its own review. For a deployment under LGPD or BCB scrutiny, this
is the difference between a cache that can be explained in review and one that cannot.

The stored key contains the identity digest, not plaintext client IDs or prompts. Digests
are not encryption or protection from guessing low-entropy inputs; access to keys and
stored completions still needs appropriate transport/access/residency controls. No new
identity or prompt-derived cache metadata is added to logs, traces, or public events.
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
| Cache contract | Identity/migration and real coordinator with synthetic auth/PDP/providers over a RESP emulator | default gate, credential-free |
| Integration | The same expectations against real Valkey **and** real Redis | `redis-health` workflow |

The emulator keeps the default gate credential-free and serverless. It proves the logic,
not the protocol, which is why the real-server matrix exists.
The cache suite covers client separation/spoofing, policy changes, fresh PDP denial/outage/
invalid provenance, effective classification floors, concurrent scoped hits, unchanged default-off
behavior, and health-driven deployment selection. It is not a live-provider or fleet rollout proof.
