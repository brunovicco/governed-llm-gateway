# Complexity-Aware Generation

## Scope

CR-4 extends the validated complexity-routing chain into streaming provider execution through an explicit opt-in mode on `POST /v1/generate`.

The existing generation contract remains the default:

```text
POST /v1/generate
    -> operational routing (default)

POST /v1/generate?mode=complexity
    -> trusted client context
    -> PDP authorization
    -> deterministic metadata-only complexity assessment
    -> benchmark-grounded quality narrowing
    -> operational ranking of the narrowed subset
    -> streaming provider execution
```

The request-body schema remains `1.0`. Complexity selection is an HTTP query mode so existing consumers do not opt in accidentally.

## Authority boundary

Complexity-aware generation preserves the permanent subset relation:

```text
executed deployment
    ⊆ complexity-eligible candidates
    ⊆ PDP-authorized candidates
```

`ComplexityGenerateCoordinator` resolves trusted client context first and delegates routing to the existing `ComplexityRouteExplainService`. The PDP therefore completes before the complexity evaluator runs. The resulting `RankingDecision` contains only candidates retained by complexity narrowing and is passed unchanged to the existing `StreamingExecutionService`.

Provider execution, retry, and fallback never receive the broader authorized candidate set. A deployment excluded by the configured complexity quality floor cannot be restored because another retained deployment is unhealthy or fails during preflight/execution.

## Evidence requirements

Complexity mode requires the existing evidence-driven ranking boundary. Quality narrowing accepts only `benchmark_hybrid` provenance and uses the versioned `ComplexityQualityPolicy`. Missing benchmark quality, evidence drift, an empty complexity subset, or a subset invariant violation fails closed.

The versioned operational values live in `config/routing/complexity.json`. Loading that artifact alone does not activate complexity-aware generation; the composition root must explicitly inject a `ComplexityGenerateCoordinator`.

## Failure behavior

Complexity-aware generation completes authentication, PDP authorization, complexity narrowing, and ranking before an SSE response starts. Configuration/evidence failures are therefore returned as bounded HTTP errors instead of beginning provider execution.

If complexity mode is requested without a configured complexity coordinator, the API returns `503` with `complexity_routing_unavailable`. The default operational mode remains independent of complexity configuration.

## Non-goals

CR-4 does not add a semantic or LLM-based complexity classifier, adaptive routing, a new authorization source, provider credentials, provider-specific request contracts, business-tool execution, or Phase 14 integrations.
