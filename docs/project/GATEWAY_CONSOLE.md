# Gateway Console Foundation

## Purpose

PC-25 / OR-5A introduces the first browser-based operator surface for the Governed LLM Gateway. It is a
read-only consumer of the already-reviewed Operations API; it is not a control plane and it does not
create a new source of truth.

The first console consumes only:

```text
GET /v1/ops/overview
GET /v1/ops/deployments
```

The console does not call providers, the Policy Router, Tempo, Grafana, Langfuse, secret stores or
configuration files directly.

## Technology boundary

The application lives at `apps/gateway-console` and uses pinned React, TypeScript and Vite dependencies.
Frontend CI uses Node.js 24 LTS and a committed npm lockfile.

Development traffic remains same-origin from the browser perspective. Vite proxies `/v1` to the local
Gateway process at `http://127.0.0.1:8000`. Production hosting/BFF/session architecture is deferred.

## Credential handling

The existing Operations transport still requires:

```text
X-Gateway-API-Key
```

PC-25 deliberately does not invent OAuth, JWTs, cookies or a browser session service. The operator enters
the credential manually and the console keeps it only in React component state for the active page
lifetime. Disconnect clears that state.

The console itself does not write the credential to:

- `localStorage`;
- `sessionStorage`;
- cookies;
- URLs or query strings;
- generated configuration;
- repository files.

This is a local-demo boundary, not the final production identity architecture. External IAM/BFF/session
hardening remains OR-9 work.

## Trusted data boundary

Browser TypeScript types are not treated as runtime validation. PC-25 decodes both Operations responses
with closed-shape runtime validators before rendering them. Unexpected fields, unsupported enum values,
invalid counts, invalid dates, non-positive context windows or disagreement between overview and catalog
sizes fail closed into a bounded console error.

No stale cache or placeholder operational values are rendered while disconnected, loading or failed.
The UI therefore does not fabricate:

- fleet health;
- provider availability;
- latency;
- cost;
- evidence freshness/completeness;
- routing decisions;
- authorization reasons;
- traces.

`process_local` is rendered explicitly for health and must not be relabeled as global/fleet state.

## Read-only authority boundary

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Console visibility is independently granted by `OperationsReadAccessService`. The browser cannot authorize
models, widen or restore PDP output, alter eligibility/complexity/ranking, mutate health/circuit state,
change retry/fallback, execute a provider or edit runtime configuration.

PC-25 contains no mutation control and the frontend boundary check rejects newly introduced POST/PUT/PATCH/
DELETE request literals and unreviewed `/v1/ops/*` paths in source.

## CI

`.github/workflows/console-quality.yml` is credential-free and path-scoped. It requires:

```text
npm ci --ignore-scripts
npm run typecheck
npm test
npm run security:surface
npm run build
```

The workflow is separate from the Python quality gate so frontend toolchain concerns do not weaken or
replace existing Python governance/security gates.

## Deferred

PC-25 does not add:

- production authentication or external IAM;
- a BFF/session service;
- deployment/evidence detail pages;
- recent routing history;
- direct Tempo/Grafana queries or trace deep links;
- dashboards;
- control-plane mutations;
- console Docker packaging;
- one-command demo orchestration;
- Phase 14 consumer integrations.
