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

Future implementations may move complexity assessment earlier for efficiency, but its output remains non-authoritative and can only be applied as an intersection with the already authorized set.

## CR-0 contract

CR-0 introduces only stable provider-neutral metadata:

- `TaskComplexity.LOW` → `low`;
- `TaskComplexity.MEDIUM` → `medium`;
- `TaskComplexity.HIGH` → `high`;
- `ComplexityAssessment` with `assessment_id`, `evaluator_id`, and `evaluator_version` provenance.

The assessment contract is metadata-only. It contains no prompt, completion, tool arguments, tool results, document contents, credentials, or provider-native payloads.

CR-0 does not change model selection.

## Planned evolution

Later increments can add a deterministic/versioned complexity evaluator, define how complexity maps to minimum capability or quality requirements, and integrate that result into routing provenance. Those increments must preserve the authorization boundary above and remain benchmark/evidence driven rather than adaptive or self-modifying.

Provider credentials remain an operational gateway concern. Consuming applications should authenticate to the gateway rather than receive direct OpenAI, Anthropic, Google/Gemini, NVIDIA, or other provider credentials.
