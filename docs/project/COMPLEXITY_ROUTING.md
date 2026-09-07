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
capability / registry eligibility
        ↓
task-complexity assessment
        ↓
complexity-aware narrowing / ranking
        ↓
deterministic operational ranking
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

CR-1 adds a pure, versioned metadata evaluator. `ComplexityPolicy` makes every rule explicit rather than embedding hidden routing heuristics:

- medium/high effective-context token thresholds;
- medium/high output-token thresholds;
- configured floors for tool calling, structured output, and vision;
- optional exact workload-specific floors.

For one request, the evaluator starts at `low` and monotonically takes the maximum complexity produced by every applicable configured rule. The effective context signal is the maximum of the caller's context estimate and the request's explicit `min_context_tokens` requirement, so a declared minimum context requirement cannot be underclassified by a smaller estimate.

The evaluator generates `assessment_id` as a SHA-256 digest over canonical metadata containing the versioned policy, workload identifier, capability flags, and token estimates. Request message content is deliberately excluded. Identical metadata under an identical policy therefore produces identical complexity evidence.

CR-1 still does not change model selection. It produces evidence only.

## Current limitation and future semantic assessment

The CR-1 evaluator does not claim to infer semantic reasoning difficulty from prompt text. Token volume and capability requirements are operational signals, while workload-specific floors allow explicit policy-defined knowledge about known task classes.

A future semantic evaluator may be added behind a provider-neutral contract when there is benchmark evidence to justify it. If such an evaluator uses an LLM, its output remains advisory evidence and must not gain authorization authority, self-modify policy, or bypass deterministic validation.

A later increment can map assessed complexity to model capability/quality tiers and intersect those requirements with the already-authorized, registry-eligible candidate set. That mapping must be explicit, versioned, auditable, reversible, and benchmark/evidence driven.

## Centralized provider boundary

Provider credentials remain an operational gateway concern. Consuming applications should authenticate to the gateway rather than receive direct OpenAI, Anthropic, Google/Gemini, NVIDIA, or other provider credentials.
