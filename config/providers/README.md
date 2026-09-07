# Provider configuration

Provider configuration is deployment-owned by the Governed LLM Gateway. Consumer applications must
not receive provider endpoints or provider credentials; they use only the Gateway URL and Gateway
credential.

The runtime boundary in `governed_llm_gateway_core.adapters.provider_runtime` provides:

- `ProviderRuntimeConfig` for provider/API-family transport metadata plus a credential reference,
  never a credential value;
- `ProviderSecretResolver` for server-side credential resolution;
- `EnvironmentProviderSecretResolver` as the initial resolver implementation;
- `build_static_provider_resolver` for the existing `(provider, api_family)` adapter mapping.

PC-1 adds `runtime.json` as the committed, closed, versioned, secret-free deployment artifact. The
artifact is parsed without provider I/O or secret resolution, receives a deterministic digest after
validation, and is cross-checked against the `(provider, api_family)` pairs required by enabled Model
Registry deployments.

The current `runtime.json` is intentionally empty because `config/model_registry.yaml` still contains
no concrete deployments. Adding a provider binding without a corresponding enabled registry deployment
fails the PC-1 cross-check; enabling a registry deployment without its runtime binding fails as well.
Neither condition has authorization semantics: Policy Model Router remains the authority for which
logical model group may be used.

Custom endpoints are validated before adapter construction and must not be caller-controlled request
values. OpenAI-compatible feature claims remain explicit and fail closed.

See `docs/project/PROVIDER_RUNTIME_CONFIGURATION.md` and
`docs/project/PROVIDER_RUNTIME_ARTIFACT.md` for the full runtime and artifact boundaries.
