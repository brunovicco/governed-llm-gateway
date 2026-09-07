"""Closed JSON artifact for deployment-owned Policy Router runtime configuration."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .policy_router_runtime import (
    PolicyRouterCredentialBinding,
    PolicyRouterRuntimeConfig,
    PolicyRouterRuntimeConfigurationError,
)

_SCHEMA_VERSION = "1.0"
_IDENTIFIER = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "config_version",
        "enabled",
        "endpoint",
        "timeout_seconds",
        "bindings",
    }
)
_BINDING_FIELDS = frozenset({"client_id", "credential_reference"})


class PolicyRouterRuntimeDocumentError(PolicyRouterRuntimeConfigurationError):
    """Raised when a Policy Router runtime configuration artifact is invalid."""


class DuplicatePolicyRouterRuntimeKeyError(PolicyRouterRuntimeDocumentError):
    """Raised when Policy Router runtime JSON repeats a key."""


@dataclass(frozen=True, slots=True)
class PolicyRouterRuntimeDocument:
    """Validated secret-free Policy Router runtime configuration snapshot."""

    schema_version: str
    config_version: str
    runtime: PolicyRouterRuntimeConfig

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
        """Return validated content with deterministic client ordering."""
        return {
            "schema_version": self.schema_version,
            "config_version": self.config_version,
            "enabled": self.runtime.enabled,
            "endpoint": self.runtime.endpoint,
            "timeout_seconds": self.runtime.timeout_seconds,
            "bindings": [
                {
                    "client_id": binding.client_id,
                    "credential_reference": binding.credential_reference,
                }
                for binding in self.runtime.bindings
            ],
        }


def load_policy_router_runtime_document(path: str | Path) -> PolicyRouterRuntimeDocument:
    """Load and validate one UTF-8 Policy Router runtime JSON artifact."""
    return load_policy_router_runtime_document_text(Path(path).read_text(encoding="utf-8"))


def load_policy_router_runtime_document_text(text: str) -> PolicyRouterRuntimeDocument:
    """Parse Policy Router JSON with duplicate-key and closed-schema validation."""
    try:
        payload: object = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except DuplicatePolicyRouterRuntimeKeyError:
        raise
    except json.JSONDecodeError as exc:
        raise PolicyRouterRuntimeDocumentError(
            "Policy Router runtime configuration is not valid JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise PolicyRouterRuntimeDocumentError(
            "Policy Router runtime configuration root must be an object"
        )
    return _build_document(cast(Mapping[object, object], payload))


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicatePolicyRouterRuntimeKeyError(
                f"duplicate Policy Router runtime configuration key: {key!r}"
            )
        result[key] = value
    return result


def _build_document(payload: Mapping[object, object]) -> PolicyRouterRuntimeDocument:
    _require_exact_fields(payload, _ROOT_FIELDS, "document")
    schema_version = _require_string(payload["schema_version"], "schema_version")
    if schema_version != _SCHEMA_VERSION:
        raise PolicyRouterRuntimeDocumentError(
            f"Policy Router runtime schema_version must be {_SCHEMA_VERSION!r}"
        )
    config_version = _require_identifier(payload["config_version"], "config_version")
    enabled = _require_bool(payload["enabled"], "enabled")
    endpoint = _require_optional_string(payload["endpoint"], "endpoint")
    timeout_seconds = _require_number(payload["timeout_seconds"], "timeout_seconds")
    bindings = _parse_bindings(payload["bindings"])

    try:
        runtime = PolicyRouterRuntimeConfig(
            enabled=enabled,
            endpoint=endpoint,
            timeout_seconds=timeout_seconds,
            bindings=tuple(sorted(bindings, key=lambda item: item.client_id)),
        )
    except PolicyRouterRuntimeConfigurationError as exc:
        raise PolicyRouterRuntimeDocumentError(str(exc)) from exc

    return PolicyRouterRuntimeDocument(
        schema_version=schema_version,
        config_version=config_version,
        runtime=runtime,
    )


def _parse_bindings(value: object) -> tuple[PolicyRouterCredentialBinding, ...]:
    if not isinstance(value, list):
        raise PolicyRouterRuntimeDocumentError("bindings must be an array")
    bindings: list[PolicyRouterCredentialBinding] = []
    for index, raw_binding in enumerate(value):
        if not isinstance(raw_binding, Mapping):
            raise PolicyRouterRuntimeDocumentError(f"bindings[{index}] must be an object")
        payload = cast(Mapping[object, object], raw_binding)
        label = f"bindings[{index}]"
        _require_exact_fields(payload, _BINDING_FIELDS, label)
        try:
            bindings.append(
                PolicyRouterCredentialBinding(
                    client_id=_require_string(payload["client_id"], f"{label}.client_id"),
                    credential_reference=_require_string(
                        payload["credential_reference"],
                        f"{label}.credential_reference",
                    ),
                )
            )
        except PolicyRouterRuntimeConfigurationError as exc:
            raise PolicyRouterRuntimeDocumentError(str(exc)) from exc
    return tuple(bindings)


def _require_exact_fields(
    payload: Mapping[object, object],
    expected: frozenset[str],
    label: str,
) -> None:
    keys: set[str] = set()
    for key in payload:
        if not isinstance(key, str):
            raise PolicyRouterRuntimeDocumentError(f"{label} keys must be strings")
        keys.add(key)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing:
        raise PolicyRouterRuntimeDocumentError(
            f"{label} is missing required fields: {', '.join(missing)}"
        )
    if unknown:
        raise PolicyRouterRuntimeDocumentError(
            f"{label} contains unknown fields: {', '.join(unknown)}"
        )


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise PolicyRouterRuntimeDocumentError(
            f"{label} must be a normalized non-empty string"
        )
    return value


def _require_optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, label)


def _require_identifier(value: object, label: str) -> str:
    text = _require_string(value, label)
    if _IDENTIFIER.fullmatch(text) is None:
        raise PolicyRouterRuntimeDocumentError(f"{label} must be a normalized identifier")
    return text


def _require_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise PolicyRouterRuntimeDocumentError(f"{label} must be boolean")
    return value


def _require_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise PolicyRouterRuntimeDocumentError(f"{label} must be numeric")
    return float(value)
