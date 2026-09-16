# Current State

Last updated: 2026-09-16

This document states only what is true today. For the dated, PR-by-PR narrative of how each of these
facts was established — proof records, security reviews, real bugs found and fixed — see
`docs/project/CHECKPOINT_LOG.md`.

## Phase status

| Phase | Status |
|---|---|
| Phase 0 — Architecture Gate | COMPLETE BASELINE |
| Phase 1 — Policy Model Router generalization | COMPLETE (`policy-model-router` PR #20) |
| Phase 2 — Contracts and Model Registry | COMPLETE (`governed-llm-gateway` PR #1) |
| Phase 3 — Provider Execution Foundation | COMPLETE (`governed-llm-gateway` PR #2) |
| Phase 4 — Policy Router integration | COMPLETE (`governed-llm-gateway` PR #3) |
| Phase 5 — Deterministic Operational Ranking and Explainability | COMPLETE (`governed-llm-gateway` PR #4) |
| Phase 6 — Runtime Health, Retry and Safe Fallback | COMPLETE (`governed-llm-gateway` PR #5) |
| Phase 7 — Structured Output and Tool Normalization | COMPLETE (`governed-llm-gateway` PR #6) |
| Phase 8 — Streaming | COMPLETE (`governed-llm-gateway` PR #7) |
| Phase 9 — OpenTelemetry | COMPLETE (`governed-llm-gateway` PR #8) |
| Phase 10 — Evaluation Framework | COMPLETE (`governed-llm-gateway` PR #9) |
| Phase 11 — Evidence-Driven Ranking | COMPLETE (`governed-llm-gateway` PR #10) |
| Phase 12 — Thin Client SDK | COMPLETE (`governed-llm-gateway` PR #11) |
| Phase 13 — Governance Integration | COMPLETE (`governed-llm-gateway` PR #12) |
| Phase 14 — Real Project Integrations | IN PROGRESS — CASES 1/2 COMPLETE; CASE 3 DEFERRED |

## Durable architecture baseline

- uv workspace with explicit `gateway-contracts`, `gateway-core`, `gateway-client`, and `gateway-api` boundaries;
- Verifiable AI Governance is an optional upstream governance authority;
- Policy Model Router remains the deterministic PDP;
- the gateway remains the PEP plus operational selector/executor;
- permanent invariant: `Gateway allowed set ⊆ Policy Router authorized set`;
- governance authorization may narrow that set further but may never expand it;
- provider-specific SDKs/credentials remain behind gateway adapters;
- metadata-only evidence remains the default;
- immediate process-local runtime health and versioned recent operational evidence remain distinct from ranking policy and from each other;
- business-tool execution remains outside the gateway;
- benchmark, telemetry, SDK, client state and runtime evidence are never authorization sources.
- Anthropic Messages and OpenAI Responses are strict northbound translations into the same governed
  coordinator; their model strings are aliases, never deployment selectors.
- canonical messages represent text, image, audio, document, tool-use and tool-result blocks; every
  extension capability defaults to unavailable until explicitly declared.
- deterministic streaming preflight constructs and freezes provider requests for every bounded
  authorized candidate before HTTP 200 commitment; preflight performs no provider network I/O.
  Runtime retry/fallback still cannot widen the PDP-authorized group or replay tool-result requests
  ([PR #259](https://github.com/brunovicco/governed-llm-gateway/pull/259), [ADR-0017](../adr/ADR-0017-deterministic-streaming-preflight.md)).

## Operational readiness status

- **OR-8** (one-command local demo) — complete at the bounded operations-only local-demo scope.
- **OR-9** (broader operational-surface hardening) — minimum-appropriate hardening for the demonstrated
  surfaces is complete (bounded increments PC-34 through PC-51 plus a dedicated gap investigation found
  no further non-production gap). Production browser identity/session handling, OAuth/OIDC/workload
  identity, TLS termination, rate limiting, CSRF policy and any future mutation authority remain
  separate, explicit future work — see [Scope](../../README.md#scope).
- **OR-10** (product-readiness validation) — complete: reproducible end-to-end validation, two focused
  security reviews (this repository's own new code, and the existing HTTP/adapter surface — no findings
  in either pass), a consolidated Non-claims section, and real Console/Grafana screenshots.
- **PC-33 `live-development` profile** — every deployment (Gemini, OpenAI, Groq, NVIDIA, OpenRouter,
  Anthropic) is individually proven live.
- **`personal-default` profile** — six provider bindings, 14 deployments across five registry groups.
  The active pinned `approved_ranking.json` (`personal-default-v2`, artifact
  `sha256:4d58f86b791267b2d38c6a95edad576ab35a5b97a8ee43a78a9d527ac8ee56ad`) covers only `rag.answer`
  in `balanced`. The other eight configured workloads fail closed with HTTP 503
  `ranking_policy_unavailable` under the current launcher/Compose startup. Every deployment in every
  group was individually proven live in historical static-policy runs on 2026-09-09; those proofs
  do not make all workloads operational under today's artifact. Further coverage requires separately
  reviewed approved ranking evidence and explicit runtime artifact/pin selection.
- **Claude Code / PR #258** — real local CLI E2E through the external PDP, approved ranking path and
  Anthropic, with text, streaming, 31 tool definitions, actual `Read`/`Bash`, local tool execution and
  tool-result continuation. This proof used `agent.tool-use` ranking coverage, not the stock
  `rag.answer` artifact. Codex remains contract-tested only, without a live CLI claim. See
  [protocol scope](PROTOCOL_MULTIMODAL_GATEWAY.md#claude-code) and the dated [proof record](CHECKPOINT_LOG.md#claude-code-live-e2e--pr-258-executed-2026-09-15).
- **PC-52 Console per-request trace navigation** — implemented and proven live, twice (SDK-level and a
  full browser run through the Console UI itself), including a real infrastructure bug found and fixed
  along the way (`otel-collector`'s host port could never actually publish because its only Docker
  network was `internal: true`).

Credential-free CI proves repository/configuration/protocol behavior only. It does not by itself prove a
credential-backed provider/PDP request.

## Benchmark and evaluation status

All roadmap-listed benchmark classes have reviewed, versioned, deterministic contracts. The detailed
matrix — every workload, its current version, scorer semantics, and originating PR — is
`docs/evaluation/BENCHMARK_MATRIX.md`.

Recent operational evidence: the immutable snapshot contract, deterministic materialization from
provider-attempt samples, optional process-local best-effort recording, and content-addressed
source-instance batch handoff are all complete. Shared ingestion and fleet/source-membership
completeness remain pending — see `docs/evaluation/OPERATIONAL_EVIDENCE.md`.

## Phase 14 — Real Project Integrations

Normative order:

1. `controlled-autonomy-lab`
2. `getnet-multi-agent-support-v2`
3. `OpsLens`
4. `RAGForge`
5. `Verifiable AI Governance`

The roadmap says each migration is an integration case and consumers must not be migrated simultaneously.

### Case 1 — controlled-autonomy-lab — COMPLETE

Consumer squash merge:

`238e4b93284579b5c9ba0d650161febcdbf83a51`

The gateway path is opt-in and bounded to supported text generation. The consumer does not own provider credentials, provider/model/deployment selection or local retry/fallback. Unsupported provider-native continuation remains outside the gateway path and fails closed rather than faking tool results as user text.

Final consumer validation:

- 194 tests passed;
- coverage 86.19%;
- strict mypy and Ruff passed;
- Bandit 0 findings;
- architecture dependency check passed.

### Case 2 — getnet-multi-agent-support-v2 — COMPLETE

Consumer squash merge:

`6ee7f3db8f666e35f78f7df5524a1fc15e1ef0da`

The gateway owns generation provider/model selection and resilience. Gemini remains required only for the separate semantic-embedding path. Incomplete gateway configuration fails closed and never silently falls back to Gemini generation.

Final consumer validation:

- 259 tests passed, 14 skipped, 1 deselected;
- coverage 88.59%;
- strict mypy and Ruff passed;
- architecture/governance gates passed;
- Bandit 0 findings.

### Case 3 — OpsLens — VALIDATED CANDIDATE, DEFERRED

`brunovicco/opslens` PR #89 reached a green candidate integration for the bounded semantic-query planner.

Validated head:

`939c0e46110329c3bac046e05f5908ffb6c6e889`

Recorded validation:

- Python CI `33888638650` — PASS;
- 73 semantic-query tests passed;
- strict Pyright: 0 errors / 0 warnings;
- Ruff passed;
- Terraform CI `33888638704` — PASS;
- Checkov, Lambda package builds, Terraform validate and TFLint passed.

Authority boundary in that candidate remained correct: the model produces only a bounded structured proposal; deterministic OpsLens parser/domain validation remains mandatory; SQL compilation and Athena execution remain deterministic OpsLens responsibilities.

**Current decision:** do not change or merge OpsLens while that repository is under active independent development. Reconcile this integration only after the repository stabilizes.

### Case 4 — RAGForge — NOT STARTED

Not started because Case 3 is deliberately deferred. The sequencing guard is versioned directly in `SOURCE_ROADMAP.txt`, `ROADMAP.md` and this checkpoint: do not start RAGForge in parallel unless the normative order is explicitly revised.

### Case 5 — Verifiable AI Governance — NOT STARTED

Remains after the preceding integration cases.

## Current working boundary

Latest post-merge validated runtime baseline as of this update:
`main@7d7e2e3840719acd257b1c25c19f8ce4a84592d8`
([PR #259](https://github.com/brunovicco/governed-llm-gateway/pull/259)). Main's
[quality run `35037637219`](https://github.com/brunovicco/governed-llm-gateway/actions/runs/35037637219)
and [image run `35037637139`](https://github.com/brunovicco/governed-llm-gateway/actions/runs/35037637139)
both passed on that exact commit.

PR #259 records 1499 passed / 6 skipped, 84.36% coverage, a governed NVIDIA `rag.answer` smoke,
direct live adapter checks for the other five providers, and an authenticated pre-stream HTTP 422
JSON probe. These are bounded local proofs, not production certification; direct adapter checks must
not be presented as full governed E2E. See the
[dated proof record](CHECKPOINT_LOG.md#deterministic-streaming-preflight--pr-259-executed-2026-09-15).

1. Start new increments from the then-current `main`; retain the distinction between credential-free CI, direct adapter checks and governed live proofs.
2. OR-9's minimum-appropriate hardening for the demonstrated operational surfaces is complete (bounded increments PC-34..PC-51 plus a dedicated 2026-09-09 gap investigation found no further non-production gap). Production identity/TLS/rate-limit/CSRF concerns remain separate, explicit future work, not a silently missing minimum. Continue only with separately justified, consumer-independent security increments that preserve existing serving semantics.
3. Do not modify OpsLens until its independent development state is ready for reconciliation.
4. Do not begin RAGForge in parallel unless the normative roadmap order is explicitly revised.
5. Accept further upstream gateway changes only when they are consumer-agnostic, independently justified and preserve the permanent authorization invariant.
6. Do not create a model-forcing benchmark bypass: benchmark target identity must never become an authorization or routing override.
7. Treat `rag-ptbr-v2` `pt_br_quality` strictly as bounded reviewer-authored Brazilian Portuguese locale/terminology evidence; do not generalize it into arbitrary fluency, grammar, style or cultural-quality claims.
8. Keep benchmark quality components and recent operational evidence outside new ranking semantics until separate explicit versioned contracts review such use.
9. A future operational-evidence increment may add shared ingestion and an explicit fleet/source-membership completeness model over validated source-instance batches; it must not make remote evidence delivery part of inference availability or invent online score normalization/adaptive policy.
10. A future live gateway-backed benchmark executor must use an already-authorized gateway path, preserve target/effective-execution integrity checks, and remain outside credential-free default CI.
11. When OpsLens is resumed, reconcile against the then-current gateway commit and rerun the full OpsLens Python and Terraform gates before merge.

## Explicitly deferred

- OpsLens reconciliation/merge while its repository is actively evolving;
- RAGForge migration while Case 3 is deferred;
- client-side provider credentials or provider SDKs;
- client-side retry/fallback/circuit breaking/model selection;
- automatic/adaptive routing self-modification;
- arbitrary key discovery from governance token contents;
- using governance/runtime/benchmark evidence as a new authorization source;
- lossless continuation of opaque provider reasoning/signature state not represented canonically
  (ordinary canonical tool-use/text tool-result continuation is supported);
- benchmark-side provider/model forcing;
- credential-bearing live-provider benchmark execution in default CI;
- payload/prompt/completion capture as default telemetry/evidence;
- running the cross-repository composition proof *in CI*. Default CI has no second repository
  checked out and no Docker-in-Docker, so `compose.pdp-composition.yml` and
  `scripts/composition_proof.py` are run by hand against a real Policy Model Router with
  `RUNTIME_AUTHORIZATION_REQUIRED=true`. See `PDP_COMPOSITION_PROOF.md`.
