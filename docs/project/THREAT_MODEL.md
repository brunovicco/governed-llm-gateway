# Threat Model — Phase 0 Draft

## Method

Architecture-level abuse cases are mapped to explicit design controls. Detailed provider-specific
threats are refined when adapters exist.

| Threat | Phase 0 design response |
|---|---|
| API/provider-key leakage | provider secrets excluded from contracts/config evidence; consumers use gateway credential only |
| prompt/data leakage | PDP metadata projection excludes messages; metadata-only telemetry by default |
| provider substitution | concrete deployment is selected from validated registry and bound into provenance |
| registry tampering | deterministic registry digest required before execution phases |
| ranking-policy tampering | version/digest provenance and controlled configuration required |
| unauthorized model escalation | monotonic PDP→PEP subset invariant enforced/tested |
| caller classification downgrade | caller fields treated as claims; authoritative identity/policy establish effective context |
| fallback authorization bypass | every fallback candidate remains inside original authorization |
| duplicate side effects | no automatic cross-provider fallback after external side effect; explicit replay/idempotency semantics required |
| malicious provider error body | future adapters normalize/sanitize typed errors; raw body not telemetry/evidence by default |
| log injection | structured/sanitized metadata-only logging requirement |
| trace data leakage | prompts/completions/tool content/secrets prohibited by default |
| SSRF via custom endpoint | custom provider endpoints are trusted deployment config, not caller-controlled request values; later validation/allowlist required |
| unbounded retry / denial of wallet | retries bounded; cost ceilings and execution budget are explicit routing inputs |
| rate-limit exhaustion | per-deployment health/retry/circuit design; no policy widening |
| malicious tool schema | gateway normalizes only; business runtime retains authorization/execution authority; schema validation required later |
| dependency compromise | provider SDKs isolated to adapters; CI includes audit/secret/security checks |
| information disclosure via /models or /route/explain | future surfaces require caller/role authorization and scoped responses |
| policy service unavailable | fail closed; provider is not called |
| stale pricing under hard budget | unknown/stale pricing cannot silently satisfy hard cost ceiling |

## Highest-priority security properties

1. No path can broaden PDP authorization.
2. No request metadata can self-authorize a lower security classification.
3. No availability mechanism can override policy/identity failure.
4. No provider payload/secret is required for routing evidence.
5. Consumer projects and provider SDKs cannot contaminate contracts/domain boundaries.
