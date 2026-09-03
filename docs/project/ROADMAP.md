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
6. Add runtime health, bounded retry, safe fallback, and circuit breaker — COMPLETE
   (`governed-llm-gateway` PR #5).
7. Structured output and tool normalization — COMPLETE (`governed-llm-gateway` PR #6).
8. Streaming — COMPLETE (`governed-llm-gateway` PR #7).
9. OpenTelemetry via `a2a-otel-kit` — CURRENT, IMPLEMENTED / READY FOR INDEPENDENT REVIEW.
10. Evaluation framework — NEXT AFTER PHASE 9 REVIEW AND MERGE.
11. Evidence-driven ranking.
12. Thin client SDK transport.
13. Optional Verifiable AI Governance integration, including signed runtime authorization when used.
14. Incremental real-project integrations.

Phase 4 establishes the authorized candidate set. Phase 5 may only remove/rank candidates inside that
set. Phase 6 may retry the same deployment or move through the already-ranked authorized alternatives,
but may never widen the PDP authorization boundary.

Runtime health introduced in Phase 6 is mutable operational state and remains distinct from Phase 5
static/versioned ranking evidence. Benchmark-derived score provenance belongs to Phases 10–11.

Phase 6 establishes the replay-safety boundary that Phase 7 and Phase 8 preserve: automatic replay
stops after observed provider output, an external side effect, or opaque provider continuation state
unless a later explicit replay contract says otherwise.

Phase 7 adds native structured-output and business-tool normalization only after authorization and
selection. The gateway validates provider output/tool arguments but never executes the business tool.
`invalid_structured_output` and `invalid_tool_call` remain permanent execution failures rather than
availability signals.

Phase 7 deliberately does not fabricate provider-native continuation state after tool execution. A
future continuation contract must preserve exact provider correlation/reasoning state before the
gateway can safely round-trip `ToolResult` back into those provider APIs.

Phase 8 adds normalized SSE events, explicit streaming capability, cancellation-safe upstream closure,
final usage semantics, partial-output handling, and retry/fallback only before semantic output becomes
visible. It does not add a new authorization source.

Phase 9 adds metadata-only OpenTelemetry through the shared `a2a-otel-kit` foundation. It instruments
gateway, policy, provider, retry/fallback, and streaming execution evidence; propagates only W3C trace
context; preserves the deny-by-default payload/credential boundary; and keeps telemetry outside
provider-neutral contracts/domain logic. Telemetry remains evidence only and cannot become an
authorization, ranking, retry/fallback, or health authority.

Do not pull work forward when doing so weakens an authority boundary or requires an unstable contract.
Phase 10 must not start until Phase 9 completes independent architecture/security review and is merged.
