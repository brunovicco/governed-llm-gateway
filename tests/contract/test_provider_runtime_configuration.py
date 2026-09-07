"""Contract tests for deployment-owned provider runtime configuration."""

from datetime import date
from decimal import Decimal
from typing import cast

import pytest
from governed_llm_gateway_contracts import Capability, DataClassification, Modality
from governed_llm_gateway_core.adapters import (
    EnvironmentProviderSecretResolver,
    OpenAICompatibleRuntimeOptions,
    ProviderApiFamily,
    ProviderRuntimeConfig,
    ProviderRuntimeConfigurationError,
    ProviderSecretResolutionError,
    build_static_provider_resolver,
)
from governed_llm_gateway_core.adapters.anthropic_streaming import (
    AnthropicMessagesStreamingAdapter,
)
from governed_llm_gateway_core.adapters.gemini_streaming import GeminiStreamingAdapter
from governed_llm_gateway_core.adapters.openai_compatible import OpenAICompatibleAdapter
from governed_llm_gateway_core.adapters.openai_compatible_streaming import (
    OpenAICompatibleStreamingAdapter,
)
from governed_llm_gateway_core.adapters.openai_responses_streaming import (
    OpenAIResponsesStreamingAdapter,
)
from governed_llm_gateway_core.application.provider import ProviderStreamingPort
from governed_llm_gateway_core.domain import ModelDeployment, PricingMetadata

_OPAQUE_VALUE = "runtime-value-must-not-appear"
_TODAY = date(2026, 9, 7)


def _config(
    provider: str,
    api_family: ProviderApiFamily,
    credential_env_var: str,
    endpoint: str,
    *,
    anthropic_api_version: str | None = None,
    compatible: OpenAICompatibleRuntimeOptions | None = None,
) -> ProviderRuntimeConfig:
    return ProviderRuntimeConfig(
        provider=provider,
        api_family=api_family,
        credential_env_var=credential_env_var,
        endpoint=endpoint,
        anthropic_api_version=anthropic_api_version,
        openai_compatible=compatible,
    )


def _deployment(provider: str, api_family: ProviderApiFamily) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=f"{provider}-deployment",
        provider=provider,
        model_id=f"model/{provider}",
        model_group="general",
        api_family=api_family.value,
        capabilities=frozenset({Capability.TEXT, Capability.STREAMING}),
        context_tokens=128_000,
        modalities=frozenset({Modality.TEXT}),
        pricing=PricingMetadata(
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("2"),
            source_date=_TODAY,
            snapshot_version="pricing-v1",
        ),
        max_data_classification=DataClassification.INTERNAL,
        allowed_environments=frozenset({"prod"}),
        enabled=True,
        source_date=_TODAY,
        catalog_version="catalog-v1",
    )


def test_provider_api_family_vocabulary_is_stable() -> None:
    assert tuple(item.value for item in ProviderApiFamily) == (
        "openai-responses",
        "anthropic-messages",
        "gemini-generate-content",
        "openai-compatible",
    )


def test_runtime_config_contains_only_credential_reference() -> None:
    config = _config(
        "openai",
        ProviderApiFamily.OPENAI_RESPONSES,
        "OPENAI_API_KEY",
        "https://api.openai.example/v1/responses",
    )

    assert config.credential_env_var == "OPENAI_API_KEY"
    assert _OPAQUE_VALUE not in repr(config)
    assert not hasattr(config, "api_key")
    assert not hasattr(config, "credential")


@pytest.mark.parametrize(
    "endpoint",
    (
        "http://provider.example/v1",
        "https://user:pass@provider.example/v1",
        "https://provider.example/v1?tenant=caller",
        "https://provider.example/v1#fragment",
        " provider.example ",
    ),
)
def test_runtime_config_rejects_unsafe_endpoint_shapes(endpoint: str) -> None:
    with pytest.raises(ProviderRuntimeConfigurationError):
        _config(
            "openai",
            ProviderApiFamily.OPENAI_RESPONSES,
            "OPENAI_API_KEY",
            endpoint,
        )


def test_native_api_family_rejects_provider_identity_substitution() -> None:
    with pytest.raises(ProviderRuntimeConfigurationError, match="requires provider"):
        _config(
            "nvidia",
            ProviderApiFamily.OPENAI_RESPONSES,
            "NVIDIA_API_KEY",
            "https://nvidia.example/v1/responses",
        )


def test_compatible_runtime_options_require_stream_usage_with_streaming() -> None:
    with pytest.raises(ProviderRuntimeConfigurationError, match="final usage"):
        OpenAICompatibleRuntimeOptions(
            supports_streaming=True,
            supports_stream_usage=False,
        )


def test_environment_secret_resolution_fails_closed_without_secret_contents() -> None:
    resolver = EnvironmentProviderSecretResolver(
        {
            "EMPTY_PROVIDER_KEY": "",
            "MALFORMED_PROVIDER_KEY": f" {_OPAQUE_VALUE} ",
        }
    )

    for reference in (
        "MISSING_PROVIDER_KEY",
        "EMPTY_PROVIDER_KEY",
        "MALFORMED_PROVIDER_KEY",
    ):
        with pytest.raises(ProviderSecretResolutionError) as caught:
            resolver.resolve(reference)
        assert _OPAQUE_VALUE not in str(caught.value)


def test_factory_builds_native_streaming_adapters_from_server_side_secrets() -> None:
    configs = (
        _config(
            "openai",
            ProviderApiFamily.OPENAI_RESPONSES,
            "OPENAI_API_KEY",
            "https://api.openai.example/v1/responses",
        ),
        _config(
            "anthropic",
            ProviderApiFamily.ANTHROPIC_MESSAGES,
            "ANTHROPIC_API_KEY",
            "https://api.anthropic.example/v1/messages",
            anthropic_api_version="2023-06-01",
        ),
        _config(
            "google",
            ProviderApiFamily.GEMINI_GENERATE_CONTENT,
            "GEMINI_API_KEY",
            "https://generativelanguage.example/v1beta/models",
        ),
    )
    resolver = build_static_provider_resolver(
        configs,
        EnvironmentProviderSecretResolver(
            {
                "OPENAI_API_KEY": _OPAQUE_VALUE,
                "ANTHROPIC_API_KEY": _OPAQUE_VALUE,
                "GEMINI_API_KEY": _OPAQUE_VALUE,
            }
        ),
    )

    assert isinstance(
        resolver.resolve(_deployment("openai", ProviderApiFamily.OPENAI_RESPONSES)),
        OpenAIResponsesStreamingAdapter,
    )
    assert isinstance(
        resolver.resolve(_deployment("anthropic", ProviderApiFamily.ANTHROPIC_MESSAGES)),
        AnthropicMessagesStreamingAdapter,
    )
    assert isinstance(
        resolver.resolve(_deployment("google", ProviderApiFamily.GEMINI_GENERATE_CONTENT)),
        GeminiStreamingAdapter,
    )


def test_nvidia_uses_explicit_openai_compatible_streaming_family() -> None:
    config = _config(
        "nvidia",
        ProviderApiFamily.OPENAI_COMPATIBLE,
        "NVIDIA_API_KEY",
        "https://nvidia.example/v1/chat/completions",
        compatible=OpenAICompatibleRuntimeOptions(
            max_tokens_field="max_tokens",
            supports_native_structured_output=True,
            supports_native_tool_calling=True,
            supports_streaming=True,
            supports_stream_usage=True,
        ),
    )
    resolver = build_static_provider_resolver(
        (config,),
        EnvironmentProviderSecretResolver({"NVIDIA_API_KEY": _OPAQUE_VALUE}),
    )

    adapter = resolver.resolve(_deployment("nvidia", ProviderApiFamily.OPENAI_COMPATIBLE))
    assert isinstance(adapter, OpenAICompatibleStreamingAdapter)
    assert isinstance(adapter, ProviderStreamingPort)
    assert adapter.feature_support.native_streaming is True
    assert adapter.feature_support.streaming_usage is True
    assert _OPAQUE_VALUE not in repr(config)


def test_non_streaming_compatible_config_does_not_gain_streaming_support() -> None:
    config = _config(
        "compatible-provider",
        ProviderApiFamily.OPENAI_COMPATIBLE,
        "COMPATIBLE_API_KEY",
        "https://compatible.example/v1/chat/completions",
        compatible=OpenAICompatibleRuntimeOptions(),
    )
    resolver = build_static_provider_resolver(
        (config,),
        EnvironmentProviderSecretResolver({"COMPATIBLE_API_KEY": _OPAQUE_VALUE}),
    )

    adapter = resolver.resolve(
        _deployment("compatible-provider", ProviderApiFamily.OPENAI_COMPATIBLE)
    )
    assert isinstance(adapter, OpenAICompatibleAdapter)
    assert not isinstance(adapter, ProviderStreamingPort)


def test_duplicate_provider_api_family_binding_fails_closed() -> None:
    first = _config(
        "openai",
        ProviderApiFamily.OPENAI_RESPONSES,
        "OPENAI_API_KEY",
        "https://api.openai.example/v1/responses",
    )
    duplicate = _config(
        "openai",
        ProviderApiFamily.OPENAI_RESPONSES,
        "OPENAI_SECONDARY_API_KEY",
        "https://secondary.openai.example/v1/responses",
    )

    with pytest.raises(
        ProviderRuntimeConfigurationError,
        match="duplicate provider runtime binding",
    ):
        build_static_provider_resolver(
            (first, duplicate),
            EnvironmentProviderSecretResolver(
                {
                    "OPENAI_API_KEY": _OPAQUE_VALUE,
                    "OPENAI_SECONDARY_API_KEY": _OPAQUE_VALUE,
                }
            ),
        )


def test_runtime_config_rejects_non_contract_values_at_runtime() -> None:
    with pytest.raises(ProviderRuntimeConfigurationError, match="api_family"):
        ProviderRuntimeConfig(
            provider="openai",
            api_family=cast(ProviderApiFamily, "openai-responses"),
            credential_env_var="OPENAI_API_KEY",
            endpoint="https://api.openai.example/v1/responses",
        )
