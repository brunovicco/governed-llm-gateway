# Threat Model — Through Phase 8

## Method

Architecture-level abuse cases are mapped to controls already implemented or deliberately deferred to
the owning phase. Availability and streaming features never receive authorization authority.

| Threat | Current design response |
|---|---|
| API/provider/PDP-key leakage | secrets excluded from consumer contracts, registry/ranking evidence, normalized errors, retry evidence, SSE metadata, and default telemetry |
| prompt/data leakage to PDP | `PolicyDecisionPort` accepts prompt-free metadata; messages/schema/tools are absent from the PDP request |
| prompt leakage via explain | `POST /v1/route/explain` rejects `messages`/unknown fields and performs no provider inference |
| caller identity/classification downgrade | authenticated `EffectivePolicyContext` supplies authoritative identity/risk/classification/environment |
| PDP response substitution | strict schema/provenance and request/environment correlation |
| unauthorized model escalation | Phase 4 registry intersection, Phase 5 validation, Phase 6 fallback pre-validation, and Phase 8 bounded-stream execution preserve monotonic authorization |
| registry TOCTOU/substitution | registry digest bound to authorization and revalidated before ranking |
| candidate injection after authorization | out-of-group candidate is an invariant violation before provider execution |
| high-scoring ineligible model wins | eligibility precedes scoring; health/streaming capability can only remove candidates |
| provider substitution | routing provenance identifies selected provider/model/deployment and fallback progression |
| malicious provider error body | adapters expose typed sanitized errors, not raw bodies/arbitrary headers |
| retry on permanent failure | only normalized transient availability errors replay |
| unbounded retry / denial of wallet | bounded attempts/fallback/backoff/Retry-After influence |
| duplicate external side effects | replay blocked after side effect/opaque state under ADR-0007 |
| hybrid cross-provider streamed response | retry/fallback stops permanently after first semantic stream output |
| partial-output replay | failure after visible content/tool output emits `response.failed(partial=true)` and does not replay |
| stream lifecycle confusion | duplicate usage, early completion, unknown events, or EOF without completion fail closed |
| missing final usage | provider/API family must support final streaming usage; successful normalized completion requires it exactly once |
| client disconnect leaks upstream connection | API/core use explicit async generator closure; provider SSE response/client are closed on cancellation |
| client cancellation poisons health | cancellation is propagated and is not recorded as provider failure |
| SSE memory exhaustion | one SSE event is bounded to 1 MiB |
| SSRF via streaming endpoint | provider endpoint comes from trusted deployment configuration; transport requires absolute HTTPS and rejects userinfo/fragments |
| provider-header/credential leakage through SSE | only `content-type` and `retry-after` retained by transport; secrets/raw bodies never normalized into public events |
| OpenAI-compatible feature overclaim | streaming and final-usage semantics remain disabled without explicit verified opt-in |
| malformed streaming tool call | complete JSON + declared-tool schema validation required before `tool_call.completed` |
| fabricated tool-call correlation | missing required provider correlation fails closed, including Gemini |
| gateway executes model-requested business action | gateway emits normalized ToolCall only; application/agent/MCP runtime owns authorization/execution |
| circuit-breaker bypass | open circuit blocks/filters concrete deployment without widening alternatives |
| stale/missing runtime health treated optimistically | active health filtering fails closed on missing snapshot |
| health feedback corrupts ranking evidence | runtime health remains separate from static score/benchmark provenance |
| policy service unavailable | fail closed before provider call |
| log/trace data leakage | metadata-only default; prompt/completion/tool content/secrets prohibited from routing/evidence by default |
| dependency compromise | locked dependencies plus audit/security/architecture/typing/test gates |
| false green coverage gate | pytest-cov threshold plus independent `coverage report --fail-under=80` enforcement |
| information disclosure via explain | authenticated, prompt-free, decision-scoped response; no global model inventory |
| information disclosure via streaming provenance | only decision-scoped routing metadata accompanies the authenticated request's stream |

## Highest-priority security properties

1. No path can broaden PDP authorization.
2. No caller metadata can self-authorize a lower security classification or different identity.
3. Ranking, health, retry, circuit, fallback, provider feature translation, and streaming cannot override policy failure.
4. Registry/authorization snapshots cannot be substituted between authorization and ranking.
5. Fallback cannot inject a deployment outside the original authorized logical model group.
6. Streaming retry/fallback stops after semantic output becomes visible.
7. Client disconnect/cancellation closes upstream resources without being misclassified as provider failure.
8. Structured-output/tool validation remains local and fail-closed during streaming.
9. The gateway never executes business tools or fabricates provider continuation/correlation state.
10. Provider credentials/raw error bodies/arbitrary headers never enter public streaming provenance.
11. Consumer projects, FastAPI types, provider wire types, and future telemetry concerns do not contaminate contracts/domain boundaries.
