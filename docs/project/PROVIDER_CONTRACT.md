# Provider Contract — Phase 0 Draft

Provider execution is intentionally not implemented in Phase 0.

Future provider ports normalize text/content, tool calls, usage, latency, status, typed errors, and
provider reasoning state where replay safety requires it. Provider-specific response classes never
enter `gateway-contracts` or `gateway-core/domain`.

Initial adapter families planned by the source roadmap:

- OpenAI Responses — native;
- Anthropic Messages — native;
- Google Gemini — native;
- OpenAI-compatible — explicit configuration for NVIDIA, Groq, OpenRouter, and custom compatible
  endpoints.

Rule: **API family defines an adapter; concrete model defines registry data.**

"OpenAI-compatible" is transport/API compatibility only. Capabilities and quirks remain explicit and
unsupported behavior must never be faked.
