"""Deployment-owned provider configuration and server-side credential composition."""

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit

from governed_llm_gateway_core.application.provider import ProviderPort
from governed_llm_gateway_core.application.resilience import StaticProviderResolver

from .anthropic_streaming import AnthropicMessagesStreamingAdapter
from .gemini_streaming import GeminiStreamingAdapter
from .openai_compatible import OpenAICompatibleAdapter
from .openai_compatible_streaming import OpenAICompatibleStreamingAdapter
from .openai_responses_streaming import OpenAIResponsesStreamingAdapter

_PROVIDER_IDENTIFIER = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_ENV_REFERENCE = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
_DEFAULT_ANTHROPIC_API_VERSION = "2023-06-01"


class ProviderRuntimeConfigurationError(ValueError):
    """Raised when deployment-owned provider configuration cannot fail closed safely."""


class ProviderSecretResolutionError(RuntimeError):
    """Raised when a configured server-side provider credential cannot be resolved."""


class ProviderApiFamily(StrEnum):
    """Canonical API families implemented by the gateway provider adapters."""

    OPENAI_RESPONSES = "openai-responses"
    ANTHROPIC_MESSAGES = "anthropic-messages"
    GEMINI_GENERATE_CONTENT = "gemini-generate-content"
    OPENAI_COMPATIBLE = "openai-compatible"


@dataclass(frozen=True, slots=True)
class OpenAICompatibleRuntimeOptions:
    """Explicitly verified wire-level features for one compatible provider endpoint."""

    max_tokens_field: str = "max_tokens"
    supports_native_structured_output: bool = False
    supports_native_tool_calling: bool = False
    supports_streaming: bool = False
    supports_stream_usage: bool = False

    def __post_init__(self) -> None:
        """Fail closed on unsupported token fields or incoherent streaming claims."""
        if self.max_tokens_field not in {"max_tokens", "max_completion_tokens"}:
            raise ProviderRuntimeConfigurationError(
                "openai-compatible max_tokens_field is unsupported"
            )
        for name, value in (
            ("supports_native_structured_output", self.supports_native_structured_output),
            ("supports_native_tool_calling", self.supports_native_tool_calling),
            ("supports_streaming", self.supports_streaming),
            ("supports_stream_usage", self.supports_stream_usage),
        ):
            if not isinstance(value, bool):
                raise ProviderRuntimeConfigurationError(f"{name} must be boolean")
        if self.supports_streaming != self.supports_stream_usage:
            raise ProviderRuntimeConfigurationError(
                "openai-compatible streaming requires verified final usage support"
            )


@dataclass(frozen=True, slots=True)
class ProviderRuntimeConfig:
    """Secret-free configuration for one provider/API-family adapter binding."""

    provider: str
    api_family: ProviderApiFamily
    credential_env_var: str
    endpoint: str
    anthropic_api_version: str | None = None
    openai_compatible: OpenAICompatibleRuntimeOptions | None = None

    def __post_init__(self) -> None:
        """Validate immutable deployment-owned configuration before adapter construction."""
        if (
            not isinstance(self.provider, str)
            or _PROVIDER_IDENTIFIER.fullmatch(self.provider) is None
        ):
            raise ProviderRuntimeConfigurationError("provider must be a normalized identifier")
        if not isinstance(self.api_family, ProviderApiFamily):
            raise ProviderRuntimeConfigurationError("api_family must use ProviderApiFamily")
        if (
            not isinstance(self.credential_env_var, str)
            or _ENV_REFERENCE.fullmatch(self.credential_env_var) is None
        ):
            raise ProviderRuntimeConfigurationError(
                "credential_env_var must be a normalized environment-variable name"
            )
        _validate_endpoint(self.endpoint)
        self._validate_family_configuration()

    def _validate_family_configuration(self) -> None:
        native_provider = {
            ProviderApiFamily.OPENAI_RESPONSES: "openai",
            ProviderApiFamily.ANTHROPIC_MESSAGES: "anthropic",
            ProviderApiFamily.GEMINI_GENERATE_CONTENT: "google",
        }.get(self.api_family)
        if native_provider is not None and self.provider != native_provider:
            raise ProviderRuntimeConfigurationError(
                f"{self.api_family.value} requires provider {native_provider!r}"
            )

        if self.api_family is ProviderApiFamily.ANTHROPIC_MESSAGES:
            if self.anthropic_api_version is not None:
                _require_normalized_value(
                    self.anthropic_api_version,
                    "anthropic_api_version",
                )
        elif self.anthropic_api_version is not None:
            raise ProviderRuntimeConfigurationError(
                "anthropic_api_version is valid only for anthropic-messages"
            )

        if self.api_family is ProviderApiFamily.OPENAI_COMPATIBLE:
            if not isinstance(self.openai_compatible, OpenAICompatibleRuntimeOptions):
                raise ProviderRuntimeConfigurationError(
                    "openai-compatible providers require explicit runtime options"
                )
        elif self.openai_compatible is not None:
            raise ProviderRuntimeConfigurationError(
                "openai_compatible options are valid only for openai-compatible providers"
            )


class ProviderSecretResolver(Protocol):
    """Resolve one server-side credential reference without exposing it to consumers."""

    def resolve(self, reference: str) -> str:
        """Return the raw provider credential or fail closed with sanitized metadata."""
        ...


class EnvironmentProviderSecretResolver:
    """Resolve provider credentials from the gateway process environment."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        """Bind a mapping for tests or use the current gateway process environment."""
        self._environ = os.environ if environ is None else environ

    def resolve(self, reference: str) -> str:
        """Resolve a normalized environment reference without surfacing credential values."""
        if _ENV_REFERENCE.fullmatch(reference) is None:
            raise ProviderSecretResolutionError("provider credential reference is invalid")
        value = self._environ.get(reference)
        if value is None or not value or value.strip() != value:
            raise ProviderSecretResolutionError(
                f"provider credential {reference!r} is unavailable or malformed"
            )
        return value


def build_static_provider_resolver(
    configs: Sequence[ProviderRuntimeConfig],
    secrets: ProviderSecretResolver,
) -> StaticProviderResolver:
    """Build one immutable resolver from validated configs and server-side credentials."""
    providers: dict[tuple[str, str], ProviderPort] = {}
    for config in configs:
        if not isinstance(config, ProviderRuntimeConfig):
            raise ProviderRuntimeConfigurationError(
                "provider runtime configs must contain ProviderRuntimeConfig values"
            )
        key = (config.provider, config.api_family.value)
        if key in providers:
            raise ProviderRuntimeConfigurationError(
                f"duplicate provider runtime binding for {key[0]}/{key[1]}"
            )
        credential = secrets.resolve(config.credential_env_var)
        providers[key] = _build_adapter(config, credential)
    return StaticProviderResolver(providers)


def _build_adapter(config: ProviderRuntimeConfig, credential: str) -> ProviderPort:
    if config.api_family is ProviderApiFamily.OPENAI_RESPONSES:
        return OpenAIResponsesStreamingAdapter(
            api_key=credential,
            endpoint=config.endpoint,
        )
    if config.api_family is ProviderApiFamily.ANTHROPIC_MESSAGES:
        return AnthropicMessagesStreamingAdapter(
            api_key=credential,
            endpoint=config.endpoint,
            api_version=config.anthropic_api_version or _DEFAULT_ANTHROPIC_API_VERSION,
        )
    if config.api_family is ProviderApiFamily.GEMINI_GENERATE_CONTENT:
        return GeminiStreamingAdapter(
            api_key=credential,
            base_url=config.endpoint,
        )

    options = config.openai_compatible
    if options is None:
        raise ProviderRuntimeConfigurationError(
            "openai-compatible provider runtime options are missing"
        )
    if options.supports_streaming:
        return OpenAICompatibleStreamingAdapter(
            provider=config.provider,
            api_key=credential,
            endpoint=config.endpoint,
            max_tokens_field=options.max_tokens_field,
            supports_native_structured_output=options.supports_native_structured_output,
            supports_native_tool_calling=options.supports_native_tool_calling,
            supports_streaming=True,
            supports_stream_usage=True,
        )
    return OpenAICompatibleAdapter(
        provider=config.provider,
        api_key=credential,
        endpoint=config.endpoint,
        max_tokens_field=options.max_tokens_field,
        supports_native_structured_output=options.supports_native_structured_output,
        supports_native_tool_calling=options.supports_native_tool_calling,
    )


def _validate_endpoint(value: object) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ProviderRuntimeConfigurationError(
            "provider endpoint must be a normalized absolute HTTPS URL"
        )
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise ProviderRuntimeConfigurationError("provider endpoint is invalid") from exc
    if parsed.scheme != "https" or not parsed.hostname:
        raise ProviderRuntimeConfigurationError(
            "provider endpoint must be a normalized absolute HTTPS URL"
        )
    if parsed.username is not None or parsed.password is not None:
        raise ProviderRuntimeConfigurationError("provider endpoint must not contain userinfo")
    if parsed.query or parsed.fragment:
        raise ProviderRuntimeConfigurationError(
            "provider endpoint must not contain query or fragment"
        )


def _require_normalized_value(value: object, label: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ProviderRuntimeConfigurationError(f"{label} must be a normalized non-empty string")
