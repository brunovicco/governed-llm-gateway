"""Closed JSON artifact for deployment-owned operations-read visibility grants."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .client_auth import GatewayClientAuthenticationConfigurationError, GatewayClientIdentity
from .client_auth_json import GatewayClientAuthDocument
from .operations_access import OperationsReadAccessConfigurationError, OperationsReadAccessPolicy

_SCHEMA_VERSION = "1.0"
_IDENTIFIER = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_ROOT_FIELDS = frozenset({"schema_version", "config_version", "principals"})
_PRINCIPAL_FIELDS = frozenset({"client_id", "environment"})


class OperationsReadAccessDocumentError(OperationsReadAccessConfigurationError):
    """Raised when an operations-read access configuration artifact is invalid."""


class DuplicateOperationsReadAccessKeyError(OperationsReadAccessDocumentError):
    """Raised when JSON repeats a key that would otherwise be overwritten."""


@dataclass(frozen=True, slots=True)
class OperationsReadAccessDocument:
    """Validated secret-free operations-read access configuration snapshot."""

    schema_version: str
    config_version: str
    policy: OperationsReadAccessPolicy

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
        """Return validated content with deterministic principal ordering."""
        return {
            "schema_version": self.schema_version,
            "config_version": self.config_version,
            "principals": [
                {
                    "client_id": principal.client_id,
                    "environment": principal.environment,
                }
                for principal in self.policy.principals
            ],
        }


def load_operations_read_access_document(path: str | Path) -> OperationsReadAccessDocument:
    """Load and validate one UTF-8 operations-read access JSON artifact."""
    return load_operations_read_access_document_text(Path(path).read_text(encoding="utf-8"))


def load_operations_read_access_document_text(text: str) -> OperationsReadAccessDocument:
    """Parse operations-read access JSON with duplicate-key and closed-schema validation."""
    try:
        payload: object = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except DuplicateOperationsReadAccessKeyError:
        raise
    except json.JSONDecodeError as exc:
        raise OperationsReadAccessDocumentError(
            "operations-read access configuration is not valid JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise OperationsReadAccessDocumentError(
            "operations-read access configuration root must be an object"
        )
    return _build_document(cast(Mapping[object, object], payload))


def validate_operations_access_client_auth(
    document: OperationsReadAccessDocument,
    client_auth_document: GatewayClientAuthDocument,
) -> None:
    """Require every operations principal to reference one configured Gateway identity."""
    if not isinstance(document, OperationsReadAccessDocument):
        raise TypeError("document must use OperationsReadAccessDocument")
    if not isinstance(client_auth_document, GatewayClientAuthDocument):
        raise TypeError("client_auth_document must use GatewayClientAuthDocument")

    configured = {
        GatewayClientIdentity(
            client_id=binding.client_id,
            environment=binding.environment,
        )
        for binding in client_auth_document.bindings
    }
    if any(principal not in configured for principal in document.policy.principals):
        raise OperationsReadAccessDocumentError(
            "operations-read principals must reference configured Gateway client identities"
        )


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateOperationsReadAccessKeyError(
                f"duplicate operations-read access configuration key: {key!r}"
            )
        result[key] = value
    return result


def _build_document(payload: Mapping[object, object]) -> OperationsReadAccessDocument:
    _require_exact_fields(payload, _ROOT_FIELDS, "document")
    schema_version = _require_string(payload["schema_version"], "schema_version")
    if schema_version != _SCHEMA_VERSION:
        raise OperationsReadAccessDocumentError(
            f"operations-read schema_version must be {_SCHEMA_VERSION!r}"
        )
    config_version = _require_identifier(payload["config_version"], "config_version")
    raw_principals = payload["principals"]
    if not isinstance(raw_principals, list):
        raise OperationsReadAccessDocumentError("principals must be an array")

    principals: list[GatewayClientIdentity] = []
    for index, raw_principal in enumerate(raw_principals):
        if not isinstance(raw_principal, Mapping):
            raise OperationsReadAccessDocumentError(f"principals[{index}] must be an object")
        principals.append(
            _parse_principal(cast(Mapping[object, object], raw_principal), index=index)
        )

    try:
        policy = OperationsReadAccessPolicy(principals=tuple(principals))
    except OperationsReadAccessConfigurationError as exc:
        raise OperationsReadAccessDocumentError(str(exc)) from exc
    return OperationsReadAccessDocument(
        schema_version=schema_version,
        config_version=config_version,
        policy=policy,
    )


def _parse_principal(
    payload: Mapping[object, object],
    *,
    index: int,
) -> GatewayClientIdentity:
    label = f"principals[{index}]"
    _require_exact_fields(payload, _PRINCIPAL_FIELDS, label)
    try:
        return GatewayClientIdentity(
            client_id=_require_string(payload["client_id"], f"{label}.client_id"),
            environment=_require_string(payload["environment"], f"{label}.environment"),
        )
    except GatewayClientAuthenticationConfigurationError as exc:
        raise OperationsReadAccessDocumentError(str(exc)) from exc


def _require_exact_fields(
    payload: Mapping[object, object],
    expected: frozenset[str],
    label: str,
) -> None:
    keys: set[str] = set()
    for key in payload:
        if not isinstance(key, str):
            raise OperationsReadAccessDocumentError(f"{label} keys must be strings")
        keys.add(key)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing:
        raise OperationsReadAccessDocumentError(
            f"{label} is missing required fields: {', '.join(missing)}"
        )
    if unknown:
        raise OperationsReadAccessDocumentError(
            f"{label} contains unknown fields: {', '.join(unknown)}"
        )


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise OperationsReadAccessDocumentError(f"{label} must be a normalized non-empty string")
    return value


def _require_identifier(value: object, label: str) -> str:
    text = _require_string(value, label)
    if _IDENTIFIER.fullmatch(text) is None:
        raise OperationsReadAccessDocumentError(f"{label} must be a normalized identifier")
    return text
