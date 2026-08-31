# Current State

Last updated: 2026-08-31

## Phase status

| Phase | Status |
|---|---|
| Phase 0 — Architecture Gate | COMPLETE BASELINE |
| Phase 1 — Policy Model Router generalization | COMPLETE (`policy-model-router` PR #20) |
| Phase 2 — Contracts and Model Registry | COMPLETE (`governed-llm-gateway` PR #1) |
| Phase 3 — Provider Execution Foundation | COMPLETE (`governed-llm-gateway` PR #2) |
| Phase 4 — Policy Router integration | IMPLEMENTED — IN REVIEW |
| Phase 5+ | NOT STARTED |

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

## Phase 3 completed

Phase 3 was merged through `governed-llm-gateway` PR #2.

- provider-neutral `ProviderPort`, request/response/usage types, and stable provider error categories;
- bounded HTTPS/JSON transport using the Python standard library and an injectable transport port;
- native OpenAI Responses, Google Gemini `generateContent`, and Anthropic Messages adapters;
- explicit OpenAI-compatible chat-completions adapter with provider quirks configurable;
- provider-native system/message mapping without provider response classes escaping adapters;
- token-usage extraction, request timeouts, retryability classification, and bounded `Retry-After`;
- sanitized provider/transport failures without raw non-2xx bodies, credentials, cookies, or
  arbitrary response headers;
- fake-transport contract tests and credential-free CI.

## Phase 4 implemented

Phase 4 binds the gateway to the deterministic Policy Model Router `POST /route` wire schema `1.0`
without making the router a gateway domain dependency.

Delivered:

- `PolicyDecisionPort` accepts only prompt-free `PolicyRequestMetadata`, making message leakage to the
  PDP structurally unavailable through the application boundary;
- trusted `EffectivePolicyContext` supplies client identity, workload, risk, classification, and
  environment; caller-supplied identity/risk/classification cannot downgrade those facts;
- the trusted `client_id` selects the configured PDP API key and maps to `agent_name`;
- gateway `request_id` is used as Phase 4 correlation identity for router `workflow_id` and `task_id`;
- caller latency/cost ceilings can only narrow gateway-owned projection defaults;
- accepted Policy Model Router decisions are validated against exact schema fields, request
  correlation, trusted environment, policy digest, and provenance;
- `422 no_viable_model_group` is normalized as an explicit denial only when its rejection provenance
  matches the request ID, workload, and trusted environment;
- authentication/authorization/rate-limit/server/transport/timeout/malformed-response paths fail
  closed before provider execution;
- `authorized_registry_candidates` intersects registry deployments with the PDP-authorized logical
  model group and performs no Phase 5 operational filtering/ranking;
- `execute_selected` proves the PEP boundary by checking registry membership and authorized logical
  group before invoking a provider;
- tests prove PDP rejection and authorization-boundary violations result in zero provider calls;
- the provider request contains model/messages/output/timeout execution data only, not PDP-only
  policy metadata.

## Phase 4 contract decisions

The gateway does not silently reinterpret semantically different fields:

- `requirements.min_context_tokens` is a model-capability requirement, not a prompt token estimate;
  it is therefore not mapped to Policy Model Router `context_tokens_estimated`;
- Policy Model Router API 1.0 models tool-calling requirements on the policy workload rule and has no
  per-request `tool_calling_required` field; the gateway does not invent one;
- signed runtime authorization required by some Policy Model Router deployments belongs to the later
  Verifiable AI Governance integration. Until that integration exists, a router 403 fails closed.

Phase 4 does not implement operational model choice. Ranking/filtering inside the authorized group is
Phase 5.

## Phase 4 validation

The read-only GitHub Actions quality workflow passes on the code-complete Phase 4 implementation:

- 73 tests;
- 83.38% total coverage (minimum 80%);
- Ruff lint/format PASS;
- mypy PASS across 41 source files;
- Bandit PASS with no identified issues;
- pip-audit PASS with no known vulnerabilities;
- architecture check PASS;
- secret scan PASS;
- Phase 0 regression gate PASS.

GitHub Actions push run: `33416554085`.

## Explicitly deferred

- deterministic operational eligibility/ranking and route explainability (Phase 5);
- retries, fallback runtime, and circuit breakers (Phase 6);
- structured-output and tool normalization (Phase 7);
- streaming (Phase 8);
- OpenTelemetry runtime via `a2a-otel-kit` (Phase 9);
- benchmark/evaluation-driven ranking;
- FastAPI endpoint implementation and client HTTP transport beyond their roadmap phases;
- signed Verifiable AI Governance runtime authorization (Phase 13).

## Next phase

After Phase 4 independent review/merge, start Phase 5 — deterministic operational ranking and
explainability. Every Phase 5 filter/ranking step must preserve:

`Gateway allowed set ⊆ Policy Router authorized set`.
