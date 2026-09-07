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
- server-side credential environment-variable reference;
- Anthropic API version when applicable;
- explicitly verified OpenAI-compatible transport feature options when applicable.

The object never accepts an API-key/credential value.

Endpoints fail closed during composition unless they are normalized absolute HTTPS URLs with a host and without userinfo, query strings, or fragments. They are deployment configuration, never caller-controlled request fields.

### Secret Resolver

`ProviderSecretResolver` is the server-side credential-resolution port. PC-0 provides `EnvironmentProviderSecretResolver` as the first implementation.

The environment resolver:

- accepts only normalized environment-variable references;
- fails closed when the referenced credential is missing, empty, or malformed;
- never includes the credential value in its exception text;
- returns the raw value only to the provider adapter factory inside the Gateway runtime.

A future implementation can resolve references from AWS Secrets Manager, Azure Key Vault, GCP Secret Manager, Vault, or another deployment-specific secret system without changing consumers, routing contracts, or the Model Registry.

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

`build_static_provider_resolver(...)` resolves provider credentials server-side and creates the existing `StaticProviderResolver` keyed by:

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
    credential_env_var="NVIDIA_API_KEY",
    endpoint="https://nvidia.example/v1/chat/completions",
    openai_compatible=OpenAICompatibleRuntimeOptions(
        supports_streaming=True,
        supports_stream_usage=True,
    ),
)
```

The example hostname is illustrative. Production endpoints remain explicit deployment-owned configuration and must be independently verified before enablement.

## PC-0 scope boundary

PC-0 establishes the typed runtime composition boundary. It deliberately does not add a provider configuration file loader or process bootstrap yet.

The next provider-composition increment can load a closed, versioned deployment artifact, cross-check configured provider/API-family bindings against the Model Registry, and assemble the Gateway application at startup. That work must preserve the same rule: configuration may make an adapter available, but it never authorizes a model.
