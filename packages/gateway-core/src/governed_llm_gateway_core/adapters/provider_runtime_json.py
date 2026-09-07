"""Closed JSON artifact for deployment-owned provider runtime configuration."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from governed_llm_gateway_core.domain.model_registry import ModelRegistry

from .provider_runtime import (
    OpenAICompatibleRuntimeOptions,
    ProviderApiFamily,
    ProviderRuntimeConfig,
    ProviderRuntimeConfigurationError,
)

_SCHEMA_VERSION = "1.0"
_IDENTIFIER = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_ROOT_FIELDS = frozenset({"schema_version", "config_version", "bindings"})
_BINDING_REQUIRED_FIELDS = frozenset(
    {"provider", "api_family", "credential_reference", "endpoint"}
)
_BINDING_OPTIONAL_FIELDS = frozenset({"anthropic_api_version", "openai_compatible"})
_COMPATIBLE_FIELDS = frozenset(
    {
        "max_tokens_field",
        "supports_native_structured_output",
        "supports_native_tool_calling",
        "supports_streaming",
        "supports_stream_usage",
    }
)


class ProviderRuntimeDocumentError(ProviderRuntimeConfigurationError):
    """Raised when a provider runtime configuration artifact is invalid."""


class DuplicateProviderRuntimeKeyError(ProviderRuntimeDocumentError):
    """Raised when JSON repeats a mapping key that would otherwise be overwritten."""


class ProviderRuntimeRegistryMismatchError(ProviderRuntimeDocumentError):
    """Raised when runtime bindings and enabled registry API-family requirements diverge."""


@dataclass(frozen=True, slots=True)
class ProviderRuntimeDocument:
    """Validated secret-free provider runtime configuration snapshot."""

    schema_version: str
    config_version: str
    bindings: tuple[ProviderRuntimeConfig, ...]

    @property
    def digest(self) -> str:
        """Return deterministic SHA-256 provenance over canonical validated content."""
        canonical = json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def canonical_payload(self) -> dict[str, object]:
        """Return validated content with deterministic binding ordering."""
        bindings = [
            _canonical_binding(binding)
            for binding in sorted(
                self.bindings,
                key=lambda item: (item.provider, item.api_family.value),
            )
        ]
        return {
            "schema_version": self.schema_version,
            "config_version": self.config_version,
            "bindings": bindings,
        }


def load_provider_runtime_document(path: str | Path) -> ProviderRuntimeDocument:
    """Load and validate one UTF-8 provider runtime configuration JSON file."""
    return load_provider_runtime_document_text(Path(path).read_text(encoding="utf-8"))


def load_provider_runtime_document_text(text: str) -> ProviderRuntimeDocument:
    """Parse provider runtime JSON with duplicate-key and closed-schema validation."""
    try:
        payload: object = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except DuplicateProviderRuntimeKeyError:
        raise
    except json.JSONDecodeError as exc:
        raise ProviderRuntimeDocumentError(
            "provider runtime configuration is not valid JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ProviderRuntimeDocumentError("provider runtime configuration root must be an object")
    return _build_document(cast(Mapping[object, object], payload))


def validate_provider_runtime_registry(
    document: ProviderRuntimeDocument,
    registry: ModelRegistry,
) -> None:
    """Require an exact operational binding set for enabled registry deployments."""
    configured = {(binding.provider, binding.api_family.value) for binding in document.bindings}
    required = {
        (deployment.provider, deployment.api_family)
        for deployment in registry.deployments
        if deployment.enabled
    }
    missing = sorted(required - configured)
    extra = sorted(configured - required)
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(
                "missing=" + ",".join(f"{provider}/{family}" for provider, family in missing)
            )
        if extra:
            details.append(
                "extra=" + ",".join(f"{provider}/{family}" for provider, family in extra)
            )
        raise ProviderRuntimeRegistryMismatchError(
            "provider runtime bindings do not match enabled registry API families: "
            + "; ".join(details)
        )


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateProviderRuntimeKeyError(
                f"duplicate provider runtime configuration key: {key!r}"
            )
        result[key] = value
    return result


def _build_document(payload: Mapping[object, object]) -> ProviderRuntimeDocument:
    _require_exact_fields(payload, _ROOT_FIELDS, _ROOT_FIELDS, "document")
    schema_version = _require_string(payload["schema_version"], "schema_version")
    if schema_version != _SCHEMA_VERSION:
        raise ProviderRuntimeDocumentError(
            f"provider runtime schema_version must be {_SCHEMA_VERSION!r}"
        )
    config_version = _require_identifier(payload["config_version"], "config_version")
    raw_bindings = payload["bindings"]
    if not isinstance(raw_bindings, list):
        raise ProviderRuntimeDocumentError("bindings must be an array")

    bindings: list[ProviderRuntimeConfig] = []
    seen: set[tuple[str, str]] = set()
    for index, raw_binding in enumerate(raw_bindings):
        if not isinstance(raw_binding, Mapping):
            raise ProviderRuntimeDocumentError(f"bindings[{index}] must be an object")
        binding = _parse_binding(cast(Mapping[object, object], raw_binding), index=index)
        key = (binding.provider, binding.api_family.value)
        if key in seen:
            raise ProviderRuntimeDocumentError(
                f"duplicate provider runtime binding for {key[0]}/{key[1]}"
            )
        seen.add(key)
        bindings.append(binding)

    return ProviderRuntimeDocument(
        schema_version=schema_version,
        config_version=config_version,
        bindings=tuple(sorted(bindings, key=lambda item: (item.provider, item.api_family.value))),
    )


def _parse_binding(payload: Mapping[object, object], *, index: int) -> ProviderRuntimeConfig:
    allowed = _BINDING_REQUIRED_FIELDS | _BINDING_OPTIONAL_FIELDS
    _require_exact_fields(payload, _BINDING_REQUIRED_FIELDS, allowed, f"bindings[{index}]")
    provider = _require_string(payload["provider"], f"bindings[{index}].provider")
    api_family_text = _require_string(payload["api_family"], f"bindings[{index}].api_family")
    try:
        api_family = ProviderApiFamily(api_family_text)
    except ValueError as exc:
        raise ProviderRuntimeDocumentError(
            f"bindings[{index}].api_family is unsupported"
        ) from exc

    anthropic_api_version = _optional_string(
        payload.get("anthropic_api_version"),
        f"bindings[{index}].anthropic_api_version",
    )
    compatible_payload = payload.get("openai_compatible")
    compatible = None
    if compatible_payload is not None:
        if not isinstance(compatible_payload, Mapping):
            raise ProviderRuntimeDocumentError(
                f"bindings[{index}].openai_compatible must be an object"
            )
        compatible = _parse_compatible_options(
            cast(Mapping[object, object], compatible_payload),
            index=index,
        )

    try:
        return ProviderRuntimeConfig(
            provider=provider,
            api_family=api_family,
            credential_reference=_require_string(
                payload["credential_reference"],
                f"bindings[{index}].credential_reference",
            ),
            endpoint=_require_string(payload["endpoint"], f"bindings[{index}].endpoint"),
            anthropic_api_version=anthropic_api_version,
            openai_compatible=compatible,
        )
    except ProviderRuntimeConfigurationError as exc:
        raise ProviderRuntimeDocumentError(str(exc)) from exc


def _parse_compatible_options(
    payload: Mapping[object, object],
    *,
    index: int,
) -> OpenAICompatibleRuntimeOptions:
    label = f"bindings[{index}].openai_compatible"
    _require_exact_fields(payload, _COMPATIBLE_FIELDS, _COMPATIBLE_FIELDS, label)
    try:
        return OpenAICompatibleRuntimeOptions(
            max_tokens_field=_require_string(
                payload["max_tokens_field"], f"{label}.max_tokens_field"
            ),
            supports_native_structured_output=_require_bool(
                payload["supports_native_structured_output"],
                f"{label}.supports_native_structured_output",
            ),
            supports_native_tool_calling=_require_bool(
                payload["supports_native_tool_calling"],
                f"{label}.supports_native_tool_calling",
            ),
            supports_streaming=_require_bool(
                payload["supports_streaming"], f"{label}.supports_streaming"
            ),
            supports_stream_usage=_require_bool(
                payload["supports_stream_usage"], f"{label}.supports_stream_usage"
            ),
        )
    except ProviderRuntimeConfigurationError as exc:
        raise ProviderRuntimeDocumentError(str(exc)) from exc


def _canonical_binding(binding: ProviderRuntimeConfig) -> dict[str, object]:
    result: dict[str, object] = {
        "provider": binding.provider,
        "api_family": binding.api_family.value,
        "credential_reference": binding.credential_reference,
        "endpoint": binding.endpoint,
    }
    if binding.anthropic_api_version is not None:
        result["anthropic_api_version"] = binding.anthropic_api_version
    if binding.openai_compatible is not None:
        options = binding.openai_compatible
        result["openai_compatible"] = {
            "max_tokens_field": options.max_tokens_field,
            "supports_native_structured_output": options.supports_native_structured_output,
            "supports_native_tool_calling": options.supports_native_tool_calling,
            "supports_streaming": options.supports_streaming,
            "supports_stream_usage": options.supports_stream_usage,
        }
    return result


def _require_exact_fields(
    payload: Mapping[object, object],
    required: frozenset[str],
    allowed: frozenset[str],
    label: str,
) -> None:
    keys: set[str] = set()
    for key in payload:
        if not isinstance(key, str):
            raise ProviderRuntimeDocumentError(f"{label} keys must be strings")
        keys.add(key)
    missing = sorted(required - keys)
    unknown = sorted(keys - allowed)
    if missing:
        raise ProviderRuntimeDocumentError(
            f"{label} is missing required fields: {', '.join(missing)}"
        )
    if unknown:
        raise ProviderRuntimeDocumentError(
            f"{label} contains unknown fields: {', '.join(unknown)}"
        )


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ProviderRuntimeDocumentError(f"{label} must be a normalized non-empty string")
    return value


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, label)


def _require_identifier(value: object, label: str) -> str:
    text = _require_string(value, label)
    if _IDENTIFIER.fullmatch(text) is None:
        raise ProviderRuntimeDocumentError(f"{label} must be a normalized identifier")
    return text


def _require_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ProviderRuntimeDocumentError(f"{label} must be boolean")
    return value
