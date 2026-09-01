# Roadmap

The normative detailed roadmap is preserved verbatim at `SOURCE_ROADMAP.txt`.

Current execution sequence:

0. Architecture Gate — COMPLETE BASELINE.
1. Generalize `policy-model-router` contract/vocabulary — COMPLETE (`policy-model-router` PR #20).
2. Finalize gateway contracts and implement validated, deterministic model registry/digest — COMPLETE
   (`governed-llm-gateway` PR #1).
3. Implement provider execution foundation and first adapters — COMPLETE
   (`governed-llm-gateway` PR #2).
4. Integrate deterministic Policy Model Router authorization — COMPLETE
   (`governed-llm-gateway` PR #3).
5. Implement deterministic operational ranking and explainability — CURRENT, IMPLEMENTED / IN REVIEW.
6. Add resilience (timeouts/retry/fallback/circuit breaker) — NEXT AFTER PHASE 5 MERGE.
7. Structured output and tool normalization.
8. Streaming.
9. OpenTelemetry via `a2a-otel-kit`.
10. Evaluation framework.
11. Evidence-driven ranking.
12. Thin client SDK transport.
13. Optional Verifiable AI Governance integration, including signed runtime authorization when used.
14. Incremental real-project integrations.

Phase 4 establishes the authorized candidate set and PEP enforcement. Phase 5 may only remove/rank
candidates inside that set and must never broaden PDP authorization.

Phase 5 ranking inputs are intentionally static/versioned. Live health, circuit-breaker state, retry,
and fallback belong to Phase 6. Benchmark-derived score provenance belongs to Phases 10–11.

Do not pull work forward when doing so weakens an authority boundary or requires an unstable contract.
