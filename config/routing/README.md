# Complexity routing operational configuration

`complexity.json` is the versioned, secret-free operational artifact for task-complexity assessment and benchmark-quality narrowing.

It contains only:

- deterministic assessment thresholds for effective context and requested output;
- explicit capability floors for tool calling, structured output, and vision;
- optional exact workload-specific minimum complexity floors;
- explicit benchmark-derived minimum quality floors for `low`, `medium`, and `high` complexity.

It intentionally contains no provider, model, deployment, endpoint, credential, authorization, prompt/message, provider-native payload, ranking-weight, or benchmark-score data.

The loader uses a closed schema, rejects duplicate JSON keys, and materializes the existing immutable `ComplexityPolicy` and `ComplexityQualityPolicy` domain contracts. Its digest is SHA-256 over canonical validated content, so formatting, object-field order, and equivalent decimal scale do not change semantic provenance.

## Authority boundary

This configuration is not a Policy Decision Point and cannot authorize a model. The permanent order remains:

```text
authenticated workload
    -> PDP authorization
    -> authorized candidate set
    -> complexity assessment
    -> benchmark-grounded subset narrowing
    -> operational ranking
    -> provider execution
```

Therefore:

```text
complexity-eligible candidates <= PDP-authorized candidates
```

No complexity threshold or quality floor may widen the candidate set, restore a rejected deployment, override environment/data-classification restrictions, or bypass provider/runtime eligibility.

## Runtime status

The artifact is versioned before execution wiring on purpose. Loading `config/routing/complexity.json` does not activate complexity routing for `POST /v1/generate` by itself. A separate reviewed composition increment must inject the loaded policies into generation while preserving the authorization-first chain.
