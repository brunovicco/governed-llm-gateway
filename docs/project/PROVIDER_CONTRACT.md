# Provider Contract — Phase 3

Phase 3 activates provider execution while keeping authorization, routing, and provider-specific
response types outside the provider contract.

Rule: **API family defines an adapter; concrete model defines registry data.**

Provider adapters have no authorization authority. They execute only a concrete model/deployment
already selected by upstream gateway logic. In later phases that selection must remain inside the
PDP-authorized logical model group.

## Provider-neutral execution boundary

`gateway-core/application/provider.py` defines:

- `ProviderPort` — async text-generation execution port;
- `ProviderRequest` — concrete model, canonical messages, output-token limit, timeout;
- `ProviderResponse` — normalized text, usage, optional response ID, optional finish reason;
- `ProviderUsage` — non-negative input/output token counts;
- `ProviderError` — sanitized failure carrying stable code, retryability, HTTP status, and bounded
  `Retry-After` metadata;
- `ProviderErrorCode` — authentication, rate limit, timeout, invalid request, unavailable, transport,
  invalid response, and unknown.

Provider SDK/response classes never enter `gateway-contracts` or `gateway-core/domain`.

## Initial API-family adapters

- OpenAI Responses — native;
- Anthropic Messages — native;
- Google Gemini `generateContent` — native;
- OpenAI-compatible chat completions — explicit configuration for compatible providers such as
  NVIDIA, Groq, OpenRouter, or internal endpoints.

"OpenAI-compatible" means transport/API compatibility only. Provider quirks remain explicit. Phase 3
already models the `max_tokens` versus `max_completion_tokens` difference rather than pretending all
compatible endpoints behave identically.

## Transport and security

The initial adapters use an injectable JSON transport with a stdlib HTTPS implementation.

Security properties:

- provider endpoints must use absolute HTTPS URLs;
- a bounded response size is enforced;
- request timeouts are explicit;
- non-2xx response bodies are not parsed into or retained by `ProviderError`;
- API keys and authorization headers are not included in error messages;
- malformed successful responses fail as typed `INVALID_RESPONSE` errors;
- 401/403 are non-retryable authentication errors;
- 429 is a retryable rate-limit error;
- 408/504 are retryable timeout errors;
- 5xx responses are retryable unavailable errors;
- Phase 3 classifies retryability but does not perform retry/fallback itself.

## Google Gemini API choice

As of June 2026, Google recommends the Interactions API for new Gemini development and considers
`generateContent` legacy, while continuing to fully support it.

The Phase 3 adapter intentionally uses native `generateContent` for the current provider-neutral
contract. `ProviderRequest` carries canonical message history. Stateless Interactions requires the
caller to preserve and resend the model-generated Interaction steps exactly, including intermediate
steps when present. Reconstructing those provider-native steps from canonical assistant text would be
a lossy translation and would create hidden provider state semantics.

A future Interactions adapter should therefore be introduced only with an explicit provider-state
contract or a deliberate stateful interaction design. The gateway must not synthesize provider
reasoning state merely to follow a newer endpoint.

## Phase 3 scope boundary

Supported now:

- text generation;
- token usage extraction;
- timeout propagation/classification;
- typed provider errors;
- sanitized failure metadata;
- contract tests with injected fake transports.

Deferred to later roadmap phases:

- PDP authorization integration;
- operational ranking/provider selection;
- retry/fallback/circuit breakers;
- tool normalization/execution;
- structured-output normalization;
- streaming;
- OpenTelemetry runtime instrumentation.
