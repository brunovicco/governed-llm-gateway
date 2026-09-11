# Changelog

## Unreleased

- **The two services in the authority chain now run against each other**: `compose.pdp-composition.yml`
  stands up a real Policy Model Router with `RUNTIME_AUTHORIZATION_REQUIRED=true` and Redis behind it,
  and `scripts/composition_proof.py` drives the Gateway's own PDP adapter against it through four
  scenarios -- a forwarded envelope is authorized, the same request without one is refused, an envelope
  signed by a key the Gateway trusts and the Router does not is refused, and replaying the accepted
  envelope is refused. This is the only place the two hand-written mirrors of the Verifiable AI
  Governance contract meet: neither repository may import the other, the canonical signing bytes must
  stay byte-identical, and no CI on either side would catch a one-field drift. The run surfaced three
  facts no single-repository test could produce -- the request identity has to come from the signed
  claims, workload identifiers have to be dotted for both contracts to accept them, and every model
  group in a routing policy has to be reachable from a workload. `docs/project/PDP_COMPOSITION_PROOF.md`
  records what it proves, what it deliberately does not, and why the test-only issuer fixture is not a
  Governance implementation.
- **The gateway forwards runtime authorization to the Policy Decision Point**: `PolicyRequestMetadata`
  gained an optional `ForwardableGovernanceAuthorization` — the verified facts plus the signed
  envelope exactly as received — and the PDP adapter posts the Policy Model Router's wrapped
  `{request, authorization}` body when one is present. Without it the flat body goes out unchanged,
  so a non-enforcing Router deployment sees no difference. Before this, a Router with
  `RUNTIME_AUTHORIZATION_REQUIRED=true` (mandatory in its own staging and production) answered `403`
  and the composed system served no traffic while both sides behaved as designed. The envelope is
  never rebuilt from the projection — bytes this gateway chose are exactly what a signature exists to
  rule out — and a contract test verifies the forwarded copy against the key that verified the
  original. Forwarding grants no authority: no minting, no re-signing, and a PDP denial stays a
  denial. Because the Router binds `requested_at`, `workflow_id` and `task_id` to the signed claims,
  a forwarded request takes its identity from those claims rather than from this gateway's clock and
  request id, the response correlation check reads the same identity that went on the wire, and
  `PolicyRequestMetadata` refuses at construction — naming the field — any request the signed binding
  does not describe, rather than spending a round trip to be told so. `VerifiedGovernanceAuthorization`
  gained `issued_at`, which the verifier read but did not retain.

## v1.1.0 — 2026-09-10

Everything in this release is additive. The public contracts of `1.0.0` still hold: `ProviderExecution`
gained a `cached` field with a default, `POST /v1/chat/completions` is a new surface next to the
existing one, and the response cache and shared runtime state are both off unless a deployment turns
them on. The one removal is `governed_llm_gateway_core.application.ports`, a compatibility re-export of
`PolicyDecisionPort` that no module imported; the port itself is unchanged at
`governed_llm_gateway_core.application.policy`.

What this release adds, in one line: the Gateway now deploys as a container, keeps circuit state
coherent across replicas, can cache and can refuse spending past a ceiling, accepts OpenAI-shaped
requests, and ranks on evidence from a real benchmark run rather than static configuration.

- **READMEs rewritten as a product page** (#242): the status table keyed by internal increment IDs is
  gone -- phase status and dated evidence live in `CURRENT_STATE.md` and `CHECKPOINT_LOG.md` -- the
  non-claims section is condensed into `Scope`, the secret model is stated as the capability it
  provides (one place to rotate a provider credential, no consumer redeploy) rather than as a
  prohibition, and the container build and run are documented in the README itself.
- **Project documentation index and console vocabulary** (#241): `docs/project/README.md` groups all 49
  project documents, says what question each answers, and decodes the `Phase`/`PC`/`OR`/`CR` prefixes
  the documents use. The Console renders an empty deployment catalog as an explicit statement rather
  than a blank table body, and `Rejected candidates` becomes `Excluded before selection`, since every
  reason in that list is a ranking-stage exclusion applied after authorization and never a policy
  denial. Removes dead surface: `tests/e2e/` held only a README, two declared pytest markers were
  applied by no test, and `application/ports.py` re-exported a port for no importer.
- **Estimated-spend accounting and budgets**: per-client, per-workload accumulation of what
  execution implied, with limits that refuse a request once a ceiling is reached. Amounts derive
  from the Model Registry's pinned pricing and the provider's reported usage, so they are the
  gateway's **estimate** rather than an invoice — the docs and the code say so, because presenting
  a drifting pinned price as billed cost to a finance audience would be the wrong kind of
  confidence. Money accumulates as integer micro-USD: a float ledger loses precision at the scale
  that matters (a contract test asserts a thousand tenths of a cent total exactly one dollar), and
  a counter shared across replicas must be incremented atomically, which `INCRBY` on an integer is
  and a read-modify-write of a float is not. The guard runs after PDP authorization and before
  provider work, so a budget narrows and never widens. Reading fails closed — spending against a
  ceiling nobody can see is worse than refusing — while writing is swallowed, since the caller
  already holds their answer. A cached answer records nothing, which is what the `cached` marker
  added in the previous commit is for. Exhaustion is `>=`, because a budget that permits one more
  call at exactly its ceiling is designed to be exceeded. Also consolidates the cost formula, which
  was private to `ranking.py`, into the domain module that owns `PricingMetadata`. Adds
  `docs/project/SPEND_ACCOUNTING.md` and `tests/contract/test_spend_accounting.py` (24 cases);
  three governance-critical assertions were confirmed against mutated source.
- **Response cache wired into the governed streaming path**: the cache is now consulted and
  populated by real requests rather than only being available. `ProviderExecution` gains `cached`,
  because a served hit reports the deployment that originally produced the content and without that
  marker the operational record would claim a provider call that never happened; the flag threads
  through the SSE wire and the thin client's codec. Latency on a hit is this request's, usage is the
  original call's, and the marker is what tells spend accounting not to count those tokens twice.
  The cache identity is built in the coordinator from the **effective** authorization context, so a
  caller declaring `public` under a binding that raises the floor is judged on the raised value —
  the alternative would store data the deployment classified higher. A stored answer is served only
  when ranking would still select the same deployment: the existing contract invariant that terminal
  evidence must match routing provenance caught the inconsistency, and rather than weaken it the
  cache now falls through to a real execution when runtime health has moved the selection. A cache
  write failure is swallowed, since the caller already holds the complete answer. Adds
  `tests/contract/test_streaming_cache_integration.py` (11 cases) and
  `tests/contract/test_cache_identity_authorization.py` (7 cases); the four assertions that carry
  the governance weight were each confirmed against deliberately mutated source.
- **Governed response cache**: an exact-match completion cache on the same RESP server, off by
  default and opt-in per workload. Three properties define it. A cache hit is never an
  authorization shortcut: lookup happens after the Policy Model Router has decided, and the key
  binds the full authorization context — workload, effective risk and classification, authorized
  model group, registry and ranking digests, output budget and a digest of the exact messages — so
  an entry produced under one authority is unreachable from another, and a registry or policy
  change invalidates stored answers because a different configuration may route elsewhere. Only
  `public` data is ever stored, and that ceiling lives in code rather than configuration, because
  writing prompt-derived material to a server outside the process is a data-residency decision
  rather than a performance one. Entries are keyed by content-addressed digest, never by the
  prompt, and always carry a bounded TTL. Semantic caching over embeddings is an explicit
  non-claim: an approximate hit answers a different question, which is not a trade a gateway
  selling determinism can make. Requests with images, tools or structured output do not cache,
  since each changes the answer without being represented in the key.
- **Shared health and circuit state across replicas**: `InMemoryHealthTracker` kept circuit state
  per process, so with more than one replica each worker learned independently that a provider was
  failing and the aggregate fallback behaviour stopped being deterministic — a contradiction of the
  property this gateway sells. Adds `application/health.py` with a `DeploymentHealthPort` (services
  now depend on the port, not on the concrete tracker) and
  `adapters/health_redis.py`, which keeps that state on any RESP server. The port is asynchronous
  because the only useful implementation beyond one process is a network round trip; blocking the
  event loop to decide whether a circuit is open would trade one correctness problem for a worse
  one. Every transition is a single server-side Lua script, since read-modify-write across replicas
  is exactly the race that would make a shared breaker worse than a local one — an integration test
  drives ten concurrent replicas and asserts no counter is lost.

  **Server choice stays with the operator.** The adapter uses only core data types and Lua — no
  modules, no vendor commands — and imports no client library at all, taking a `RespClient`
  Protocol instead, so `gateway-core` gains no dependency and `gateway-api` declares an optional
  `redis` extra. Redis 8 folded the former Stack modules into core, and none of them are needed
  here, so the real difference is licensing: Redis Open Source 8 is AGPLv3 while Valkey is BSD and
  the AWS ElastiCache/MemoryDB default. That belongs to whoever deploys this, so the new
  `redis-health` workflow runs the same contract against **both** Valkey 8 and Redis 8.

  Also consolidates a pre-existing duplication surfaced by this work: the transient-error
  classification lived in two copies in `resilience.py` and `streaming.py`, and a third slightly
  different copy nearly shipped in the new adapter. There is now one
  `is_transient_provider_error`, because a copy that drifted by one condition would silently change
  when a circuit opens.
- **OpenAI-compatible ingress** (`POST /v1/chat/completions`): a consumer can now repoint an
  existing OpenAI client's `base_url` at the Gateway instead of adopting the thin SDK. It is
  adoption friction removed, not a second execution path — the route translates onto the existing
  `GenerateRequestModel` and reuses the same `GenerateCoordinator` preflight as `/v1/generate`, so
  authentication, PDP authorization, ranking, fallback and evidence are the governed path unchanged.
  `model` carries the **workload**, never a provider model. Shape validation refuses `openai/gpt-4`
  and uppercase or undotted names, but a dotted model name like `gpt-5.6-luna` is shaped exactly
  like a workload and passes — what refuses it is authorization, since an unregistered workload is
  in no binding's `allowed_workloads`. That distinction is documented rather than glossed, because
  relying on the pattern would be a protection that only looks like one. `risk_level` and
  `data_classification` come from the deployment-owned client-auth binding, so a caller cannot lower
  its own classification through this surface. Unknown fields, sampling controls included, are
  rejected rather than silently dropped. Responses carry governed evidence in an `x_gateway` object
  that OpenAI clients ignore. Adds `docs/project/OPENAI_COMPATIBLE_INGRESS.md`,
  `tests/contract/test_openai_compatible_ingress.py` (20 cases) and
  `tests/contract/test_openai_sdk_compatibility.py`, which drives the unmodified `openai` SDK
  against a loopback instance — credential-free and networkless — so SDK compatibility is re-proven
  on every run rather than asserted once.
- **Streaming failure paths under test**: `/v1/generate` is SSE-only, so the streaming stack is the
  gateway's primary execution path — and it was its least-covered one, with the aggregate 83.8%
  hiding `application/streaming.py` at 68.45% and `adapters/openai_compatible.py` at 66.15%. Adds
  `tests/contract/test_streaming_failure_paths.py` (11 cases) covering the properties that make
  partial delivery safe: a provider failure after content has already reached the caller must not
  retry or fall back, a truncated stream must not resemble a completed one, usage evidence is
  required before completion, caller cancellation must close the provider stream and propagate, the
  three streaming-capability guards must refuse rather than silently downgrade, and an open circuit
  must be skipped without being called. Adds
  `tests/contract/test_provider_payload_hardening.py` (16 cases) for the provider trust boundary,
  where every tool-call rejection path was unexercised: malformed shapes, non-JSON arguments, a tool
  the caller never declared, arguments violating the declared schema, and error text that must never
  reach a sanitized `ProviderError`. `application/streaming.py` 68.45% -> 76.03%,
  `openai_compatible.py` 66.15% -> 87.50%, `gemini_streaming.py` 70.59% -> 79.19%, total 83.87% ->
  84.35%. The two central safety assertions were verified against deliberately mutated source before
  being kept, so they fail when the property they describe is removed.
- **Observability behind a port**: the application layer imported `a2a_otel_kit.Observability`
  directly in `policy.py`, `resilience.py` and `streaming.py`, and `application/telemetry.py`
  additionally reached for `a2a_otel_kit.sanitize_attributes` and OpenTelemetry's `Span`, `Status`
  and `StatusCode` — the one place in the workspace where a telemetry backend leaked into
  application code. `architecture_check.py` never caught it because it guarded only contracts and
  domain. Adds `application/observability.py` with a `GatewaySpan`/`ObservabilityPort` pair, reduces
  `application/telemetry.py` to the vocabulary the application actually owns (span names, event
  names, the attribute allowlist) with no infrastructure import at all, and moves the binding to
  `adapters/observability_otel.py`. Sanitization deliberately stays with the library that owns it:
  the gateway contributes its allowlist as data and `sanitize_attributes` merges it with the kit's
  defaults, so the two vocabularies cannot drift. `server.py` wraps the configured kit exactly once,
  and every layer below sees only the port. The free span helpers are gone; call sites use span
  methods. `architecture_check.py` and `pyproject.toml` now declare the application boundary, and
  two contract tests cover it — one asserting the layer imports no telemetry backend, one asserting
  the binding is reachable from exactly the three adapters that legitimately hold it. Both were
  confirmed to fail against a deliberately planted violation before being kept.
- **Container deployment artifact**: adds `Dockerfile`, `.dockerignore`, `compose.gateway.yml`,
  `docs/project/CONTAINER_DEPLOYMENT.md` and a `image` CI workflow. The Gateway previously had no
  deployment artifact at all — only local launcher scripts. The image carries code only: no
  deployment configuration, no default `CMD`, non-root `uid 10001`, both stages pinned to one
  identical base-image digest (the virtualenv records its interpreter path), dependencies resolved
  in a layer a source change cannot invalidate, and `uv sync --no-editable` so the runtime stage
  copies the virtualenv alone — no sources, no build tooling, no `uv`. The consumer SDK is
  deliberately excluded. CI lints the Dockerfile, validates the compose model, builds the image and
  then proves three properties against the built artifact: it ships no deployment config and runs as
  the expected non-root uid, the entrypoint fails closed with no artifacts, and the credential-free
  operations-only container reports `healthy`. Documented limitation, not worked around: the
  operations-only entrypoint binds `127.0.0.1` with no `--host` flag, so it is reachable only from
  inside its container.
- **Benchmark-derived ranking, actually closed**: the Phase 10 -> Phase 11 chain
  (`Scorecard -> promote_snapshot -> compile_benchmark_hybrid_policy -> ApprovedRankingArtifact`)
  existed end to end and the runtime already accepted an approved artifact, but no
  `BenchmarkExecutor` implementation had ever been written, so `benchmarks/scorecards/` was empty
  and `personal-default`'s `rag.answer` ranked six deployments on hand-written scores that were
  `0.50` on every dimension except a single `cost` preference. Adds
  `benchmarks/provider_execution.py`, which binds one benchmark target to exactly one reviewed
  registry deployment and calls it through the same provider adapters the Gateway uses, and
  `scripts/publish_ranking_evidence.py`, which runs the dataset, persists an immutable
  content-addressed snapshot, promotes it through explicit mappings and writes the pinned approved
  artifact. `rag.answer` now ranks on real evidence from all six `balanced` deployments: quality
  from `0.875` to `1.000` and one genuine NVIDIA provider failure recorded as `0.833` availability.
  `reliability`/`latency`/`cost` remain static by the compiler's existing contract.
  `scripts/personal_default_launcher.py` boots from the artifact and pins its ID, so drift fails
  closed at startup. Adds `tests/contract/test_benchmark_provider_execution.py` and
  `tests/contract/test_personal_default_approved_ranking.py`, the latter asserting that promoted
  quality and availability are not uniform placeholders.
- **Quality gate runs each step once**: `scripts/quality_gate.py` invoked `architecture_check.py`
  and `secret_scan.py` directly and then ran `phase0_gate.py`, which runs both again. Steps are now
  named, timed, reported as a summary, and deduplicated; `phase0_gate.py` stays independently
  runnable and keeps owning those two checks.
- **Secret scan enumerates through Git, and is now itself under test**: `scripts/secret_scan.py`
  walked the filesystem and excluded only `.git`, `.venv` and `uv.lock`, so it read paths that can
  never reach a commit. A local `.env` holding a real provider key therefore failed
  `scripts/quality_gate.py` on a developer machine while CI stayed green only because no `.env`
  exists there, and every scan also read `node_modules/`, `dist/` and the tool caches. Candidates now
  come from `git ls-files --cached --others --exclude-standard` — tracked files plus untracked files
  that are not ignored, which is exactly the set a commit could carry. Enumeration fails closed
  outside a Git working tree rather than silently narrowing, findings report a line number and never
  print the matched value, and symlinks, deleted index entries, binary and oversized files are
  skipped. Adds `tests/contract/test_secret_scan.py` (10 cases), the first coverage this security
  control has had.
- **Documentation restructure** (#240): consolidates 27 narrow per-workload/per-benchmark docs under
  `docs/evaluation/` into the already-comprehensive `BENCHMARK_MATRIX.md`, removes 3 completed phase
  reports and a duplicate `MODEL_REGISTRY.md`, and splits `docs/project/CURRENT_STATE.md` into a short
  evergreen status document plus a new dated, append-only `docs/project/CHECKPOINT_LOG.md`.
- **Personal-default profile — full Anthropic and reasoning-strong proof coverage** (#239): every
  deployment in every model group `personal-default` wires is now individually proven live in that
  profile specifically (previously some were proven only in `live-development`), including
  `security.analysis`, `code.generate` and `code.review`.
- **PC-52 — Gateway Console per-request trace navigation** (#237): closes README item 2 and the OR-6
  per-trace-correlation gap. `ProviderExecution` gains an optional, strictly-validated `trace_id`; the
  Gateway threads its own real OTel span's trace ID through the terminal SSE event when tracing is
  enabled; the Console renders a "View this request's trace in Grafana" link to the exact trace via a
  second panel on the existing provisioned dashboard. Proven live twice (SDK and full browser run)
  against a real captured trace. Also fixes a real bug found while proving this: `otel-collector` in
  `compose.observability.yml` could never actually publish its host port because its only network was
  `internal: true`.
- **OR-9 minimum-hardening investigation** (#236): closes README item 3. A dedicated investigation found
  no further non-production security gap beyond the existing PC-34..PC-51 increments on the demonstrated
  operational surfaces; documents one previously-implicit-but-correct property (no CORS middleware on the
  Gateway API) explicitly.
- **PC-33 profile completeness** (#235): closes README item 1 for real. Fixes a stale README claim
  (OpenAI was already proven, the claim said otherwise) and proves the profile's actual remaining gap,
  OpenRouter, live. Every deployment in the `live-development` profile is now individually proven.

The PC-33/OR-9/PC-52 group above closes every item in the README's post-v1.0.0 punch list. The
personal-default proof coverage and documentation restructure are further hardening/cleanup on top of
that closed list, not new punch-list items.

## v1.0.0 — 2026-09-09

First versioned release. `1.0.0` marks a stable public contract for the workspace packages and a
reusable open-source package, not a production-infrastructure claim — see [Scope](README.md#scope)
in the README for exactly what is and is not covered.

All workspace packages move to `1.0.0` in lockstep: `governed-llm-gateway-contracts`,
`governed-llm-gateway-core`, `governed-llm-gateway-api`, `governed-llm-gateway-client`, and the
`governed-llm-gateway-console` frontend.

### Included

- **Core platform (Phases 0–13, complete):** PDP/PEP separation with the permanent invariant
  `Gateway allowed set ⊆ Policy Router authorized set`; provider-neutral contracts and model registry;
  deterministic operational ranking and explainability; runtime health, bounded retry and safe
  fallback; structured-output/tool-call normalization; streaming; metadata-only OpenTelemetry;
  a deterministic evaluation/benchmark framework; a thin typed client SDK; optional governance
  integration that can only narrow authorization, never widen it.
- **Real-project integrations (Phase 14, in progress):** two consumer integrations complete; a third
  (OpsLens) intentionally deferred pending its own repository stabilizing; two more not started, by
  explicit sequencing decision.
- **Local operational demo (OR-8, complete):** one-command, credential-free, operations-only local
  demo (Gateway Operations API, Console, OTel Collector, Tempo, Grafana).
- **Live-inference profiles:** `config/profiles/live-development/` (reviewed demo/development profile,
  two native providers) and `config/profiles/personal-default/` (the profile for calling the Gateway
  from your own projects, six providers, NVIDIA cost-preferred ranking).
- **Bounded operational-surface hardening (OR-9, in progress):** PC-34 through PC-51 close specific
  gaps on the surfaces this repository actually exposes (non-storable responses, header sanitization,
  bounded request bodies); production IAM/TLS/SSO, session handling, rate limiting and CSRF remain
  explicit future work, not silently assumed.
- **Product-readiness validation (OR-10, complete):** reproducible end-to-end validation against the
  repository's own documented quick starts; two focused security reviews (this session's new code, and
  the existing HTTP/adapter surface) with no findings in either pass; a consolidated Non-claims section;
  real Console/Grafana screenshots of the operations-only demo.

### Not included (see [Scope](README.md#scope) for the full list)

Production infrastructure (TLS termination, production IAM/OAuth/OIDC, browser session management,
rate limiting, CSRF policy), a third-party provider SLA, a benchmark of real production traffic, a
multi-tenant or remote deployment, and the remaining Phase 14 integrations.

See [`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md) for the full, continuously updated
project checkpoint this release is cut from.
