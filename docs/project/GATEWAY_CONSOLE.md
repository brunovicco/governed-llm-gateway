# Gateway Console Foundation

## Purpose

PC-25 / OR-5A introduces the first browser-based operator surface for the Governed LLM Gateway. It is a
read-only consumer of the already-reviewed Operations API; it is not a control plane and it does not
create a new source of truth.

The console consumes only:

```text
GET /v1/ops/overview
GET /v1/ops/deployments
```

The console does not call providers, the Policy Router, Tempo, Grafana, Langfuse, secret stores or
configuration files directly. PC-28 adds navigation to the already-reviewed local Grafana dashboard; it
does not add a Grafana API call or data dependency.

## Technology boundary

The application lives at `apps/gateway-console` and uses pinned React, TypeScript and Vite dependencies.
Frontend CI uses Node.js 24 LTS and a committed npm lockfile.

Development traffic remains same-origin from the browser perspective. Vite proxies `/v1` to the local
Gateway process at `http://127.0.0.1:8000`. Production hosting/BFF/session architecture is deferred.

PC-51 hardens only the reviewed local Vite server response boundary. The Console emits
`Content-Security-Policy: frame-ancestors 'none'` plus `X-Frame-Options: DENY` to reject framing, and also
emits `Referrer-Policy: no-referrer` and `X-Content-Type-Options: nosniff`. No script, style or connect CSP
directive is introduced, so this slice does not redefine Vite HMR/runtime connectivity or claim a
production Content Security Policy. Production TLS and hosting headers remain deployment concerns.

## Local development

Start an already-configured governed Gateway process on loopback port `8000`, then run the console in a
separate shell:

```text
cd apps/gateway-console
npm ci --ignore-scripts
npm run dev
```

Vite serves the console on `http://127.0.0.1:5173` and proxies only `/v1` requests to the local Gateway.
The operator must explicitly enter an identity that has the deployment-owned Operations read grant. No
credential is embedded in the build or supplied through a Vite environment variable.

The PC-28 Grafana navigation is available only from that exact reviewed local Console origin. The target
is derived from the validated origin and resolves to the PC-27 dashboard UID
`governed-llm-gateway-traces` on loopback Grafana port `3000`. No environment variable or arbitrary
external observability URL is introduced.

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

PC-28 does not pass the Operations credential or any Operations response data to the Grafana navigation
builder. The generated target has no query string, fragment, userinfo or token. The link opens in a new
tab with `noopener noreferrer` isolation.

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

PC-28 does not add trace IDs, routing history or a trace list. The new link navigates to the existing
Grafana dashboard only; any true per-trace correlation surface requires a separately reviewed source of
correlation evidence rather than inference in the browser.

## Read-only authority boundary

The permanent invariant remains:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

Console visibility is independently granted by `OperationsReadAccessService`. The browser cannot authorize
models, widen or restore PDP output, alter eligibility/complexity/ranking, mutate health/circuit state,
change retry/fallback, execute a provider or edit runtime configuration.

The Console contains no control-plane mutation. The frontend boundary check permits only the already
reviewed provider-neutral `POST /v1/generate` inference action and rejects unreviewed POST/PUT/PATCH/DELETE
request literals, arbitrary absolute HTTP URLs and unreviewed `/v1/ops/*` paths in source. PC-28 preserves
the navigation boundary by constructing the local Grafana target only after validating the runtime Console
origin. PC-51 adds browser anti-framing headers without changing any Gateway request or authority surface.

## Local Grafana navigation

PC-28 adds one bounded navigation affordance after a trusted Operations snapshot has loaded. The link is
rendered only when `window.location.origin` exactly matches the reviewed development origin contract:

```text
protocol: http
hostname: 127.0.0.1
port: 5173
```

The URL builder rejects malformed origins plus unexpected protocol, hostname, port, path, query,
fragment or userinfo. It then changes only the port/path needed to reach the already-certified PC-27
Grafana dashboard. Tests cross-check the Console dashboard UID against the checked-in Grafana dashboard
JSON so the navigation cannot silently drift from provisioning.

The Console does not fetch Grafana or Tempo, proxy their APIs, inspect their health, or treat their
availability as Gateway readiness. The link is descriptive local-demo navigation only.

## CI

`.github/workflows/console-quality.yml` is credential-free and path-scoped. It requires:

```text
npm ci --ignore-scripts
npm run typecheck
npm test
npm run security:surface
npm run build
```

PC-28 extends deterministic frontend tests for the exact accepted/rejected origin contract and dashboard
UID alignment. PC-51 adds a deterministic configuration contract for the exact local browser hardening
headers while re-locking the loopback host, fixed port and relative `/v1` proxy. The existing
security-surface check remains unchanged and continues to reject arbitrary absolute HTTP URLs in Console
source.

The workflow is separate from the Python quality gate so frontend toolchain concerns do not weaken or
replace existing Python governance/security gates.

## Deferred

PC-25/PC-28/PC-51 do not add:

- production authentication or external IAM;
- a BFF/session service;
- deployment/evidence detail pages;
- recent routing history;
- per-trace correlation/deep links by trace ID;
- direct Tempo/Grafana API queries from the Console;
- production Grafana URL discovery or arbitrary external observability URLs;
- broader dashboard navigation;
- control-plane mutations;
- production TLS termination or hosting security policy;
- console Docker packaging;
- one-command demo orchestration;
- Phase 14 consumer integrations.
