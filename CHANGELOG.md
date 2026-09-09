# Changelog

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
