# Security Model

## Assets

Provider credentials, PDP credentials/authorization decisions, model registry/ranking policy,
workload identity, prompt/customer payload, routing provenance, runtime health/circuit state, retry
budgets, cost budgets, streaming lifecycle state, and upstream network resources.

## Trust boundaries

1. consumer → gateway authentication;
2. gateway → Policy Model Router;
3. gateway configuration/registry/ranking-policy supply chain;
4. Phase 4 authorized candidate set → Phase 5 ranking;
5. Phase 5 ranked candidates → Phase 6 resilient execution;
6. Phase 6 bounded execution → Phase 7 feature normalization;
7. Phase 7 normalized execution → Phase 8 streaming lifecycle;
8. gateway → provider;
9. gateway → consumer SSE connection;
10. gateway telemetry/evidence sinks;
11. authenticated explain and future administrative/catalog surfaces.

## Authorization

Identity and policy failures fail closed. Operational selection, resilience, feature normalization, and
streaming may only narrow or traverse the set already authorized by the PDP.

Phase 5 validates registry continuity and candidate group membership. Phase 6 pre-validates the bounded
fallback sequence against the original authorized logical model group. Phase 8 reuses only this ranked
sequence and never performs registry-wide fallback after a provider failure.

Caller metadata can request stricter constraints but cannot downgrade authoritative identity,
classification, risk, environment, or authorization.

## Pre-stream governance

`POST /v1/generate` completes authentication, trusted-context resolution, PDP authorization,
runtime-health snapshot, deterministic ranking, and eligible-streaming-candidate checks before
returning SSE.

Policy denial, invalid structured/tool contracts, ranking failures, invariant violations, and absence
of an eligible authorized streaming deployment therefore fail before provider execution and retain
ordinary HTTP error semantics.

## Streaming replay safety

Automatic replay is allowed only before semantic output becomes visible. Provider-native
`response.started` is internal and does not by itself cross the replay boundary.

The boundary is crossed by content or any tool-call output. After that point:

- same-provider retry is forbidden;
- cross-provider fallback is forbidden;
- provider failure is exposed as `response.failed(partial=true, retryable=false)`.

This prevents one public response from combining multiple provider executions.

The Phase 6 `FallbackSafetyState` rules for external side effects and opaque provider state remain in
force and are not weakened by streaming.

## Usage and lifecycle integrity

A successful normalized stream must contain semantic output, exactly one final `usage.completed`, and
then `response.completed`. Duplicate usage, early completion, unknown lifecycle events, or upstream EOF
without normalized completion fail closed.

Provider success is recorded before public completion is emitted.

## Cancellation and upstream ownership

Streaming uses an asynchronous transport whose response/client resources are explicitly owned by the
stream. The API body and core execution generator use deterministic close propagation.

Client disconnect or cancellation closes the gateway generator and upstream provider stream. Client
cancellation is not classified as a provider failure and therefore cannot poison deployment health.

## SSE transport controls

`HttpxSseTransport` requires:

- absolute HTTPS endpoint;
- no URL userinfo;
- no fragment;
- positive timeout;
- maximum 1 MiB per SSE event;
- normalized timeout/network failure categories;
- response-header allowlist limited to `content-type` and `retry-after`;
- explicit/idempotent close.

Provider credentials, arbitrary response headers, and raw provider error bodies do not enter public
SSE events or default evidence.

## Runtime health and circuit state

Circuit state remains per concrete deployment and initially per process. Open/unhealthy state can only
remove/skip deployments. Missing health evidence fails closed when health filtering is active.

Health cannot grant authorization and is not benchmark/ranking evidence.

## Structured-output and tool safety

Phase 7 local schema/tool validation remains mandatory during streaming. Tool arguments can be emitted
incrementally but a canonical completed tool call exists only after full JSON assembly and schema
validation.

The gateway never executes business tools and never fabricates missing provider correlation or opaque
continuation state.

## Configuration integrity

Registry/ranking configuration remains untrusted until strict parsing, duplicate-key rejection,
semantic validation, and deterministic digests succeed. Provider streaming feature flags are execution
capabilities, not authorization grants. OpenAI-compatible streaming remains disabled unless explicitly
verified/configured.

## Explainability and streaming surfaces

`POST /v1/route/explain` remains authenticated, prompt-free, metadata-only, and provider-free.

`POST /v1/generate` necessarily returns requested model output to the authenticated caller but keeps
routing provenance separate from payload content and never exposes a global deployment inventory.

## Secrets and privacy

Consumers receive only gateway credentials. Provider/PDP credentials do not enter consumer contracts,
registry/ranking policy, routing/fallback evidence, normalized errors, or SSE payload metadata.

Default evidence remains metadata-only. Phase 8 does not introduce prompt/completion/tool content into
logs, traces, routing provenance, or future telemetry sinks. Payload capture must not be introduced
implicitly by middleware, exception serialization, streaming transport, cancellation handling, or
future OpenTelemetry exporters.
