# Roadmap

The normative detailed roadmap is preserved verbatim at `SOURCE_ROADMAP.txt`.

Current execution sequence:

0. Architecture Gate — COMPLETE BASELINE.
1. Generalize `policy-model-router` contract/vocabulary — COMPLETE (`policy-model-router` PR #20).
2. Finalize gateway contracts and implement validated, deterministic model registry/digest — COMPLETE
   (`governed-llm-gateway` PR #1).
3. Implement provider execution foundation and first adapters — CURRENT, IMPLEMENTED / IN REVIEW.
4. Integrate deterministic PDP authorization.
5. Implement deterministic operational ranking and explainability.
6. Add resilience (timeouts/retry/fallback/circuit breaker).
7. Structured output and tool normalization.
8. Streaming.
9. OpenTelemetry via `a2a-otel-kit`.
10. Evaluation framework.
11. Evidence-driven ranking.
12. Thin client SDK transport.
13. Optional Verifiable AI Governance integration.
14. Incremental real-project integrations.

Do not pull work forward when doing so weakens an authority boundary or requires an unstable contract.
