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
| Phase 5 — Deterministic Operational Ranking and Explainability | IMPLEMENTED — IN REVIEW |
| Phase 6+ | NOT STARTED |

## Durable architecture baseline

- uv workspace with explicit `gateway-contracts`, `gateway-core`, `gateway-client`, and `gateway-api`
  boundaries;
- provider-neutral contracts/domain and provider-specific infrastructure isolated in adapters;
- Policy Model Router remains the PDP; the gateway remains the PEP plus operational selector;
- core invariant: `Gateway allowed set ⊆ Policy Router authorized set`;
- metadata-only evidence by default and fail-closed handling of untrusted configuration/external
  responses.

## Phase 1 through Phase 4 completed

Phase 1 generalized Policy Model Router workload/model-group identifiers. Phase 2 established the
strict model registry and deterministic registry digest. Phase 3 added provider execution ports and
OpenAI Responses, OpenAI-compatible, Gemini `generateContent`, and Anthropic Messages adapters.
Phase 4, merged through PR #3, bound the gateway to Policy Model Router `POST /route` schema `1.0`,
projected trusted prompt-free policy metadata, validated authorization provenance, intersected the
registry with the authorized logical model group, and proved that PDP denial or out-of-authorization
selection results in zero provider calls.

## Phase 5 implemented

Phase 5 implements deterministic operational ranking only inside the Phase 4 authorized candidate
set.

Delivered:

- ADR-0006 defines deterministic candidate ranking and Phase 5 evidence semantics;
- strict versioned `ranking_policy.yaml` with safe YAML loading, duplicate-key rejection,
  closed-schema validation, semantic validation, canonicalization, and SHA-256 digest;
- workload-specific `Decimal` weights for quality, reliability, latency, cost, and availability that
  must sum exactly to `1`;
- static versioned deployment score records plus expected-latency planning metadata;
- static eligibility filtering before scoring for deployment enabled state, trusted environment/data
  allowance, required capabilities, context capacity, ranking evidence, pricing evidence, projected
  cost ceiling, and expected-latency ceiling;
- unknown pricing and missing ranking inputs fail closed instead of becoming free/default scores;
- deterministic score ordering with ascending `deployment_id` tie-break;
- selection provenance including PDP provenance, model-registry digest, ranking-policy
  version/digest, score snapshot ID, selected provider/model/deployment, and machine-readable
  rejection reasons;
- deterministic routing decision IDs derived only from canonical metadata/ranking evidence, never
  prompt content;
- `benchmark_snapshot_id` remains unset because Phase 5 static score inputs are not empirical
  benchmark evidence;
- `RouteExplainService` composes PDP authorization, eligibility, ranking, and explanation without
  provider inference;
- authenticated `POST /v1/route/explain` in `gateway-api`, with a prompt-free closed request schema,
  trusted context resolver, deterministic response, and no provider call;
- FastAPI/Pydantic remain confined to the API composition boundary;
- Phase 5 rejects registry drift after authorization, candidates outside the PDP group, and ambiguous
  multi-group authorization before ranking;
- the Phase 0 regression gate is frozen to the five contract modules from the original
  `phase-0-architecture-gate` tag, while all current/future contract tests run through pytest.

## Phase 5 acceptance evidence

The four normative Phase 5 acceptance criteria are covered:

- same inputs produce the same ranking and deterministic routing decision ID;
- ineligible deployments cannot win because filtering precedes scoring;
- equal scores resolve deterministically by `deployment_id`;
- `POST /v1/route/explain` is implemented and performs no model inference.

Additional authority-boundary tests prove that ranking fails closed when:

- the registry digest no longer matches the registry authorized in Phase 4;
- a candidate outside the PDP-authorized logical group reaches the Phase 5 boundary;
- a decision contains more than one authorized logical group;
- the explain API receives an unsupported schema version, non-dotted workload identifier, or prompt
  field.

## Phase 5 validation

Read-only GitHub Actions push run `33453828758` passed on head
`090f7f250c23c69b87e1c71c34ca27f0ec67a770` after the acceptance/boundary tests were complete:

- 94 tests PASS;
- 83.43% total coverage (minimum 80%);
- Ruff lint/format PASS;
- mypy PASS across 49 source files;
- Bandit PASS with no identified issues;
- pip-audit PASS with no known vulnerabilities;
- architecture check PASS;
- secret scan PASS;
- Phase 0 regression gate PASS;
- GitHub Actions permissions: `contents: read`.

There is one non-blocking Starlette TestClient deprecation warning about `httpx`; it is not a Phase 5
functional/security failure and should be handled separately unless a later dependency-maintenance
change requires it.

## Phase 5 scope decisions

- Phase 5 uses static/versioned ranking inputs. It does not claim benchmark-derived quality evidence.
- Expected latency is configuration evidence, not live provider health.
- Provider/deployment health and circuit-breaker state belong to Phase 6.
- Retry/fallback semantics belong to Phase 6 and must remain inside PDP authorization.
- The explain endpoint is an authenticated metadata-only surface; it does not accept messages and does
  not expose a global model inventory.

## Explicitly deferred

- runtime health, bounded retry, fallback, and circuit breakers (Phase 6);
- structured-output/tool normalization (Phase 7);
- streaming (Phase 8);
- OpenTelemetry runtime via `a2a-otel-kit` (Phase 9);
- benchmark/evaluation framework (Phase 10);
- benchmark-derived ranking evidence (Phase 11);
- thin client HTTP transport completion (Phase 12);
- signed Verifiable AI Governance runtime authorization (Phase 13).

## Next step

Complete independent review and merge of Phase 5. After merge, start Phase 6 — Resilience. Phase 6
must preserve the same authority invariant: retries/fallback/circuit/health logic may only remove or
reorder deployments that remain inside the PDP-authorized logical model group.
