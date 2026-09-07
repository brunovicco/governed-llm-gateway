# Task Complexity Routing

## Product intent

The gateway is intended to centralize provider-neutral LLM access and route each task to an appropriate authorized model instead of requiring every consuming project to choose a provider/model directly.

Task complexity is one input to that operational selection. It is not an authorization source.

## Permanent authority boundary

The governing invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

A complexity assessment may only narrow or rank candidates that have already crossed the authoritative policy boundary. It must never:

- authorize a provider, model group, model, or deployment;
- widen the candidate set returned by policy enforcement;
- resurrect a candidate rejected by policy, registry eligibility, data-classification rules, capability requirements, or other fail-closed controls;
- override provider or environment restrictions;
- self-modify policy or routing rules.

The safe ordering is:

```text
authenticated workload context
        ↓
Policy Router authorization
        ↓
authorized candidate set
        ↓
task-complexity assessment
        ↓
benchmark-grounded complexity narrowing
        ↓
deterministic operational ranking of the narrowed subset
        ↓
provider execution / bounded resilience
```

Complexity may be computed earlier for efficiency, but its output remains non-authoritative and can only be applied as an intersection with the already authorized set.

## CR-0 contract

CR-0 introduced stable provider-neutral metadata:

- `TaskComplexity.LOW` → `low`;
- `TaskComplexity.MEDIUM` → `medium`;
- `TaskComplexity.HIGH` → `high`;
- `ComplexityAssessment` with `assessment_id`, `evaluator_id`, and `evaluator_version` provenance.

The assessment contract is metadata-only. It contains no prompt, completion, tool arguments, tool results, document contents, credentials, or provider-native payloads.

## CR-1 deterministic evaluator

CR-1 added a pure, versioned metadata evaluator. `ComplexityPolicy` makes every rule explicit rather than embedding hidden routing heuristics:

- medium/high effective-context token thresholds;
- medium/high output-token thresholds;
- configured floors for tool calling, structured output, and vision;
- optional exact workload-specific floors.

For one request, the evaluator starts at `low` and monotonically takes the maximum complexity produced by every applicable configured rule. The effective context signal is the maximum of the caller's context estimate and the request's explicit `min_context_tokens` requirement, so a declared minimum context requirement cannot be underclassified by a smaller estimate.

The evaluator generates `assessment_id` as a SHA-256 digest over canonical metadata containing the versioned policy, workload identifier, capability flags, and token estimates. Request message content is deliberately excluded. Identical metadata under an identical policy therefore produces identical complexity evidence.

CR-1 does not change model selection. It produces evidence only.

## CR-2a benchmark-grounded quality narrowing

CR-2a connects complexity evidence to the existing Phase 11 benchmark evidence plane without adding a second subjective model tier to the registry.

`ComplexityQualityPolicy` declares explicit, versioned minimum quality floors for `low`, `medium`, and `high` complexity. The floors must be finite values in `[0, 1]` and monotonic:

```text
low_min_quality <= medium_min_quality <= high_min_quality
```

The narrowing boundary accepts only an already-created `AuthorizedCandidateSet`. It then reads per-deployment quality from an `EvidenceDrivenRankingPolicy` whose score provenance is explicitly `benchmark_hybrid`. Static Phase 5 ranking policies and manual-override ranking policies fail closed at this boundary because they do not prove that the quality value used for complexity narrowing came from promoted benchmark evidence.

For every authorized candidate, benchmark-derived quality must be present for the workload. Missing quality evidence fails closed rather than silently falling back. Candidates below the assessed complexity floor are excluded; candidates meeting the floor remain eligible for later operational ranking.

The permanent subset relation is therefore explicit:

```text
complexity-eligible candidates
    ⊆ authorized candidates
    ⊆ Policy Router authorized set
```

A high-quality deployment that is present in benchmark evidence but absent from the authorized candidate set can never appear in the complexity-eligible result.

CR-2a emits metadata-only narrowing provenance containing the complexity assessment identity, complexity level, effective minimum quality, quality-policy digest, ranking-policy digest, benchmark snapshot identity, promotion evidence identity, and excluded deployment identifiers. It does not capture prompt or completion content.

## CR-2b operational ranking composition

CR-2b composes the CR-2a subset with the existing `OperationalRankingService` without changing the Phase 5 scoring formula or its authority boundary.

`ComplexityAwareRankingService` accepts a previously validated `ComplexityEligibleCandidateSet`. It reconstructs an `AuthorizedCandidateSet` containing only those complexity-eligible deployments while preserving the original PDP decision and model-registry digest, then delegates to the existing Phase 5 ranking implementation.

The service fails closed before ranking when the complexity-eligible subset is empty. It does not relax the quality floor, reuse the broader authorized set, or search benchmark/ranking evidence for a replacement deployment.

The ranking policy digest must also match the digest recorded by CR-2a narrowing provenance. This prevents one ranking/evidence policy from determining complexity eligibility and a different policy from scoring the retained deployments.

After delegation, the composition boundary defensively verifies that every selected deployment, alternative, and Phase 5 rejection belongs to the complexity-eligible subset. The resulting invariant is:

```text
selected model / alternatives / ranking rejections
    ⊆ complexity-eligible candidates
    ⊆ authorized candidates
    ⊆ Policy Router authorized set
```

Phase 5 continues to own deterministic operational checks such as capabilities, context size, pricing/cost, expected latency, runtime health, environment, data classification, and score availability. Those checks may only remove candidates from the complexity subset; they cannot restore a deployment that CR-2a excluded.

`ComplexityAwareRankingDecision` preserves both evidence planes: the existing `RankingDecision` and the immutable CR-2a `ComplexityNarrowingProvenance`.

## CR-2c end-to-end no-inference composition

CR-2c introduces `ComplexityRouteExplainService`, an application-level composition boundary for the complete validated chain without changing the public API yet.

The service performs these steps in fixed order:

```text
project trusted policy metadata
        ↓
PDP authorization
        ↓
deterministic complexity assessment
        ↓
benchmark-grounded complexity narrowing
        ↓
complexity-aware operational ranking
```

The PDP call completes before the complexity evaluator is invoked. A PDP rejection therefore terminates the request before any complexity assessment can influence later routing work.

The same explicit context/output token estimates are used for policy projection and CR-1 assessment. CR-2a and CR-2b receive the same `EvidenceDrivenRankingPolicy`, and CR-2b still verifies its digest against the narrowing provenance before scoring.

`ComplexityRouteExplainDecision` returns only metadata/provenance: the CR-1 assessment, CR-2a narrowing provenance, the retained deployment identifiers, and the existing Phase 5 `RankingDecision`. No provider call is part of this service.

Missing benchmark quality, an empty complexity-eligible subset, PDP rejection, policy/evidence drift, or any downstream subset violation fails closed. There is no automatic fallback to the broader authorized set and no quality-floor relaxation.

CR-2c deliberately stops at the application boundary. Public `/v1/route/explain` response/schema wiring and generation/provider-execution wiring remain separate increments so compatibility and execution behavior can be reviewed independently.

## Current limitation and future semantic assessment

The CR-1 evaluator does not claim to infer semantic reasoning difficulty from prompt text. Token volume and capability requirements are operational signals, while workload-specific floors allow explicit policy-defined knowledge about known task classes.

A future semantic evaluator may be added behind a provider-neutral contract when there is benchmark evidence to justify it. If such an evaluator uses an LLM, its output remains advisory evidence and must not gain authorization authority, self-modify policy, or bypass deterministic validation.

Future increments can expose the validated CR-0 → CR-1 → CR-2a → CR-2b → CR-2c evidence chain through route explanation and later provider execution. Any additional capability/quality mapping must remain explicit, versioned, auditable, reversible, and benchmark/evidence driven.

## Centralized provider boundary

Provider credentials remain an operational gateway concern. Consuming applications should authenticate to the gateway rather than receive direct OpenAI, Anthropic, Google/Gemini, NVIDIA, or other provider credentials.
