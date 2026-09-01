# Threat Model — Through Phase 6

## Method

Architecture-level abuse cases are mapped to controls already implemented or deliberately deferred to
the phase that owns them. Availability features never receive authorization authority.

| Threat | Current design response |
|---|---|
| API/provider/PDP-key leakage | secrets excluded from consumer contracts, registry/ranking evidence, normalized errors, retry evidence, and metadata-only telemetry |
| prompt/data leakage to PDP | `PolicyDecisionPort` accepts prompt-free metadata; `GatewayRequest.messages` is structurally absent from the PDP request |
| prompt leakage via explain | `POST /v1/route/explain` rejects `messages`/unknown fields and performs no provider inference |
| caller identity/classification downgrade | authenticated `EffectivePolicyContext` supplies authoritative identity/risk/classification/environment |
| PDP response substitution | accepted/rejected decisions require strict schema/provenance plus request/environment correlation |
| unauthorized model escalation | Phase 4 registry intersection, Phase 5 candidate validation, and Phase 6 fallback pre-validation enforce monotonic PDP→PEP authorization |
| registry TOCTOU/substitution | Phase 5 requires current registry digest to equal the digest bound to authorization |
| ambiguous PDP authorization | current PMR 1.0 binding requires exactly one authorized logical model group |
| candidate injection after authorization | out-of-group candidate is an invariant violation; Phase 6 validates bounded fallback candidates before any provider call |
| registry/ranking-policy tampering | strict safe parsing/schema validation plus deterministic digests/versioned score snapshot |
| ranking default bypass | unknown pricing and missing ranking score fail closed |
| high-scoring ineligible model wins | eligibility precedes scoring; runtime-health filtering can only remove candidates |
| nondeterministic model choice | exact `Decimal` scoring and ascending deployment tie-break |
| false benchmark provenance | static `score_snapshot_id` remains distinct from future `benchmark_snapshot_id` |
| provider substitution | selected provider/model/deployment plus PDP/registry/ranking provenance identify the routed deployment |
| malicious provider error body | adapters normalize typed errors; raw non-2xx body and arbitrary headers do not enter retry/evidence state |
| fallback authorization bypass | fallback sequence comes only from Phase 5 ranked candidates and is pre-validated against the original authorized model group |
| fallback to unregistered/misconfigured adapter | missing adapter is a terminal configuration failure; the gateway does not silently skip to another provider |
| retry on permanent failure | only retryable rate-limit/timeout/unavailable/transport failures are replayed; permanent failure stops retry/fallback |
| unbounded retry / denial of wallet | attempts/fallback count/backoff/Retry-After influence are explicitly bounded |
| synchronized retry storm | bounded exponential backoff uses deterministic per-request/deployment/attempt jitter |
| duplicate external side effects | `FallbackSafetyState` blocks replay after an external side effect |
| replay after partial/observed model output | replay safety blocks automatic retry/fallback after provider output is observed |
| cross-provider continuation of opaque reasoning state | replay safety blocks automatic continuation once opaque provider state is established |
| circuit-breaker bypass | open circuit blocks provider call and can remove deployment from ranking eligibility |
| missing runtime health treated optimistically | once runtime-health filtering is active, missing deployment snapshot fails closed |
| health feedback corrupts static ranking evidence | runtime health remains separate from Phase 5 static score/benchmark provenance |
| policy service unavailable | fail closed; provider is not called |
| malicious tool schema | tool normalization/execution semantics remain Phase 7; business runtime retains tool execution authority |
| streaming duplicate output/side effects | streaming and partial-output replay/cancellation are deferred to Phase 8 and must preserve ADR-0007 |
| log/trace data leakage | structured metadata-only evidence; prompt/completion/tool content/secrets prohibited by default |
| SSRF via custom endpoint | provider/PDP endpoints are trusted deployment configuration rather than caller request values; transport validation remains bounded |
| dependency compromise | bounded package dependencies plus lock/audit/secret/security/architecture/typing/test gates |
| information disclosure via explain | authenticated, prompt-free, decision-scoped response; no global model inventory |
| stale/unknown pricing under hard budget | unknown pricing is ineligible rather than treated as zero cost |

## Highest-priority security properties

1. No path can broaden PDP authorization.
2. No caller metadata can self-authorize a lower security classification or different identity.
3. No ranking, health, retry, circuit, or fallback mechanism can override policy/identity failure.
4. Registry/authorization snapshots cannot be substituted between Phase 4 and Phase 5.
5. Phase 6 cannot inject a fallback outside the original authorized logical model group.
6. Automatic replay stops at output/side-effect/opaque-state boundaries.
7. No provider payload/secret is required for routing, retry, health, or explainability evidence.
8. Consumer projects, FastAPI types, and provider SDK concerns cannot contaminate contracts/domain
   boundaries.
