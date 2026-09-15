# ADR-0017 — Deterministic Streaming Preflight

- Status: Accepted
- Date: 2026-09-15
- Supersedes: the incomplete pre-stream boundary described by ADR-0011

## Context

ADR-0011 requires authorization and ranking to finish before SSE begins. The implementation still
constructed `ProviderRequest`, resolved and checked provider adapters, and built provider-native
payloads inside an async generator. Python does not execute an async-generator body when it is
created. Starlette could therefore commit `HTTP 200` and only then discover a deterministic schema,
capability, adapter, deployment, endpoint, or provider-request construction error.

Those failures are not provider runtime failures. Encoding them as a failed stream after a successful
HTTP status makes clients observe a response that should never have started and makes Anthropic and
OpenAI compatibility error envelopes impossible to return correctly.

The authorization invariant remains unchanged:

```text
Gateway allowed set ⊆ Policy Router authorized set
```

## Decision

### Preparation is a synchronous, no-I/O execution phase

`StreamingExecutionService.prepare(...)` consumes the canonical request and the already-authorized
ranking decision and returns an immutable `StreamingExecutionPlan`. Preparation completes before the
API constructs `StreamingResponse`.

For every authorized candidate retained by the configured fallback bound, preparation:

1. rechecks the authorized model-group and streaming-capability invariants;
2. resolves the configured provider adapter;
3. verifies native streaming and final-usage support;
4. constructs the immutable provider-neutral `ProviderRequest` exactly once;
5. invokes the adapter's synchronous `prepare_stream(...)` boundary;
6. constructs and validates provider-native payload and transport inputs without provider I/O.

A tool-result continuation remains single-candidate and single-attempt. Ordinary replay-safe requests
prepare the selected candidate plus only the already-ranked alternatives allowed by
`max_fallbacks`. Preparation never enumerates the registry or adds a candidate.

### Provider preparation is opaque and reusable

An adapter returns `PreparedProviderStream`, an opaque factory whose captured state has passed all
deterministic request construction. The execution plan retains that object and the corresponding
`ProviderRequest`. Retry opens a new runtime attempt from the same prepared state; it does not rebuild
or revalidate the provider request.

Direct adapter `stream(request)` remains a compatibility entry point implemented as
`prepare_stream(request).stream()`. Governed execution uses the prepared object directly.

### Runtime streaming consumes only the plan

`StreamingExecutionService.stream(...)` accepts only `StreamingExecutionPlan`. It may perform:

- cache lookup/write under an already-computed cache identity;
- mutable circuit/health checks;
- provider connection and network I/O;
- provider HTTP-status and event parsing;
- normalized response lifecycle, usage, structured-output, and tool-call validation;
- retry/fallback decisions for runtime provider failures;
- cancellation and resource closure.

Provider-returned malformed output remains a runtime failure because it cannot be known before the
provider responds. Transport timeouts, connection failures, provider HTTP failures, cancellation, and
health races likewise remain valid post-commit stream failures.

### Deterministic failures retain ordinary HTTP semantics

Authentication, policy, routing, ranking, deployment, capability, adapter resolution, schema,
provider-request, provider-payload, and transport-input construction failures occur while the route
can still return a normal HTTP error. Protocol ingress maps only stable sanitized codes; provider
credentials, payloads, and raw errors are never exposed.

Capability or deployment configuration failures return service-unavailable semantics. Invalid
provider request construction returns client-invalid-request semantics, including Anthropic's
`invalid_request_error` envelope.

## Consequences

### Positive

- deterministic failures cannot follow a committed streaming `200`;
- all bounded fallback candidates are known executable before streaming starts;
- retries reuse one provider request and one provider-native preparation, eliminating reconstruction
  drift;
- Anthropic and OpenAI ingress can render their normal pre-stream error envelopes;
- authorization, ranking, retry, fallback, and tool-execution boundaries remain unchanged.

### Trade-offs

- preparation performs provider-payload construction for fallbacks that may never execute;
- adapters must separate pure preparation from runtime response handling;
- provider configuration errors are detected on each request, before response commit, rather than
  first provider use after commit;
- runtime health may still change between preparation and an attempt, so execution rechecks only that
  mutable state.

## Rejected alternatives

### Catch deterministic exceptions inside the SSE generator

Rejected because response headers may already be committed and the protocol-compatible HTTP error is
no longer available.

### Prepare only the selected candidate

Rejected because a deterministic defect in a bounded fallback would otherwise still be discovered
after the response starts.

### Rebuild the provider request on every retry

Rejected because duplicate validation permits implementation drift and a time-of-check/time-of-use
split between preflight and execution.

### Remove an invalid fallback and continue

Rejected because silently pruning a ranked deployment hides configuration failure and weakens the
gateway's fail-closed behavior.
