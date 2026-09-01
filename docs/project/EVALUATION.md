# Evaluation

Gateway routing is treated as empirical optimization. Runtime code must not encode personal model
preferences such as "model X is always best for agents".

## Phase 5 status

Phase 5 introduces a deterministic ranking mechanism before the benchmark framework exists. Its
`score_snapshot_id` identifies **static, versioned ranking input configuration** only.

It is not benchmark evidence and must not be represented as `benchmark_snapshot_id`.

Static Phase 5 inputs provide a reproducible bridge to later empirical routing while preserving:

- workload-specific versioned weights;
- deterministic score calculation;
- ranking-policy digest provenance;
- explicit rollback/replay of configuration;
- no hard-coded model preference in application logic.

## Planned benchmark evidence

The roadmap's initial benchmark classes include `structured_extraction`, `rag_ptbr`,
`code_generation`, `tool_use`, and `agent_orchestration`, later expanding to multimodal/long-context
and other classes.

Offline quality evidence is separated from online operational health:

- offline: task success, grounding, schema/tool accuracy, language quality, and other approved
  benchmark measurements;
- online: latency, errors, timeouts, rate limits, availability, and later circuit-breaker state.

Phase 10 establishes the evaluation framework. Phase 11 allows the ranking policy to consume approved
benchmark snapshots. Only then should `benchmark_snapshot_id` become routing provenance.

No private/confidential benchmark fixture may be sent to free/dev provider endpoints.
