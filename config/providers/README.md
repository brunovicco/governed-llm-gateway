# Provider configuration

Provider configuration is deployment-owned by the Governed LLM Gateway. Consumer applications must
not receive provider endpoints or provider credentials; they use only the Gateway URL and Gateway
credential.

PC-0 introduces the typed runtime boundary in
`governed_llm_gateway_core.adapters.provider_runtime`:

- `ProviderRuntimeConfig` stores provider/API-family transport metadata and a credential reference,
  never a credential value;
- `ProviderSecretResolver` resolves provider credentials inside the Gateway process;
- `EnvironmentProviderSecretResolver` is the initial server-side implementation;
- `build_static_provider_resolver` creates the existing `(provider, api_family)` resolver mapping.

Custom endpoints are validated before adapter construction and must not be caller-controlled request
values. OpenAI-compatible feature claims remain explicit and fail closed.

No committed provider configuration artifact or provider secret is added in PC-0. A later PC-1
increment will define the closed deployment file/bootstrap contract and cross-check it against the
Model Registry.

See `docs/project/PROVIDER_RUNTIME_CONFIGURATION.md` for the full boundary and supported API-family
vocabulary.
