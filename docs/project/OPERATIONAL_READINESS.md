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
health state. PC-20 begins the OR-4 security prerequisite by separating authenticated Gateway identity
from workload authorization and adding an explicit secret-free operations-read grant boundary before
any operations HTTP route is exposed.

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
| OR-4 | read-only Operations API | access prerequisite active in PC-20; HTTP not started |
| OR-5 | React/TypeScript/Vite Gateway Console | not started |
| OR-6 | Grafana dashboards + trace correlation/deep links | not started |
| OR-7 | optional Langfuse OTLP fan-out | optional / not started |
| OR-8 | one-command deterministic local demo | not started |
| OR-9 | broader authentication/security hardening for operational surfaces | not started; minimum OR-4 access prerequisite pulled forward |
| OR-10 | final docs, screenshots, demo and product-readiness validation | not started |

OR-1 is split into small increments. Issue #83 declares the compatibility vocabulary and updates the
Phase 9 documentation before any external observability stack is added.

PC-15 and PC-16 are bounded OR-2 increments. PC-17 closes the separate process-owned observability
lifecycle prerequisite. PC-18 and PC-19 close the typed/read-model and service-composition prerequisites
for OR-3. PC-20 deliberately pulls forward only the minimum access-control primitive needed to prevent
OR-4 from becoming a global unauthenticated catalog. None of these increments implicitly completes an
Operations API, Tempo query verification, Grafana visualization, dashboards or any later operations
surface.

## Read-only operations boundary

The first operations surface must be read-only and explicitly composed from typed gateway-owned data.
A UI must not inspect arbitrary internal objects or provider SDK state.

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
Gateway credential resolver can now authenticate a `GatewayClientIdentity` without constructing a
synthetic workload request. `OperationsReadAccessPolicy` then requires an exact secret-free
`(client_id, environment)` grant. Workload allowlists do not imply administrative visibility, and an
operations-read grant does not imply model/deployment execution authority. Empty grants deny all.

See `docs/project/OPERATIONS_READ_MODEL.md` for the typed projection/non-claims and
`docs/project/OPERATIONS_ACCESS.md` for the operations visibility boundary.

Candidate future endpoints include:

```text
GET /v1/ops/overview
GET /v1/ops/deployments
GET /v1/ops/deployments/{deployment_id}
GET /v1/ops/evidence
GET /v1/ops/evidence/operational
GET /v1/ops/evidence/benchmarks
GET /v1/ops/routing/recent
GET /v1/ops/system
```

This list is a product-readiness target, not an implemented API contract yet.

No direct mutation endpoint belongs in the first version. In particular, do not add unaudited buttons
or APIs for deployment disablement, circuit reset, registry/policy changes, or evidence promotion.

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

The future console/dashboard must not fabricate metrics or reason codes.

When data is absent, the backend read model must represent absence explicitly. Process-local samples
must not be labeled fleet-complete. Cost is shown only when the gateway has real cost evidence. Routing
visualization must display gateway-produced reason codes rather than deriving authorization or health
reasons in the frontend.

Trace views in the Gateway Console remain a correlation surface, not a replacement for Tempo/Grafana
or another trace explorer.

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
ungranted-principal behavior without network or PDP/provider access.

Changes to the shared observability/readiness documentation trigger both the positive-receipt and local
Compose validation workflows so the documented contract and the executable infrastructure are
validated on the same candidate SHA.

## Next slice

Before OR-4 attaches an HTTP endpoint, the next bounded dependency is a deployment-owned, secret-free
operations-access artifact/loader and bootstrap binding that selects the explicitly granted
`GatewayClientIdentity` principals. It must validate that configured principals correspond to the
already-loaded Gateway client-auth identities without resolving credentials a second time.

Only after that configuration boundary is validated should a first read-only endpoint such as
`GET /v1/ops/overview` be attached to the PC-19 `OperationsReadModelService` behind the PC-20
`OperationsReadAccessService`. Recent routing history remains a separate persistence/read-model concern
and must not be fabricated from current health or ranking configuration.

## Completion rule

No OR increment is considered complete until its pull request is merged and the corresponding
post-merge `main` CI is green. Product-ready demo status requires the full operational stack, read-only
operations surfaces, console, trace correlation, reproducible local demo, security review,
documentation and final post-merge validation.
