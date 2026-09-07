"""Closed JSON artifact for deployment-owned Gateway client authentication."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from governed_llm_gateway_contracts import DataClassification, RiskLevel

from .client_auth import (
    GatewayClientAuthBinding,
    GatewayClientAuthenticationConfigurationError,
)

_SCHEMA_VERSION = "1.0"
_IDENTIFIER = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_ROOT_FIELDS = frozenset({"schema_version", "config_version", "bindings"})
_BINDING_FIELDS = frozenset(
    {
        "client_id",
        "environment",
        "credential_reference",
        "allowed_workloads",
        "minimum_risk_level",
        "minimum_data_classification",
    }
)


class GatewayClientAuthDocumentError(GatewayClientAuthenticationConfigurationError):
    """Raised when a Gateway client-auth configuration artifact is invalid."""


class DuplicateGatewayClientAuthKeyError(GatewayClientAuthDocumentError):
    """Raised when JSON repeats a key that would otherwise be overwritten."""


@dataclass(frozen=True, slots=True)
class GatewayClientAuthDocument:
    """Validated secret-free Gateway client-auth configuration snapshot."""

    schema_version: str
    config_version: str
    bindings: tuple[GatewayClientAuthBinding, ...]

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
            "bindings": [
                _canonical_binding(binding)
                for binding in sorted(self.bindings, key=lambda item: item.client_id)
            ],
        }


def load_gateway_client_auth_document(path: str | Path) -> GatewayClientAuthDocument:
    """Load and validate one UTF-8 Gateway client-auth JSON artifact."""
    return load_gateway_client_auth_document_text(Path(path).read_text(encoding="utf-8"))


def load_gateway_client_auth_document_text(text: str) -> GatewayClientAuthDocument:
    """Parse Gateway client-auth JSON with duplicate-key and closed-schema validation."""
    try:
        payload: object = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except DuplicateGatewayClientAuthKeyError:
        raise
    except json.JSONDecodeError as exc:
        raise GatewayClientAuthDocumentError(
            "gateway client-auth configuration is not valid JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise GatewayClientAuthDocumentError(
            "gateway client-auth configuration root must be an object"
        )
    return _build_document(cast(Mapping[object, object], payload))


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateGatewayClientAuthKeyError(
                f"duplicate gateway client-auth configuration key: {key!r}"
            )
        result[key] = value
    return result


def _build_document(payload: Mapping[object, object]) -> GatewayClientAuthDocument:
    _require_exact_fields(payload, _ROOT_FIELDS, "document")
    schema_version = _require_string(payload["schema_version"], "schema_version")
    if schema_version != _SCHEMA_VERSION:
        raise GatewayClientAuthDocumentError(
            f"gateway client-auth schema_version must be {_SCHEMA_VERSION!r}"
        )
    config_version = _require_identifier(payload["config_version"], "config_version")
    raw_bindings = payload["bindings"]
    if not isinstance(raw_bindings, list):
        raise GatewayClientAuthDocumentError("bindings must be an array")

    bindings: list[GatewayClientAuthBinding] = []
    client_ids: set[str] = set()
    credential_references: set[str] = set()
    for index, raw_binding in enumerate(raw_bindings):
        if not isinstance(raw_binding, Mapping):
            raise GatewayClientAuthDocumentError(f"bindings[{index}] must be an object")
        binding = _parse_binding(cast(Mapping[object, object], raw_binding), index=index)
        if binding.client_id in client_ids:
            raise GatewayClientAuthDocumentError(
                f"duplicate gateway client-auth client_id: {binding.client_id!r}"
            )
        if binding.credential_reference in credential_references:
            raise GatewayClientAuthDocumentError(
                "gateway client-auth credential references must be unique"
            )
        client_ids.add(binding.client_id)
        credential_references.add(binding.credential_reference)
        bindings.append(binding)

    return GatewayClientAuthDocument(
        schema_version=schema_version,
        config_version=config_version,
        bindings=tuple(sorted(bindings, key=lambda item: item.client_id)),
    )


def _parse_binding(
    payload: Mapping[object, object],
    *,
    index: int,
) -> GatewayClientAuthBinding:
    label = f"bindings[{index}]"
    _require_exact_fields(payload, _BINDING_FIELDS, label)
    risk_text = _require_string(payload["minimum_risk_level"], f"{label}.minimum_risk_level")
    classification_text = _require_string(
        payload["minimum_data_classification"],
        f"{label}.minimum_data_classification",
    )
    try:
        minimum_risk = RiskLevel(risk_text)
    except ValueError as exc:
        raise GatewayClientAuthDocumentError(f"{label}.minimum_risk_level is unsupported") from exc
    try:
        minimum_classification = DataClassification(classification_text)
    except ValueError as exc:
        raise GatewayClientAuthDocumentError(
            f"{label}.minimum_data_classification is unsupported"
        ) from exc

    workloads = _require_workloads(payload["allowed_workloads"], f"{label}.allowed_workloads")
    try:
        return GatewayClientAuthBinding(
            client_id=_require_string(payload["client_id"], f"{label}.client_id"),
            environment=_require_string(payload["environment"], f"{label}.environment"),
            credential_reference=_require_string(
                payload["credential_reference"],
                f"{label}.credential_reference",
            ),
            allowed_workloads=workloads,
            minimum_risk_level=minimum_risk,
            minimum_data_classification=minimum_classification,
        )
    except GatewayClientAuthenticationConfigurationError as exc:
        raise GatewayClientAuthDocumentError(str(exc)) from exc


def _canonical_binding(binding: GatewayClientAuthBinding) -> dict[str, object]:
    return {
        "client_id": binding.client_id,
        "environment": binding.environment,
        "credential_reference": binding.credential_reference,
        "allowed_workloads": list(binding.allowed_workloads),
        "minimum_risk_level": binding.minimum_risk_level.value,
        "minimum_data_classification": binding.minimum_data_classification.value,
    }


def _require_exact_fields(
    payload: Mapping[object, object],
    expected: frozenset[str],
    label: str,
) -> None:
    keys: set[str] = set()
    for key in payload:
        if not isinstance(key, str):
            raise GatewayClientAuthDocumentError(f"{label} keys must be strings")
        keys.add(key)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing:
        raise GatewayClientAuthDocumentError(
            f"{label} is missing required fields: {', '.join(missing)}"
        )
    if unknown:
        raise GatewayClientAuthDocumentError(
            f"{label} contains unknown fields: {', '.join(unknown)}"
        )


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise GatewayClientAuthDocumentError(f"{label} must be a normalized non-empty string")
    return value


def _require_identifier(value: object, label: str) -> str:
    text = _require_string(value, label)
    if _IDENTIFIER.fullmatch(text) is None:
        raise GatewayClientAuthDocumentError(f"{label} must be a normalized identifier")
    return text


def _require_workloads(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise GatewayClientAuthDocumentError(f"{label} must be a non-empty array")
    workloads: list[str] = []
    for index, workload in enumerate(value):
        workloads.append(_require_string(workload, f"{label}[{index}]"))
    return tuple(workloads)
