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
5. Implement deterministic operational ranking and explainability — COMPLETE
   (`governed-llm-gateway` PR #4).
6. Add runtime health, bounded retry, safe fallback, and circuit breaker — CURRENT, IMPLEMENTED / IN
   REVIEW.
7. Structured output and tool normalization — NEXT AFTER PHASE 6 MERGE.
8. Streaming.
9. OpenTelemetry via `a2a-otel-kit`.
10. Evaluation framework.
11. Evidence-driven ranking.
12. Thin client SDK transport.
13. Optional Verifiable AI Governance integration, including signed runtime authorization when used.
14. Incremental real-project integrations.

Phase 4 establishes the authorized candidate set. Phase 5 may only remove/rank candidates inside that
set. Phase 6 may retry the same deployment or move through the already-ranked authorized alternatives,
but may never widen the PDP authorization boundary.

Runtime health introduced in Phase 6 is mutable operational state and remains distinct from Phase 5
static/versioned ranking evidence. Benchmark-derived score provenance belongs to Phases 10–11.

Phase 6 also establishes the replay-safety boundary that later tool/structured-output and streaming
phases must preserve: automatic replay stops after observed provider output, an external side effect,
or opaque provider continuation state unless a later explicit replay contract says otherwise.

Do not pull work forward when doing so weakens an authority boundary or requires an unstable contract.
