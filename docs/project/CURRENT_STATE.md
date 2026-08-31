# Current State

Last updated: 2026-08-31

## Phase status

| Phase | Status |
|---|---|
| Phase 0 — Architecture Gate | COMPLETE BASELINE |
| Phase 1 — Policy Model Router generalization | NOT STARTED |
| Phase 2 — Contracts and Model Registry | NOT STARTED |
| Phase 3+ | NOT STARTED |

## Phase 0 delivered

- uv workspace root with four explicit members;
- `gateway-contracts` immutable provider-neutral draft contracts;
- `gateway-core` domain/application/adapters separation and authorization invariant guard;
- `gateway-client` ownership boundary without HTTP implementation;
- `gateway-api` composition-root namespace without FastAPI/runtime dependency;
- `AGENTS.md`, `.codex/`, agent skill, and minimal `CLAUDE.md` reviewer file;
- durable project source documents;
- ADR-0001 through ADR-0005 accepted;
- trusted/untrusted attribute model;
- PDP/PEP interface draft;
- model registry and ranking policy drafts;
- threat model and security model drafts;
- architecture and Phase 0 validation scripts/tests;
- original source roadmap preserved at `SOURCE_ROADMAP.txt`.

## Architecture Gate decisions closed in this baseline

1. Caller security metadata is a claim, not automatically authoritative. Authenticated workload
   identity and deterministic policy determine effective context.
2. PDP authorization is immutable input to gateway selection. Gateway filtering is monotonic:
   authorization may only become narrower.
3. `/v1/models`, `/v1/route/explain`, `/metrics`, and administrative/readiness surfaces require
   explicit authorization in their implementation phases and must not leak global registry/policy
   internals to unprivileged clients.
4. Fallback is allowed only when replay is safe and stays inside authorization. Side effects or
   opaque provider state block cross-provider continuation unless an explicit replay strategy exists.
5. Routing provenance minimally binds policy decision/digest, registry digest, ranking policy
   version, benchmark snapshot (when used), selected deployment, rejections, and fallback sequence.
6. Pricing is temporal registry/evaluation metadata. Selection must use a versioned pricing snapshot;
   unknown/stale pricing cannot silently satisfy a hard cost ceiling.

## Explicitly deferred

- provider SDKs and live inference;
- FastAPI endpoint implementation;
- model registry loader/validation/digest implementation (Phase 2);
- Policy Model Router API integration (Phase 4 after its Phase 1 generalization);
- retries, fallback runtime, circuit breakers, streaming, OpenTelemetry runtime, benchmarks;
- client HTTP transport.

## Next phase

Phase 1 is performed in the existing `policy-model-router` repository. Generalize workload and
logical model-group vocabularies while preserving deterministic fail-closed decisions and policy
provenance. The gateway must not implement a compatibility translation to the legacy credit-desk
vocabulary.
