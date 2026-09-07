# Provider Runtime Configuration

## Product intent

Consumer applications should know only the Governed LLM Gateway endpoint and a Gateway credential. They must not receive or duplicate OpenAI, Anthropic, Google/Gemini, NVIDIA, or other provider credentials.

Provider endpoint configuration and provider credentials are deployment concerns owned by the Gateway runtime.

```text
consumer application
    ├─ GOVERNED_LLM_GATEWAY_URL
    └─ GOVERNED_LLM_GATEWAY_API_KEY
                ↓
        Governed LLM Gateway
                ↓
    Model Registry + Provider Runtime Config
                ↓
       server-side Secret Resolver
                ↓
        configured ProviderResolver
                ↓
 OpenAI / Anthropic / Gemini / compatible providers
```

## Separation of responsibilities

### Model Registry

The Model Registry remains provider/model/deployment metadata and routing evidence. It contains model identity, logical model group, API family, capabilities, context capacity, pricing evidence, environment restrictions, classification limits, and catalog provenance.

It does **not** contain provider credentials and registry membership does not grant authorization.

### Provider Runtime Config

`ProviderRuntimeConfig` binds one provider identity and API family to deployment-owned transport configuration:

- provider identifier;
- canonical API family;
- provider endpoint/base URL;
- server-side `credential_reference` understood by the injected secret resolver;
- Anthropic API version when applicable;
- explicitly verified OpenAI-compatible transport feature options when applicable.

The object never accepts an API-key/credential value. The credential reference is intentionally resolver-neutral: an environment deployment can use `OPENAI_API_KEY`, while a future secret backend can use a provider-specific identifier such as `vault://providers/openai` without changing the runtime configuration schema.

Endpoints fail closed during composition unless they are normalized absolute HTTPS URLs with a host and without userinfo, query strings, or fragments. They are deployment configuration, never caller-controlled request fields.

### Secret Resolver

`ProviderSecretResolver` is the server-side credential-resolution port. PC-0 provides `EnvironmentProviderSecretResolver` as the first implementation.

The environment resolver:

- accepts only normalized environment-variable references;
- fails closed when the referenced credential is missing, empty, or malformed;
- never includes the credential value or reference in its exception text;
- returns the raw value only to the provider adapter factory inside the Gateway runtime.

`build_static_provider_resolver(...)` wraps arbitrary secret-backend exceptions into a bounded `ProviderSecretResolutionError` without preserving backend exception text in the visible chain. It also validates returned credential values before adapter construction.

A future implementation can resolve references from AWS Secrets Manager, Azure Key Vault, GCP Secret Manager, Vault, or another deployment-specific secret system without changing consumers, routing contracts, `ProviderRuntimeConfig`, or the Model Registry.

## Canonical API families

PC-0 makes the implemented adapter families explicit:

| API family | Native provider identity | Adapter strategy |
| --- | --- | --- |
| `openai-responses` | `openai` | native OpenAI Responses, streaming-capable |
| `anthropic-messages` | `anthropic` | native Anthropic Messages, streaming-capable |
| `gemini-generate-content` | `google` | native Gemini generateContent/streamGenerateContent |
| `openai-compatible` | explicit configured provider | compatible chat completions with opt-in features |

Native API-family/provider mismatches fail closed. For example, a provider named `nvidia` cannot be configured as `openai-responses`.

NVIDIA, Groq, OpenRouter, internal gateways, and other endpoints that have been verified as OpenAI-compatible use `openai-compatible`. This is transport compatibility only; it does not imply capability equivalence.

## OpenAI-compatible feature verification

`OpenAICompatibleRuntimeOptions` keeps endpoint quirks and feature claims explicit:

- `max_tokens` versus `max_completion_tokens`;
- native structured output support;
- native tool calling support;
- streaming support;
- final streaming usage support.

Streaming is enabled only when final usage support is also explicitly verified. An endpoint configured without streaming stays non-streaming even though another compatible provider might support it.

This adapter capability evidence remains separate from the Model Registry. A registry deployment must still declare the corresponding capability, and routing must still have authorized/selected that deployment before execution.

## Composition

`build_static_provider_resolver(...)` validates the complete provider configuration set before invoking any secret resolver. Duplicate `(provider, api_family)` bindings or malformed config therefore fail before secret-manager access or adapter construction.

Only after structural validation does composition resolve credentials server-side and create the existing `StaticProviderResolver` keyed by:

```text
(provider, api_family)
```

Native families use their streaming-capable adapters so one configured binding can satisfy both normalized non-streaming provider execution and the current SSE generation path. OpenAI-compatible endpoints use the streaming variant only when streaming plus final-usage support were explicitly enabled.

The configured resolver has no authorization authority. It can only resolve the adapter for a concrete deployment already selected by governed routing.

## Example composition

The following example contains only a secret reference, not a secret value:

```python
ProviderRuntimeConfig(
    provider="nvidia",
    api_family=ProviderApiFamily.OPENAI_COMPATIBLE,
    credential_reference="NVIDIA_API_KEY",
    endpoint="https://nvidia.example/v1/chat/completions",
    openai_compatible=OpenAICompatibleRuntimeOptions(
        supports_streaming=True,
        supports_stream_usage=True,
    ),
)
```

The example hostname is illustrative. Production endpoints remain explicit deployment-owned configuration and must be independently verified before enablement.

## Versioned artifact and bootstrap progression

PC-0 established the typed provider configuration and server-side secret-resolution boundary.

PC-1 added the closed JSON provider-runtime artifact at `config/providers/runtime.json`, deterministic configuration provenance, and exact cross-checking against the enabled `(provider, api_family)` requirement set from `config/model_registry.yaml`. The checked-in artifacts remain intentionally empty and credential-free until reviewed live provider entries are introduced.

PC-2 adds the API composition helper `bootstrap_provider_runtime(...)`. It is deliberately a one-shot provider-runtime bootstrap rather than a global application singleton. The required startup ordering is:

```text
explicit local paths
    -> load Model Registry
    -> load provider runtime artifact
    -> exact registry/runtime cross-check
    -> server-side ProviderSecretResolver
    -> StaticProviderResolver
    -> immutable ProviderRuntimeBootstrapBundle
```

The registry/runtime cross-check occurs before any provider credential is resolved. A malformed artifact, missing binding, or extra binding therefore fails closed without secret-backend access.

The immutable bootstrap bundle exposes:

- the validated `ModelRegistry`;
- the validated `ProviderRuntimeDocument`;
- deterministic model-registry and provider-runtime digests;
- the provider-runtime `config_version`;
- the configured `StaticProviderResolver` used only after governed routing has selected a concrete deployment.

It does not expose raw provider credentials and it does not create provider candidates, model groups, ranking scores, policy decisions, health state, or fallback authority.

## Full process bootstrap remains a separate increment

The FastAPI package already exposes dependency-injected route/application factories, but provider composition is only one part of a complete Gateway process. Policy Router authentication/configuration, trusted client-context resolution, ranking-policy composition, health lifecycle, observability process setup, and deployment entrypoint configuration must be composed explicitly rather than hidden behind mutable module globals.

PC-2 therefore does **not** add a module-level `FastAPI` application, `uvicorn` entrypoint, container command, request-time provider config reload, file watcher, adaptive provider discovery, or cloud-specific secret-manager implementation.

A later process-bootstrap increment may assemble those independently reviewed dependencies around this provider bundle. That future composition must preserve the permanent authority rule: provider configuration can make an adapter operationally available, but it can never authorize, widen, rank, or resurrect a model candidate.
