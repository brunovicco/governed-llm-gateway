# Current State

Last updated: 2026-08-31

## Phase status

| Phase | Status |
|---|---|
| Phase 0 — Architecture Gate | COMPLETE BASELINE |
| Phase 1 — Policy Model Router generalization | COMPLETE (`policy-model-router` PR #20) |
| Phase 2 — Contracts and Model Registry | COMPLETE (`governed-llm-gateway` PR #1) |
| Phase 3 — Provider Execution Foundation | COMPLETE (`governed-llm-gateway` PR #2) |
| Phase 4 — Policy Router integration | COMPLETE (`governed-llm-gateway` PR #3) |
| Phase 5 — Deterministic Operational Ranking and Explainability | COMPLETE (`governed-llm-gateway` PR #4) |
| Phase 6 — Runtime Health, Retry and Safe Fallback | IMPLEMENTED — IN REVIEW |
| Phase 7+ | NOT STARTED |

## Durable architecture baseline

- uv workspace with explicit `gateway-contracts`, `gateway-core`, `gateway-client`, and `gateway-api`
  boundaries;
- provider-neutral contracts/domain and provider-specific infrastructure isolated in adapters;
- Policy Model Router remains the PDP; the gateway remains the PEP plus operational selector;
- core invariant: `Gateway allowed set ⊆ Policy Router authorized set`;
- metadata-only evidence by default and fail-closed handling of untrusted configuration/external
  responses.

## Completed through Phase 5

Phase 1 generalized Policy Model Router workload/model-group identifiers. Phase 2 established the
strict model registry and deterministic registry digest. Phase 3 added provider execution ports and
OpenAI Responses, OpenAI-compatible, Gemini `generateContent`, and Anthropic Messages adapters.
Phase 4 bound the gateway to Policy Model Router `POST /route` schema `1.0`, validated prompt-free
policy provenance, and built the authorized registry candidate set. Phase 5, merged through PR #4,
added deterministic eligibility/ranking, ADR-0006, ranking-policy provenance, and authenticated
`POST /v1/route/explain` without provider inference.

Phase 5 static score inputs remain configuration evidence, not benchmark evidence.
`benchmark_snapshot_id` stays unset until later evaluation/evidence-driven ranking phases.

## Phase 6 implemented

Phase 6 adds runtime resilience strictly inside the already-authorized/ranked candidate sequence.

Delivered:

- ADR-0007 defines fallback/replay safety semantics;
- `RetryPolicy` bounds attempts per deployment, fallback count, exponential backoff, maximum delay,
  and deterministic jitter;
- provider `Retry-After` is honored only within the gateway's maximum delay;
- retry targets the same concrete deployment;
- fallback targets only the next deployment already present in the Phase 5 ranked alternatives;
- all bounded fallback candidates are validated against the PDP-authorized logical model group before
  the first provider call;
- only normalized retryable `rate_limit`, `timeout`, `unavailable`, and `transport` failures trigger
  automatic replay;
- permanent provider/configuration failures fail closed without cross-provider fallback;
- `FallbackSafetyState` blocks automatic replay after observed output, external side effect, or opaque
  provider continuation/reasoning state;
- `InMemoryHealthTracker` maintains per-process, per-deployment execution health and circuit state;
- circuit lifecycle: `CLOSED → OPEN → HALF_OPEN → CLOSED`;
- transient threshold opens the circuit, cooldown enables half-open probing, success closes it, and a
  transient half-open failure reopens it;
- runtime health can only remove candidates from Phase 5 eligibility;
- open circuit produces `circuit_breaker_open`;
- unhealthy or missing active runtime-health snapshot produces `deployment_unhealthy`;
- runtime health remains distinct from Phase 5 static ranking weights/scores;
- successful resilient execution records actual deployment progression in
  `RoutingProvenance.fallback_sequence` and same-deployment retries in metadata-only
  `ExecutionAttempt` evidence.

## Phase 6 acceptance evidence

Normative acceptance and additional boundary tests prove:

- 429 retries the same deployment;
- timeout failures retry and update timeout/transient health counters;
- 5xx/unavailable and transport failures can fall back to the next authorized ranked deployment;
- permanent errors do not retry or fall back;
- retry and fallback counts are bounded exactly;
- fallback never widens the PDP-authorized model group;
- an out-of-group fallback candidate fails before any provider call;
- missing provider-adapter configuration fails closed rather than silently choosing another provider;
- side-effect/output/opaque-state boundaries block automatic replay before a provider call;
- an open circuit blocks provider execution and removes the deployment from ranking eligibility;
- half-open recovery and half-open transient failure behavior are deterministic;
- active runtime-health filtering fails closed when a deployment snapshot is missing;
- retry delay is reconstructable for identical request/deployment/policy inputs.

## Current validation

Read-only GitHub Actions run `33455984065` passed on head
`96089a21ee2b47ccecdcfa6d3a52f5e2e2248ad4` after Phase 6 resilience boundary tests were complete:

- 111 tests PASS;
- 84.11% total coverage (minimum 80%);
- Ruff lint/format PASS;
- mypy PASS across 54 source files;
- Bandit PASS with no identified issues;
- pip-audit PASS with no known vulnerabilities;
- architecture check PASS;
- secret scan PASS;
- Phase 0 regression gate PASS;
- GitHub Actions permissions: `contents: read`.

The known Starlette TestClient `httpx`/`httpx2` deprecation warning remains non-blocking and unrelated
to Phase 6 behavior.

## Phase 6 scope decisions

- circuit-breaker state is initially per process; shared Redis state is deferred until operational
  evidence justifies it;
- runtime health is mutable operational state and does not alter Phase 5 static weighted scores;
- provider timeout is bounded per attempt;
- Phase 6 does not silently reinterpret the ranking/policy `max_latency_ms` constraint as a total
  cross-retry execution deadline; a total execution budget requires an explicit future contract;
- Phase 6 is text-generation resilience only. Structured-output/tool replay semantics remain Phase 7
  and streaming replay semantics remain Phase 8.

## Explicitly deferred

- structured-output/tool normalization and execution-boundary replay semantics (Phase 7);
- streaming and partial-output cancellation/replay semantics (Phase 8);
- OpenTelemetry runtime via `a2a-otel-kit` (Phase 9);
- benchmark/evaluation framework (Phase 10);
- benchmark-derived ranking evidence (Phase 11);
- thin client HTTP transport completion (Phase 12);
- signed Verifiable AI Governance runtime authorization (Phase 13).

## Next step

Complete independent architecture/security review and merge of Phase 6. After merge, start Phase 7 —
Structured Output and Tool Normalization without weakening the fallback safety boundary established in
ADR-0007.
