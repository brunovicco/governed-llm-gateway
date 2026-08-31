# Current State

Last updated: 2026-08-31

## Phase status

| Phase | Status |
|---|---|
| Phase 0 — Architecture Gate | COMPLETE BASELINE |
| Phase 1 — Policy Model Router generalization | COMPLETE (`policy-model-router` PR #20) |
| Phase 2 — Contracts and Model Registry | COMPLETE (`governed-llm-gateway` PR #1) |
| Phase 3 — Provider Execution Foundation | IMPLEMENTED — IN REVIEW |
| Phase 4+ | NOT STARTED |

## Phase 0 delivered

- uv workspace root with four explicit members;
- provider-neutral immutable contract baseline;
- explicit domain/application/adapters separation and authorization invariant guard;
- durable project source documents and ADR-0001 through ADR-0005;
- trusted/untrusted attribute model, PDP/PEP contract draft, threat model, and architecture gates.

## Phase 1 dependency completed

`policy-model-router` was generalized so workload and logical model-group identifiers are policy-defined
rather than credit-desk-specific closed enums. Unknown workloads remain fail-closed and deterministic
policy provenance is preserved. The gateway does not implement a legacy compatibility translation.

## Phase 2 completed

- provider-neutral `Capability` and `Modality` vocabularies;
- immutable model-registry domain objects separating provider, model, deployment, and logical group;
- strict safe-YAML loading with duplicate-key, closed-schema, and semantic validation;
- versioned pricing metadata with explicit unknown-pricing representation;
- deterministic canonical representation and SHA-256 registry provenance digest;
- checked-in empty registry so no provider/model approval is implied by configuration.

## Phase 3 implemented

- provider-neutral `ProviderPort`, `ProviderRequest`, `ProviderResponse`, `ProviderUsage`,
  `ProviderError`, and stable provider error categories;
- bounded HTTPS/JSON transport using the Python standard library and an injectable transport port;
- native OpenAI Responses adapter;
- explicit OpenAI-compatible chat-completions adapter with provider quirks kept configurable;
- native Google Gemini `generateContent` adapter;
- native Anthropic Messages adapter;
- provider-native system/message mapping while preventing provider response classes from escaping the
  adapter boundary;
- token-usage extraction, request timeouts, retryability classification, and bounded `Retry-After`
  metadata;
- sanitized provider/transport failures that do not retain raw non-2xx bodies, credentials,
  authorization headers, cookies, or arbitrary provider response headers;
- contract tests using fake transports only; CI requires no provider credential and makes no live
  provider request;
- Phase 0 regression gate evolved from the obsolete repository-wide provider ban to the durable
  contracts/domain boundary enforced by AST-based architecture checks.

## Gemini API decision

Google recommends the Interactions API for new development as of June 2026, while `generateContent`
remains fully supported. The Phase 3 adapter intentionally uses `generateContent` because the current
provider-neutral request carries canonical conversation messages but does not retain Gemini-generated
Interaction steps. Stateless Interactions requires those model-generated steps to be preserved and
resent exactly; inventing them from canonical assistant text would be lossy and unsafe. A future
Interaction adapter requires an explicit provider-state contract rather than a silent translation.

## Phase 3 validation

The read-only GitHub Actions quality workflow passes with:

- 52 tests;
- 85.59% total coverage (minimum 80%);
- Ruff lint/format PASS;
- mypy PASS across 36 source files;
- Bandit PASS with no identified issues;
- pip-audit PASS with no known vulnerabilities;
- architecture check PASS;
- secret scan PASS;
- Phase 0 regression gate PASS.

## Explicitly deferred

- Policy Model Router runtime/API integration (Phase 4);
- operational ranking and explainability (Phase 5);
- retries, fallback runtime, and circuit breakers (Phase 6);
- structured-output and tool normalization (Phase 7);
- streaming (Phase 8);
- OpenTelemetry runtime (Phase 9);
- benchmark/evaluation-driven ranking;
- FastAPI endpoint implementation and client HTTP transport beyond their roadmap phases.

## Next phase

After Phase 3 review/merge, start Phase 4 — PDP Authorization Integration. The gateway may consume
only deterministic Policy Model Router authorization and must continue enforcing:

`Gateway allowed set ⊆ Policy Router authorized set`.
