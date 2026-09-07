"""Contract tests for the secret-free PC-3 multi-provider reference bundle."""

from pathlib import Path

from governed_llm_gateway_contracts import DataClassification
from governed_llm_gateway_core.adapters import (
    EnvironmentProviderSecretResolver,
    OpenAICompatibleAdapter,
    ProviderApiFamily,
    build_static_provider_resolver,
    load_model_registry,
    load_provider_runtime_document,
    validate_provider_runtime_registry,
)
from governed_llm_gateway_core.adapters.anthropic_streaming import (
    AnthropicMessagesStreamingAdapter,
)
from governed_llm_gateway_core.adapters.gemini_streaming import GeminiStreamingAdapter
from governed_llm_gateway_core.adapters.openai_responses_streaming import (
    OpenAIResponsesStreamingAdapter,
)

_ROOT = Path(__file__).resolve().parents[2]
_REFERENCE = _ROOT / "config" / "reference" / "multi-provider"
_OPAQUE_VALUE = "pc3-opaque-runtime-value"


def test_reference_bundle_has_exact_reviewed_provider_family_set() -> None:
    registry = load_model_registry(_REFERENCE / "model_registry.yaml")
    runtime = load_provider_runtime_document(_REFERENCE / "provider_runtime.json")

    validate_provider_runtime_registry(runtime, registry)

    assert registry.catalog_version == "pc3-reference-20260907"
    assert runtime.config_version == "pc3-reference-20260907"
    assert len(registry.deployments) == 4
    assert {
        (deployment.provider, deployment.api_family) for deployment in registry.deployments
    } == {
        ("openai", ProviderApiFamily.OPENAI_RESPONSES.value),
        ("anthropic", ProviderApiFamily.ANTHROPIC_MESSAGES.value),
        ("google", ProviderApiFamily.GEMINI_GENERATE_CONTENT.value),
        ("nvidia", ProviderApiFamily.OPENAI_COMPATIBLE.value),
    }
    assert {(binding.provider, binding.api_family.value) for binding in runtime.bindings} == {
        ("openai", ProviderApiFamily.OPENAI_RESPONSES.value),
        ("anthropic", ProviderApiFamily.ANTHROPIC_MESSAGES.value),
        ("google", ProviderApiFamily.GEMINI_GENERATE_CONTENT.value),
        ("nvidia", ProviderApiFamily.OPENAI_COMPATIBLE.value),
    }

    for deployment in registry.deployments:
        assert deployment.model_group == "reference-general"
        assert deployment.context_tokens == 32_768
        assert deployment.pricing is None
        assert deployment.max_data_classification is DataClassification.PUBLIC
        assert deployment.allowed_environments == frozenset({"benchmark", "development"})
        assert deployment.enabled is True


def test_reference_bundle_composes_provider_adapters_from_server_side_secrets() -> None:
    registry = load_model_registry(_REFERENCE / "model_registry.yaml")
    runtime = load_provider_runtime_document(_REFERENCE / "provider_runtime.json")
    validate_provider_runtime_registry(runtime, registry)

    resolver = build_static_provider_resolver(
        runtime.bindings,
        EnvironmentProviderSecretResolver(
            {
                "OPENAI_API_KEY": _OPAQUE_VALUE,
                "ANTHROPIC_API_KEY": _OPAQUE_VALUE,
                "GEMINI_API_KEY": _OPAQUE_VALUE,
                "NVIDIA_API_KEY": _OPAQUE_VALUE,
            }
        ),
    )

    assert isinstance(
        resolver.resolve(registry.by_id("openai-gpt-5-6-luna-reference")),
        OpenAIResponsesStreamingAdapter,
    )
    assert isinstance(
        resolver.resolve(registry.by_id("anthropic-claude-sonnet-5-reference")),
        AnthropicMessagesStreamingAdapter,
    )
    assert isinstance(
        resolver.resolve(registry.by_id("google-gemini-3-8-flash-reference")),
        GeminiStreamingAdapter,
    )
    assert isinstance(
        resolver.resolve(registry.by_id("nvidia-llama-3-3-70b-reference")),
        OpenAICompatibleAdapter,
    )
    assert _OPAQUE_VALUE not in repr(runtime)


def test_reference_bundle_keeps_provider_credentials_as_references_only() -> None:
    runtime = load_provider_runtime_document(_REFERENCE / "provider_runtime.json")

    assert {binding.credential_reference for binding in runtime.bindings} == {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "NVIDIA_API_KEY",
    }
    for binding in runtime.bindings:
        assert not hasattr(binding, "api_key")
        assert not hasattr(binding, "credential")
        assert _OPAQUE_VALUE not in repr(binding)


def test_nvidia_reference_is_explicitly_non_streaming_openai_compatible() -> None:
    registry = load_model_registry(_REFERENCE / "model_registry.yaml")
    runtime = load_provider_runtime_document(_REFERENCE / "provider_runtime.json")

    deployment = registry.by_id("nvidia-llama-3-3-70b-reference")
    binding = next(item for item in runtime.bindings if item.provider == "nvidia")

    assert deployment.model_id == "meta/llama-3.3-70b-instruct"
    assert deployment.api_family == ProviderApiFamily.OPENAI_COMPATIBLE.value
    assert binding.api_family is ProviderApiFamily.OPENAI_COMPATIBLE
    assert binding.endpoint == "https://nvidia-nim.example/v1/chat/completions"
    assert binding.openai_compatible is not None
    assert binding.openai_compatible.supports_streaming is False
    assert binding.openai_compatible.supports_stream_usage is False
    assert binding.openai_compatible.supports_native_structured_output is False
    assert binding.openai_compatible.supports_native_tool_calling is False


def test_reference_bundle_does_not_activate_default_runtime_artifacts() -> None:
    default_registry = load_model_registry(_ROOT / "config" / "model_registry.yaml")
    default_runtime = load_provider_runtime_document(
        _ROOT / "config" / "providers" / "runtime.json"
    )
    reference_registry = load_model_registry(_REFERENCE / "model_registry.yaml")
    reference_runtime = load_provider_runtime_document(_REFERENCE / "provider_runtime.json")

    assert default_registry.deployments == ()
    assert default_runtime.bindings == ()
    assert len(reference_registry.deployments) == 4
    assert len(reference_runtime.bindings) == 4
