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
9. OpenTelemetry via `a2a-otel-kit` — COMPLETE (`governed-llm-gateway` PR #8, merge commit
   `be15c21ecfc76ef9bb727e5c4144c4929f028489`).
10. Evaluation framework — COMPLETE (`governed-llm-gateway` PR #9, squash merge
    `db30ffc481d1a3c02fb01f46524b5190290fb7ac`).
11. Evidence-driven ranking — CURRENT; implementation validated, documentation/review preparation in
    progress. ADR-0009 accepted.
12. Thin client SDK transport — NOT STARTED; blocked on Phase 11 review and merge.
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

Phase 10 added an offline-first evaluation source root under `benchmarks/`: strict public/synthetic
versioned datasets, deterministic local scorers, a provider-neutral benchmark executor/runner,
fully identified provider/model/API/configuration targets, explicit quality-vs-availability evidence,
scorecards, canonical dataset digests, and immutable content-derived result snapshots. Benchmark code
is included in repository lint, typing, security, architecture, and coverage gates.

Phase 10 remained evidence-only through merge. Runtime ranking did not consume benchmark results until
Phase 11 was explicitly authorized by ADR-0009.

Phase 11 uses an explicit promotion boundary:

`immutable benchmark snapshot -> explicit approval/promotion -> versioned ranking evidence -> runtime ranking`

Implemented Phase 11 behavior:

- benchmark promotion maps exact benchmark target/workload evidence to exact runtime
  deployment/workload identities;
- runtime validates promoted evidence without importing the offline `benchmarks/` source root;
- the first evidence-driven compiler replaces only bounded empirical `quality` and `availability`;
  reliability, normalized latency/cost, weights, and hard expected-latency inputs remain static until
  separately reviewed normalization semantics exist;
- benchmark snapshot and promotion identities participate in the ranking-policy digest;
- routing provenance exposes exact benchmark snapshot identity and explicit score-provenance mode;
- manual override is a content-addressed, versioned, attributable operator action and may replace only
  the benchmark-promoted quality/availability dimensions;
- an active override carries exact `manual_override_id` provenance into the ranking policy and routing
  decision identity;
- override cannot add candidates, stack implicitly, bypass PDP authorization, or bypass gateway
  eligibility;
- rollback selects exactly one previously approved immutable ranking artifact by content-derived
  artifact identity;
- unknown/missing evidence, unknown override targets, and ambiguous rollback targets fail closed.

Runtime must not discover or auto-promote the newest benchmark snapshot. Benchmark-derived evidence may
only change ordering inside the already-authorized and otherwise-eligible candidate set. No benchmark
run, telemetry signal, provider outcome, or runtime observation may automatically rewrite active
ranking policy.

Final implementation baseline before documentation synchronization:

- head `d076ced8a99fcf89afa7f0d62234913501413a4d`;
- GitHub Actions run `33814109995` — PASS;
- pytest — 251 passed;
- aggregate branch coverage — 81.27%;
- mypy — PASS across 97 source files;
- Ruff lint/format, Bandit, pip-audit, architecture check, secret scan, and Phase 0 gate — PASS.

Phase 12 must not begin until Phase 11 documentation is synchronized, PR-head CI is green, independent
architecture/security review returns APPROVE with no justified BLOCKER/HIGH/MEDIUM findings, and the
Phase 11 PR is merged.

Do not pull work forward when doing so weakens an authority boundary or requires an unstable contract.
