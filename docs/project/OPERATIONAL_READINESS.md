# Gateway Operational Readiness

This track is independent from Phase 14 consumer integrations. It turns the existing governed execution
core into a locally demonstrable operational platform without changing the permanent authorization
sequence or pulling forward OpsLens, RAGForge, or Verifiable AI Governance work.

## Authority boundary

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Operational readiness may add read models, telemetry export, dashboards, local infrastructure and a
read-only console. None of those surfaces may authorize a deployment, widen policy, resurrect a
rejected candidate, execute business tools, or mutate runtime policy.

Evidence is not authority. Telemetry is not authority. Health is not authority.

## OR-0 foundation audit

The September 2026 audit established the following baseline before product-readiness changes:

- Phase 9 OpenTelemetry instrumentation already exists on top of `a2a-otel-kit`;
- `gateway-core` pins `a2a-otel-kit==0.6.0`;
- gateway attributes pass through the kit sanitizer plus a gateway-specific allowlist;
- default telemetry is metadata-only;
- W3C trace propagation is covered across gateway/provider HTTP and SSE boundaries;
- provider-attempt retry/fallback events and streaming lifecycle telemetry already exist;
- Phase 10/11 benchmark evidence and later operational evidence are already separate from
  authorization;
- process-local health, process-local attempt recording, content-addressed sample batches and reviewed
  operational snapshots are intentionally distinct abstractions;
- the gateway repository did not yet contain a local Collector + Tempo + Grafana stack;
- the gateway repository did not yet contain a dedicated operations read model/API or React Gateway
  Console;
- Collector receipt verification existed as a reusable pattern in `a2a-otel-kit` but not yet as a
  gateway integration/e2e proof.

PC-15 subsequently added the pinned local Collector + Tempo + Grafana foundation. PC-16 added the
credential-free positive Collector receipt proof. PC-17 added optional executable-process ownership of
`Observability.configure()` / injection / shutdown while preserving the original metadata-only and
non-authoritative boundaries. PC-18 introduced the typed application-layer operations projection.
PC-19 composes that projection from the exact active registry, ranking policy and shared process-local
health state. PC-20 separates authenticated Gateway identity from workload authorization and adds an
explicit operations-read grant boundary. PC-21 binds that boundary to a deployment-owned secret-free
artifact, validates its principals against client-auth before secret resolution, and carries the same
authorization service into the governed service graph. PC-22 then exposes the first bounded authenticated
Operations HTTP endpoint, `GET /v1/ops/overview`, with authorization before snapshot reads and a reduced
aggregate response. PC-23 binds an optional explicit reviewed operational-evidence artifact during
secret-free startup. PC-24 adds the authenticated read-only `GET /v1/ops/deployments` catalog without
introducing mutation authority or detailed runtime counters. PC-25 adds the first React/TypeScript/Vite
Gateway Console foundation as a read-only consumer of those two already-reviewed Operations endpoints.

The audit also found documentation drift: the previous observability document still described Phase 9
runtime tracing as future work even though Phase 9 is already complete.

## Reuse boundary with a2a-otel-kit

`a2a-otel-kit` is the observability foundation, not the home for gateway domain concepts.

Reuse from the kit:

- `Observability` lifecycle;
- OTLP/HTTP export;
- W3C Trace Context propagation;
- deny-by-default attribute sanitization;
- metadata-safe structured events;
- flush/shutdown semantics;
- Collector configuration patterns;
- Tempo and Grafana local-demo patterns;
- positive Collector receipt verification;
- optional A2A/MCP trace continuity.

Keep in the gateway:

- model registry and registry provenance;
- policy authorization/enforcement;
- candidate eligibility/ranking and route explain;
- runtime health/circuit state;
- retry/fallback semantics;
- benchmark evidence;
- operational evidence/completeness;
- process composition and the decision to enable/inject the observability facade;
- operations read models/APIs;
- operations-surface authentication/authorization;
- Gateway Console.

The dependency direction remains:

```text
Gateway -> a2a-otel-kit -> OpenTelemetry/OTLP -> Collector -> backends
```

Do not add a Langfuse SDK to the gateway or to `a2a-otel-kit` for this track.

## Delivery sequence

The sequence is intentionally incremental; later items may be reordered when a concrete dependency
requires it, but authority/security boundaries take precedence over visual/demo convenience.

| Track | Scope | Current state |
| --- | --- | --- |
| OR-0 | current observability/product-readiness audit | baseline recorded |
| OR-1 | telemetry vocabulary hardening | active |
| OR-2 | local OTel Collector + Tempo + Grafana foundation | foundation + positive receipt complete |
| process activation | optional process-owned OTel lifecycle | complete in PC-17 |
| OR-3 | typed read-only operations read model | typed foundation + service-graph composition complete in PC-18/PC-19 |
| OR-4 | read-only Operations API | authenticated overview, evidence binding and deployment catalog implemented in PC-20..PC-24; broader read surfaces deferred |
| OR-5 | React/TypeScript/Vite Gateway Console | read-only overview + deployment-catalog foundation implemented in PC-25; broader console surfaces deferred |
| OR-6 | Grafana dashboards + trace correlation/deep links | not started |
| OR-7 | optional Langfuse OTLP fan-out | optional / not started |
| OR-8 | one-command deterministic local demo | not started |
| OR-9 | broader authentication/security hardening for operational surfaces | not started; minimum OR-4 access prerequisite pulled forward |
| OR-10 | final docs, screenshots, demo and product-readiness validation | not started |

OR-1 is split into small increments. Issue #83 declares the compatibility vocabulary and updates the
Phase 9 documentation before any external observability stack is added.

PC-15 and PC-16 are bounded OR-2 increments. PC-17 closes the separate process-owned observability
lifecycle prerequisite. PC-18 and PC-19 close the typed/read-model and service-composition prerequisites
for OR-3. PC-20 and PC-21 deliberately pull forward only the minimum authentication/configuration
boundary needed to prevent OR-4 from becoming a global unauthenticated catalog. PC-22 consumes those
boundaries for the first authenticated read-only endpoint. PC-23 adds explicit deployment-owned evidence
binding, and PC-24 adds the bounded deployment catalog. PC-25 consumes only those certified read surfaces
for the first console foundation. None of these increments implies that deployment detail, evidence detail,
routing-history persistence, Tempo query verification, Grafana visualization, dashboards, production
browser identity/session handling or later admin surfaces are complete.

## Read-only operations boundary

The operations surface is read-only and explicitly composed from typed gateway-owned data. A UI must not
inspect arbitrary internal objects or provider SDK state.

PC-18 introduces `OperationsReadModelService` and an immutable `OperationsSnapshot` in
`gateway-core/application`. The projection is built only from the validated `ModelRegistry`, effective
`RankingPolicy`, an explicit read-only health inspection port and an optional already-verified
`OperationalEvidenceSnapshot`.

PC-19 binds one `OperationsReadModelService` into `GovernedGatewayServices` using the exact active
registry and effective ranking policy already used by request execution. It wraps the same live
`InMemoryHealthTracker` in `InMemoryHealthInspectionAdapter`, so descriptive reads observe current
process state without creating another tracker or advancing the live circuit breaker.

The health view is explicitly `process_local`. `InMemoryHealthInspectionAdapter` evaluates health on an
isolated replica of the in-memory tracker so dashboard-style reads cannot materialize live state or
advance the live circuit breaker. Operational-evidence absence is represented as `not_supplied`; it is
never converted to zero requests, zero errors or a healthy-fleet claim.

PC-20 adds the minimum visibility authorization prerequisite before transport is attached. The existing
Gateway credential resolver can authenticate a `GatewayClientIdentity` without constructing a synthetic
workload request. `OperationsReadAccessPolicy` then requires an exact secret-free
`(client_id, environment)` grant. Workload allowlists do not imply administrative visibility, and an
operations-read grant does not imply model/deployment execution authority. Empty grants deny all.

PC-21 makes the grant deployment-owned without adding a new secret path. `OperationsReadAccessDocument`
is a closed JSON artifact containing only schema/config provenance and ordered exact principals. It is
loaded during the existing secret-free process stage and every principal is cross-validated against the
already-loaded Gateway client-auth identities before any client, Policy Router or provider credential
is read. Omitting the artifact is explicit deny-all. After validation, the runtime creates
`OperationsReadAccessService` from the same already-materialized `StaticGatewayClientContextResolver`
and carries that exact service instance into `GovernedGatewayServices`.

PC-22 attaches `GET /v1/ops/overview` from the service composition root. The adapter reuses
`X-Gateway-API-Key`, authorizes through the exact PC-21 service before calling the PC-19 read model, and
returns sanitized 401/403/503 failures. Its response intentionally exposes only registry/ranking
provenance, aggregate process-local health counts, and operational-evidence availability state. It does
not expose principal/grant data, individual deployment/model/provider identities, per-deployment counters,
credential references, PDP/provider internals, or mutable runtime state. PC-22 introduces no `POST`,
`PUT`, `PATCH`, or `DELETE` operation under `/v1/ops/*`; mutation authority remains absent.

PC-23 binds an optional explicit `OperationalEvidenceSnapshot` during the secret-free startup stage,
cross-validates its deployment IDs against the active registry and fixes that exact snapshot into the
Operations snapshot reader for the process lifetime. Omission remains explicit `not_supplied`; configured
valid evidence changes only the bounded overview availability state to `available`. Evidence remains
descriptive and is not consumed by authorization, ranking, health, retry/fallback or readiness.

PC-24 attaches `GET /v1/ops/deployments` through the same Operations access service and snapshot reader.
It returns deterministic registry metadata plus coarse process-local `status`/`circuit_state`, while
excluding mutable execution counters, latency, provider endpoints, credential references, principal/grant
metadata and operational-evidence records.

See `docs/project/OPERATIONS_READ_MODEL.md` for the typed projection/non-claims,
`docs/project/OPERATIONS_ACCESS.md` for the operations visibility boundary,
`docs/project/OPERATIONS_ACCESS_ARTIFACT.md` for the deployment artifact/bootstrap contract,
`docs/project/OPERATIONAL_EVIDENCE_BINDING.md` for PC-23 evidence binding, and
`docs/project/OPERATIONS_HTTP.md` for the HTTP transport/response contracts.

The implemented Operations endpoints at PC-24 are:

```text
GET /v1/ops/overview
GET /v1/ops/deployments
```

Possible later endpoints remain product-readiness targets rather than contracts:

```text
GET /v1/ops/deployments/{deployment_id}
GET /v1/ops/evidence
GET /v1/ops/evidence/operational
GET /v1/ops/evidence/benchmarks
GET /v1/ops/routing/recent
GET /v1/ops/system
```

No direct mutation endpoint belongs in the first version. In particular, do not add unaudited buttons
or APIs for deployment disablement, circuit reset, registry/policy changes, or evidence promotion.

## Gateway Console boundary

PC-25 introduces `apps/gateway-console` as a bounded browser consumer of the two existing Operations GET
endpoints. It uses React, strict TypeScript and Vite with a committed npm lockfile and Node.js 24 LTS in
frontend CI.

The browser sends `X-Gateway-API-Key` only after an operator explicitly connects. The credential remains
in React component memory for the active page lifetime and is cleared on disconnect; the console does not
persist it to `localStorage`, `sessionStorage`, cookies, URLs/query strings, generated configuration or
repository files.

Development requests remain same-origin from the browser perspective through the Vite `/v1` proxy to
the local Gateway process. PC-25 does not introduce a BFF, token exchange, session service or production
identity architecture.

The console performs closed-shape runtime validation before treating Operations JSON as trusted display
data. Unexpected fields, unsupported enum values, invalid counts/dates/context sizes, or disagreement
between overview and deployment-catalog sizes fail closed into bounded operator-facing errors. Sanitized
backend 401/403/503 codes are mapped without rendering raw server exceptions.

The UI displays registry/ranking provenance, aggregate health, operational-evidence availability and the
bounded deployment catalog. `process_local` remains visible and is not relabeled as fleet/global state.
No fake metrics, fake traces, fake costs, fake evidence, inferred authorization reasons or inferred routing
decisions are rendered. The console contains no mutation control and makes no direct provider, PDP, Tempo,
Grafana or Langfuse call.

See `docs/project/GATEWAY_CONSOLE.md` for the local execution, credential, runtime-validation and CI
contract.

## Local observability target

The local infrastructure foundation is now:

```text
gateway-api
    │
    └── a2a-otel-kit -> OTLP/HTTP -> otel-collector -> tempo -> grafana
```

PC-15 provides the checked-in Collector, Tempo and Grafana Compose topology. PC-16 separately proves
that a known metadata-only Gateway span can reach an isolated Collector receipt surface. PC-17 owns
optional observability configuration at the executable process boundary and injects the configured
facade through the existing deployment/service composition path.

Observability is disabled by default. Explicit endpoint/environment process arguments enable it. A
runtime configuration failure degrades to null telemetry; a configured facade is shut down best-effort
when the runner returns or activation/runner fails. No telemetry backend is probed for startup or
readiness.

Langfuse may be added later as an optional downstream Collector/OTLP destination when its current
integration contract is reviewed. Its availability must never affect gateway inference.

The local stack uses pinned image versions, loopback host bindings, `no-new-privileges`, dropped Linux
capabilities where compatible, read-only configuration mounts and no hardcoded secrets. Demo-only
Grafana authentication relaxations are documented as local only and must not be presented as a
production configuration.

## Evidence presentation rules

The console/dashboard must not fabricate metrics or reason codes.

When data is absent, the backend read model must represent absence explicitly. Process-local samples
must not be labeled fleet-complete. PC-23 evidence binding does not establish freshness or fleet
completeness, and PC-24 deployment health remains explicitly `process_local`. PC-25 preserves those
claims in the first UI rather than deriving stronger semantics in the browser. Cost is shown only when
the gateway has real cost evidence. Routing visualization must display gateway-produced reason codes
rather than deriving authorization or health reasons in the frontend.

Trace views in later Gateway Console increments remain a correlation surface, not a replacement for
Tempo/Grafana or another trace explorer.

## CI boundary

Default CI remains deterministic and credential-free:

- no real provider API required;
- no SaaS observability backend required;
- no secret required;
- no Langfuse Cloud dependency;
- live-provider tests remain opt-in.

PC-16 adds an explicit Docker-based `collector-receipt` integration workflow. It starts only a local
receipt Collector, performs a bounded startup probe, emits one metadata-only span through
`a2a-otel-kit`, requires positive appended receipt evidence and always tears the Collector down.
Exporter `flush()` success alone is not sufficient proof of Collector receipt.

PC-17 lifecycle contracts do not open a socket or require a Collector. They inject deterministic test
doubles at the process boundary to prove default-disabled behavior, explicit settings, degradation,
injection and shutdown semantics.

PC-18 read-model contracts are credential-free and network-free. They prove deterministic projection,
explicit evidence absence, exact ranking/registry provenance and non-mutating inspection of
process-local health. PC-19 service-composition contracts prove that the projection consumes the active
registry/ranking and same process-local health tracker without new secret reads or an HTTP route.
PC-20 operations-access contracts reuse already-materialized test credentials, prove no request-time
secret re-resolution, preserve workload authorization semantics and verify fail-closed deny-all and
ungranted-principal behavior without network or PDP/provider access. PC-21 artifact/bootstrap contracts
prove closed-schema deterministic grants, cross-artifact rejection before all secret resolvers,
deployment-root path containment, omitted deny-all behavior and exact runtime service-instance reuse.
PC-22 HTTP contracts prove missing/invalid/ungranted callers cannot read a snapshot, authorization occurs
before successful reads, bounded aggregation excludes deployment/principal details, and mismatched
aggregates fail closed. PC-23 activation contracts prove malformed or registry-incompatible evidence
fails before secret lookup, omission remains `not_supplied`, and configured evidence reaches the real
overview as `available` without request-time rediscovery. PC-24 contracts prove the deployment catalog
uses the same authorization-before-snapshot order, preserves typed ordering, exposes only approved catalog
fields plus coarse process-local health, excludes mutable counters/secrets/evidence, maps snapshot failures
to sanitized 503, and fails route composition before partial attachment on owned-path conflicts. No live
provider, PDP call, or external secret/backend is required by the Operations request path.

PC-25 adds the credential-free, path-scoped `console-quality` workflow. On Node.js 24 LTS it requires a
locked install, strict TypeScript checking, deterministic unit tests, a console security-boundary scan and
a production Vite build. The boundary scan rejects browser persistence APIs, mutation request literals and
unreviewed `/v1/ops/*` paths in console source. Frontend CI does not replace or weaken the Python quality,
collector-receipt or observability-compose gates.

Changes to the shared observability/readiness documentation trigger both the positive-receipt and local
Compose validation workflows so the documented contract and the executable infrastructure are
validated on the same candidate SHA.

## Next slice

With the authenticated overview, explicit reviewed-evidence binding, bounded deployment catalog and first
read-only Gateway Console foundation established, the next product-readiness increment must be selected
from a concrete remaining gap rather than by adding speculative admin capabilities.

Likely candidates now sit outside the basic console foundation: OR-6 trace correlation/Grafana dashboard
work or OR-8 deterministic demo orchestration. Each requires a fresh audit of the existing trace/query and
local-process topology before an issue is opened. Deployment detail, evidence detail and recent routing
history still require separate information-disclosure, completeness or persistence contracts before an
endpoint or screen is added.

Recent routing history remains a separate persistence/read-model concern and must not be fabricated
from current health or ranking configuration. Fleet aggregation, external IAM and mutations remain
separate increments. Phase 14 consumer integrations remain frozen by their sequencing guard.

## Completion rule

No OR increment is considered complete until its pull request is merged and the corresponding
post-merge `main` CI is green. Product-ready demo status requires the full operational stack, read-only
operations surfaces, console, trace correlation, reproducible local demo, security review,
documentation and final post-merge validation.
