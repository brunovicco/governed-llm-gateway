# Threat Model — Through Phase 5

## Method

Architecture-level abuse cases are mapped to explicit controls already implemented or deliberately
deferred to the phase that owns them. Availability features do not receive authorization authority.

| Threat | Current design response |
|---|---|
| API/provider/PDP-key leakage | secrets excluded from consumer contracts, registry/ranking evidence, normalized errors, and metadata-only evidence; consumers use gateway credential only |
| prompt/data leakage to PDP | `PolicyDecisionPort` accepts prompt-free metadata; `GatewayRequest.messages` is structurally absent from the PDP request |
| prompt leakage via explain | `POST /v1/route/explain` request schema rejects `messages`/unknown fields and performs no provider inference |
| caller identity/classification downgrade | caller fields remain claims; authenticated `EffectivePolicyContext` supplies authoritative identity/risk/classification/environment |
| PDP response substitution | accepted/rejected decisions require strict schema/provenance and request/environment correlation before use |
| unauthorized model escalation | Phase 4 registry intersection plus Phase 5 candidate-group validation enforce the monotonic PDP→PEP subset invariant |
| registry TOCTOU/substitution | Phase 5 requires the current registry digest to equal the digest bound into the authorized candidate set |
| ambiguous PDP authorization | current PMR 1.0 binding requires exactly one authorized logical model group before Phase 5 ranking |
| candidate injection after authorization | any candidate outside the PDP-authorized group is an invariant violation, not a rankable alternative |
| registry tampering | strict safe parsing/schema validation plus deterministic registry digest |
| ranking-policy tampering | strict safe YAML/duplicate-key/schema validation plus deterministic ranking-policy digest and versioned score snapshot |
| ranking default bypass | unknown pricing and missing ranking score fail closed rather than becoming free/neutral |
| high-scoring ineligible model wins | eligibility is evaluated before score; contract tests prove disabled/capability/context/environment/cost/latency rejection precedes selection |
| nondeterministic model choice | exact `Decimal` score calculation and ascending `deployment_id` tie-break; same inputs reproduce the same decision ID |
| false benchmark provenance | Phase 5 static `score_snapshot_id` is kept distinct from future `benchmark_snapshot_id` |
| provider substitution | concrete selected provider/model/deployment plus registry/ranking/PDP provenance are bound into routing evidence |
| malicious provider error body | provider adapters normalize/sanitize typed errors; raw non-2xx body and arbitrary headers do not escape by default |
| malicious PDP error body | non-authoritative error bodies are not propagated; 422 denial provenance is parsed only under strict schema/correlation checks |
| log/trace data leakage | structured metadata-only evidence; prompt/completion/tool content/secrets prohibited by default |
| SSRF via custom endpoint | provider/PDP endpoints are trusted deployment configuration rather than caller-controlled request values; transport validation remains bounded |
| fallback authorization bypass | Phase 6 must keep every fallback candidate inside the original authorization; no fallback exists yet in Phase 5 |
| duplicate side effects | Phase 6/7 must prohibit unsafe cross-provider continuation after external side effects; no such fallback exists yet |
| unbounded retry / denial of wallet | retry is not implemented in Phase 5; Phase 6 requires bounded retry while existing projected cost ceilings remain eligibility inputs |
| rate-limit exhaustion | Phase 6 owns retry/health/circuit behavior and may only narrow/reorder authorized candidates |
| malicious tool schema | gateway tool normalization is deferred; business runtime retains tool execution authority |
| dependency compromise | framework/provider dependencies stay in bounded packages; CI runs lock check, audit, secret/security, architecture, typing, and tests |
| information disclosure via explain | current explain endpoint is authenticated, prompt-free, decision-scoped, and does not expose a global model inventory |
| information disclosure via future `/models`/admin surfaces | future surfaces require explicit caller/role authorization and scoped responses |
| policy service unavailable | fail closed; provider is not called |
| stale/unknown pricing under hard budget | unknown pricing is ineligible; freshness-policy semantics may evolve explicitly rather than silently assuming zero cost |

## Highest-priority security properties

1. No path can broaden PDP authorization.
2. No request metadata can self-authorize a lower security classification or different identity.
3. No ranking/resilience mechanism can override policy/identity failure.
4. Authorization and registry snapshots cannot be substituted between Phase 4 and Phase 5.
5. No provider payload/secret is required for routing evidence or explainability.
6. Consumer projects, FastAPI types, and provider SDK concerns cannot contaminate contracts/domain
   boundaries.
