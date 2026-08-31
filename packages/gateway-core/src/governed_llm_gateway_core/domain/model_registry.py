"""Validated model-registry domain objects and deterministic provenance digest."""

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from governed_llm_gateway_contracts import Capability, DataClassification, Modality

_IDENTIFIER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_ROOT_FIELDS = frozenset({"schema_version", "catalog_version", "source_date", "deployments"})
_DEPLOYMENT_FIELDS = frozenset(
    {
        "provider",
        "model_id",
        "model_group",
        "api_family",
        "capabilities",
        "context_tokens",
        "modalities",
        "pricing",
        "max_data_classification",
        "allowed_environments",
        "enabled",
        "source_date",
        "catalog_version",
    }
)
_CAPABILITY_FIELDS = frozenset(capability.value for capability in Capability)
_PRICING_FIELDS = frozenset(
    {
        "input_usd_per_million_tokens",
        "output_usd_per_million_tokens",
        "source_date",
        "snapshot_version",
    }
)


class ModelRegistryError(ValueError):
    """Base error for invalid model-registry configuration."""


class DuplicateRegistryKeyError(ModelRegistryError):
    """Raised when a registry document repeats a mapping key."""


@dataclass(frozen=True, slots=True)
class PricingMetadata:
    """Versioned USD token-pricing evidence for one deployment."""

    input_usd_per_million_tokens: Decimal
    output_usd_per_million_tokens: Decimal
    source_date: date
    snapshot_version: str


@dataclass(frozen=True, slots=True)
class ModelDeployment:
    """One concrete provider/model deployment declared by registry data."""

    deployment_id: str
    provider: str
    model_id: str
    model_group: str
    api_family: str
    capabilities: frozenset[Capability]
    context_tokens: int
    modalities: frozenset[Modality]
    pricing: PricingMetadata | None
    max_data_classification: DataClassification
    allowed_environments: frozenset[str]
    enabled: bool
    source_date: date
    catalog_version: str


@dataclass(frozen=True, slots=True)
class ModelRegistry:
    """Validated, versioned model registry used as routing provenance."""

    schema_version: str
    catalog_version: str
    source_date: date
    deployments: tuple[ModelDeployment, ...]

    @property
    def digest(self) -> str:
        """Return the deterministic SHA-256 digest of canonical validated content."""
        canonical = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def canonical_payload(self) -> dict[str, object]:
        """Return a JSON-serializable canonical representation of the validated registry."""
        deployments = {
            deployment.deployment_id: _canonical_deployment(deployment)
            for deployment in sorted(self.deployments, key=lambda item: item.deployment_id)
        }
        return {
            "schema_version": self.schema_version,
            "catalog_version": self.catalog_version,
            "source_date": self.source_date.isoformat(),
            "deployments": deployments,
        }

    def by_id(self, deployment_id: str) -> ModelDeployment:
        """Return one deployment by identifier or raise ``KeyError`` when absent."""
        for deployment in self.deployments:
            if deployment.deployment_id == deployment_id:
                return deployment
        raise KeyError(deployment_id)


def build_model_registry(payload: Mapping[object, object]) -> ModelRegistry:
    """Validate parsed registry data and construct the immutable domain registry."""
    _require_fields(payload, _ROOT_FIELDS, _ROOT_FIELDS, "registry")
    schema_version = _require_string(payload["schema_version"], "schema_version")
    if schema_version != "1.0":
        raise ModelRegistryError("registry schema_version must be '1.0'")
    catalog_version = _require_identifier(payload["catalog_version"], "catalog_version")
    source_date = _require_date(payload["source_date"], "source_date")
    deployments_payload = _require_mapping(payload["deployments"], "deployments")

    deployments: list[ModelDeployment] = []
    seen: set[str] = set()
    for raw_deployment_id, raw_spec in deployments_payload.items():
        deployment_id = _require_identifier(raw_deployment_id, "deployment_id")
        if deployment_id in seen:
            raise ModelRegistryError(f"duplicate deployment_id: {deployment_id}")
        seen.add(deployment_id)
        deployments.append(
            _parse_deployment(
                deployment_id,
                _require_mapping(raw_spec, f"deployment {deployment_id}"),
                catalog_version=catalog_version,
                registry_source_date=source_date,
            )
        )

    return ModelRegistry(
        schema_version=schema_version,
        catalog_version=catalog_version,
        source_date=source_date,
        deployments=tuple(sorted(deployments, key=lambda item: item.deployment_id)),
    )


def _parse_deployment(
    deployment_id: str,
    payload: Mapping[object, object],
    *,
    catalog_version: str,
    registry_source_date: date,
) -> ModelDeployment:
    _require_fields(payload, _DEPLOYMENT_FIELDS, _DEPLOYMENT_FIELDS, f"deployment {deployment_id}")
    provider = _require_identifier(payload["provider"], f"{deployment_id}.provider")
    model_id = _require_normalized_string(payload["model_id"], f"{deployment_id}.model_id", 256)
    model_group = _require_identifier(payload["model_group"], f"{deployment_id}.model_group")
    api_family = _require_identifier(payload["api_family"], f"{deployment_id}.api_family")
    capabilities = _parse_capabilities(payload["capabilities"], deployment_id)
    context_tokens = _require_positive_int(
        payload["context_tokens"], f"{deployment_id}.context_tokens"
    )
    modalities = _parse_modalities(payload["modalities"], deployment_id)
    pricing = _parse_pricing(payload["pricing"], deployment_id)
    classification = _require_enum(
        payload["max_data_classification"],
        DataClassification,
        f"{deployment_id}.max_data_classification",
    )
    environments = _parse_identifiers(
        payload["allowed_environments"], f"{deployment_id}.allowed_environments"
    )
    enabled = _require_bool(payload["enabled"], f"{deployment_id}.enabled")
    source_date = _require_date(payload["source_date"], f"{deployment_id}.source_date")
    deployment_catalog = _require_identifier(
        payload["catalog_version"], f"{deployment_id}.catalog_version"
    )

    if source_date != registry_source_date:
        raise ModelRegistryError(f"{deployment_id}.source_date must match registry source_date")
    if deployment_catalog != catalog_version:
        raise ModelRegistryError(
            f"{deployment_id}.catalog_version must match registry catalog_version"
        )
    _validate_capability_combination(deployment_id, capabilities, modalities)

    return ModelDeployment(
        deployment_id=deployment_id,
        provider=provider,
        model_id=model_id,
        model_group=model_group,
        api_family=api_family,
        capabilities=capabilities,
        context_tokens=context_tokens,
        modalities=modalities,
        pricing=pricing,
        max_data_classification=classification,
        allowed_environments=environments,
        enabled=enabled,
        source_date=source_date,
        catalog_version=deployment_catalog,
    )


def _parse_capabilities(value: object, deployment_id: str) -> frozenset[Capability]:
    payload = _require_mapping(value, f"{deployment_id}.capabilities")
    _require_fields(
        payload,
        _CAPABILITY_FIELDS,
        _CAPABILITY_FIELDS,
        f"{deployment_id}.capabilities",
    )
    enabled: set[Capability] = set()
    for capability in Capability:
        if _require_bool(
            payload[capability.value], f"{deployment_id}.capabilities.{capability.value}"
        ):
            enabled.add(capability)
    return frozenset(enabled)


def _parse_modalities(value: object, deployment_id: str) -> frozenset[Modality]:
    items = _require_sequence(value, f"{deployment_id}.modalities")
    modalities: set[Modality] = set()
    for item in items:
        modality = _require_enum(item, Modality, f"{deployment_id}.modalities")
        if modality in modalities:
            raise ModelRegistryError(f"duplicate modality for {deployment_id}: {modality.value}")
        modalities.add(modality)
    if not modalities:
        raise ModelRegistryError(f"{deployment_id}.modalities must not be empty")
    return frozenset(modalities)


def _parse_pricing(value: object, deployment_id: str) -> PricingMetadata | None:
    if value is None:
        return None
    payload = _require_mapping(value, f"{deployment_id}.pricing")
    _require_fields(payload, _PRICING_FIELDS, _PRICING_FIELDS, f"{deployment_id}.pricing")
    return PricingMetadata(
        input_usd_per_million_tokens=_require_non_negative_decimal(
            payload["input_usd_per_million_tokens"],
            f"{deployment_id}.pricing.input_usd_per_million_tokens",
        ),
        output_usd_per_million_tokens=_require_non_negative_decimal(
            payload["output_usd_per_million_tokens"],
            f"{deployment_id}.pricing.output_usd_per_million_tokens",
        ),
        source_date=_require_date(payload["source_date"], f"{deployment_id}.pricing.source_date"),
        snapshot_version=_require_identifier(
            payload["snapshot_version"], f"{deployment_id}.pricing.snapshot_version"
        ),
    )


def _parse_identifiers(value: object, field: str) -> frozenset[str]:
    items = _require_sequence(value, field)
    values: set[str] = set()
    for item in items:
        identifier = _require_identifier(item, field)
        if identifier in values:
            raise ModelRegistryError(f"duplicate identifier in {field}: {identifier}")
        values.add(identifier)
    if not values:
        raise ModelRegistryError(f"{field} must not be empty")
    return frozenset(values)


def _validate_capability_combination(
    deployment_id: str,
    capabilities: frozenset[Capability],
    modalities: frozenset[Modality],
) -> None:
    if Capability.TEXT not in capabilities:
        raise ModelRegistryError(f"{deployment_id} must declare text capability")
    if Modality.TEXT not in modalities:
        raise ModelRegistryError(f"{deployment_id} must support text modality")
    has_vision = Capability.VISION in capabilities
    has_image = Modality.IMAGE in modalities
    if has_vision != has_image:
        raise ModelRegistryError(
            f"{deployment_id} vision capability and image modality must be declared together"
        )


def _canonical_deployment(deployment: ModelDeployment) -> dict[str, object]:
    pricing: dict[str, object] | None = None
    if deployment.pricing is not None:
        pricing = {
            "input_usd_per_million_tokens": _canonical_decimal(
                deployment.pricing.input_usd_per_million_tokens
            ),
            "output_usd_per_million_tokens": _canonical_decimal(
                deployment.pricing.output_usd_per_million_tokens
            ),
            "source_date": deployment.pricing.source_date.isoformat(),
            "snapshot_version": deployment.pricing.snapshot_version,
        }
    return {
        "provider": deployment.provider,
        "model_id": deployment.model_id,
        "model_group": deployment.model_group,
        "api_family": deployment.api_family,
        "capabilities": {
            capability.value: capability in deployment.capabilities for capability in Capability
        },
        "context_tokens": deployment.context_tokens,
        "modalities": sorted(modality.value for modality in deployment.modalities),
        "pricing": pricing,
        "max_data_classification": deployment.max_data_classification.value,
        "allowed_environments": sorted(deployment.allowed_environments),
        "enabled": deployment.enabled,
        "source_date": deployment.source_date.isoformat(),
        "catalog_version": deployment.catalog_version,
    }


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def _require_fields(
    payload: Mapping[object, object],
    allowed: frozenset[str],
    required: frozenset[str],
    location: str,
) -> None:
    keys: set[str] = set()
    for key in payload:
        if not isinstance(key, str):
            raise ModelRegistryError(f"{location} field names must be strings")
        keys.add(key)
    unknown = sorted(keys - allowed)
    if unknown:
        raise ModelRegistryError(f"unknown {location} fields: {', '.join(unknown)}")
    missing = sorted(required - keys)
    if missing:
        raise ModelRegistryError(f"missing {location} fields: {', '.join(missing)}")


def _require_mapping(value: object, field: str) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise ModelRegistryError(f"{field} must be a mapping")
    return value


def _require_sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise ModelRegistryError(f"{field} must be a sequence")
    return value


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ModelRegistryError(f"{field} must be a string")
    return value


def _require_normalized_string(value: object, field: str, max_length: int) -> str:
    text = _require_string(value, field)
    if not text or text.strip() != text or len(text) > max_length:
        raise ModelRegistryError(f"{field} must be a non-empty normalized string <= {max_length}")
    return text


def _require_identifier(value: object, field: str) -> str:
    text = _require_normalized_string(value, field, 128)
    if not _IDENTIFIER_RE.fullmatch(text):
        raise ModelRegistryError(
            f"{field} must use lowercase letters, digits, '.', '_' or '-' "
            "and start/end alphanumeric"
        )
    return text


def _require_date(value: object, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = _require_string(value, field)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ModelRegistryError(f"{field} must be an ISO date") from exc


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ModelRegistryError(f"{field} must be a boolean")
    return value


def _require_positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ModelRegistryError(f"{field} must be a positive integer")
    return value


def _require_non_negative_decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str | int | float | Decimal):
        raise ModelRegistryError(f"{field} must be a decimal-compatible value")
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation as exc:
        raise ModelRegistryError(f"{field} must be a valid decimal") from exc
    if not decimal_value.is_finite() or decimal_value < 0:
        raise ModelRegistryError(f"{field} must be a finite non-negative decimal")
    return decimal_value


def _require_enum[EnumT: StrEnum](value: object, enum_type: type[EnumT], field: str) -> EnumT:
    if not isinstance(value, str):
        raise ModelRegistryError(f"{field} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ModelRegistryError(f"{field} must be one of: {allowed}") from exc
