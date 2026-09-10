# Changelog

## Unreleased

Changes on `main` since `v1.0.0`. No version has been cut for these yet; no `v1.1.0` decision has been
made.

- **Quality gate runs each step once**: `scripts/quality_gate.py` invoked `architecture_check.py`
  and `secret_scan.py` directly and then ran `phase0_gate.py`, which runs both again. Steps are now
  named, timed, reported as a summary, and deduplicated; `phase0_gate.py` stays independently
  runnable and keeps owning those two checks.
- **Secret scan enumerates through Git, and is now itself under test**: `scripts/secret_scan.py`
  walked the filesystem and excluded only `.git`, `.venv` and `uv.lock`, so it read paths that can
  never reach a commit. A local `.env` holding a real provider key therefore failed
  `scripts/quality_gate.py` on a developer machine while CI stayed green only because no `.env`
  exists there, and every scan also read `node_modules/`, `dist/` and the tool caches. Candidates now
  come from `git ls-files --cached --others --exclude-standard` — tracked files plus untracked files
  that are not ignored, which is exactly the set a commit could carry. Enumeration fails closed
  outside a Git working tree rather than silently narrowing, findings report a line number and never
  print the matched value, and symlinks, deleted index entries, binary and oversized files are
  skipped. Adds `tests/contract/test_secret_scan.py` (10 cases), the first coverage this security
  control has had.
- **README leads with a real governed request**: both READMEs opened on the operations-only demo
  screenshots, whose connected view is honestly empty (`phase2-empty` registry, `0 deployments`,
  `0 healthy`) — a first impression of a console with nothing in it. A new section above
  "What this project demonstrates" leads with `console-trace-evidence.png`, which existed only in
  `docs/project/GATEWAY_CONSOLE.md`: a real `personal-default` run showing the selected provider,
  attempt/fallback counts, routing and policy decision IDs, registry and ranking digests, and the
  emitted trace ID. The operations-only screenshots stay where they are; their column header now
  says `operations-only baseline (no inference route)` so the empty registry reads as intentional
  at a glance rather than three paragraphs later.
- **Documentation restructure** (#240): consolidates 27 narrow per-workload/per-benchmark docs under
  `docs/evaluation/` into the already-comprehensive `BENCHMARK_MATRIX.md`, removes 3 completed phase
  reports and a duplicate `MODEL_REGISTRY.md`, and splits `docs/project/CURRENT_STATE.md` into a short
  evergreen status document plus a new dated, append-only `docs/project/CHECKPOINT_LOG.md`.
- **Personal-default profile — full Anthropic and reasoning-strong proof coverage** (#239): every
  deployment in every model group `personal-default` wires is now individually proven live in that
  profile specifically (previously some were proven only in `live-development`), including
  `security.analysis`, `code.generate` and `code.review`.
- **PC-52 — Gateway Console per-request trace navigation** (#237): closes README item 2 and the OR-6
  per-trace-correlation gap. `ProviderExecution` gains an optional, strictly-validated `trace_id`; the
  Gateway threads its own real OTel span's trace ID through the terminal SSE event when tracing is
  enabled; the Console renders a "View this request's trace in Grafana" link to the exact trace via a
  second panel on the existing provisioned dashboard. Proven live twice (SDK and full browser run)
  against a real captured trace. Also fixes a real bug found while proving this: `otel-collector` in
  `compose.observability.yml` could never actually publish its host port because its only network was
  `internal: true`.
- **OR-9 minimum-hardening investigation** (#236): closes README item 3. A dedicated investigation found
  no further non-production security gap beyond the existing PC-34..PC-51 increments on the demonstrated
  operational surfaces; documents one previously-implicit-but-correct property (no CORS middleware on the
  Gateway API) explicitly.
- **PC-33 profile completeness** (#235): closes README item 1 for real. Fixes a stale README claim
  (OpenAI was already proven, the claim said otherwise) and proves the profile's actual remaining gap,
  OpenRouter, live. Every deployment in the `live-development` profile is now individually proven.

The PC-33/OR-9/PC-52 group above closes every item in the README's post-v1.0.0 punch list. The
personal-default proof coverage and documentation restructure are further hardening/cleanup on top of
that closed list, not new punch-list items.

## v1.0.0 — 2026-09-09

First versioned release. `1.0.0` marks a stable public contract for the workspace packages and a
reusable open-source package, not a production-infrastructure claim — see [Non-claims](README.md#non-claims)
in the README for exactly what is and is not covered.

All workspace packages move to `1.0.0` in lockstep: `governed-llm-gateway-contracts`,
`governed-llm-gateway-core`, `governed-llm-gateway-api`, `governed-llm-gateway-client`, and the
`governed-llm-gateway-console` frontend.

### Included

- **Core platform (Phases 0–13, complete):** PDP/PEP separation with the permanent invariant
  `Gateway allowed set ⊆ Policy Router authorized set`; provider-neutral contracts and model registry;
  deterministic operational ranking and explainability; runtime health, bounded retry and safe
  fallback; structured-output/tool-call normalization; streaming; metadata-only OpenTelemetry;
  a deterministic evaluation/benchmark framework; a thin typed client SDK; optional governance
  integration that can only narrow authorization, never widen it.
- **Real-project integrations (Phase 14, in progress):** two consumer integrations complete; a third
  (OpsLens) intentionally deferred pending its own repository stabilizing; two more not started, by
  explicit sequencing decision.
- **Local operational demo (OR-8, complete):** one-command, credential-free, operations-only local
  demo (Gateway Operations API, Console, OTel Collector, Tempo, Grafana).
- **Live-inference profiles:** `config/profiles/live-development/` (reviewed demo/development profile,
  two native providers) and `config/profiles/personal-default/` (the profile for calling the Gateway
  from your own projects, six providers, NVIDIA cost-preferred ranking).
- **Bounded operational-surface hardening (OR-9, in progress):** PC-34 through PC-51 close specific
  gaps on the surfaces this repository actually exposes (non-storable responses, header sanitization,
  bounded request bodies); production IAM/TLS/SSO, session handling, rate limiting and CSRF remain
  explicit future work, not silently assumed.
- **Product-readiness validation (OR-10, complete):** reproducible end-to-end validation against the
  repository's own documented quick starts; two focused security reviews (this session's new code, and
  the existing HTTP/adapter surface) with no findings in either pass; a consolidated Non-claims section;
  real Console/Grafana screenshots of the operations-only demo.

### Not included (see [Non-claims](README.md#non-claims) for the full list)

Production infrastructure (TLS termination, production IAM/OAuth/OIDC, browser session management,
rate limiting, CSRF policy), a third-party provider SLA, a benchmark of real production traffic, a
multi-tenant or remote deployment, and the remaining Phase 14 integrations.

See [`docs/project/CURRENT_STATE.md`](docs/project/CURRENT_STATE.md) for the full, continuously updated
project checkpoint this release is cut from.
