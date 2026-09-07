"""Closed JSON artifact for non-authoritative complexity-routing configuration."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from governed_llm_gateway_contracts import TaskComplexity

from governed_llm_gateway_core.domain.complexity import (
    ComplexityPolicy,
    WorkloadComplexityFloor,
)
from governed_llm_gateway_core.domain.complexity_quality import ComplexityQualityPolicy

_SCHEMA_VERSION = "1.0"
_IDENTIFIER = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_ROOT_FIELDS = frozenset(
    {"schema_version", "config_version", "assessment_policy", "quality_policy"}
)
_ASSESSMENT_FIELDS = frozenset(
    {
        "policy_id",
        "version",
        "medium_context_tokens",
        "high_context_tokens",
        "medium_output_tokens",
        "high_output_tokens",
        "tool_calling_floor",
        "structured_output_floor",
        "vision_floor",
        "workload_floors",
    }
)
_WORKLOAD_FLOOR_FIELDS = frozenset({"workload", "minimum"})
_QUALITY_FIELDS = frozenset(
    {
        "policy_id",
        "version",
        "low_min_quality",
        "medium_min_quality",
        "high_min_quality",
    }
)


class ComplexityRoutingDocumentError(ValueError):
    """Raised when a complexity-routing operational artifact is invalid."""


class DuplicateComplexityRoutingKeyError(ComplexityRoutingDocumentError):
    """Raised when JSON repeats a mapping key that would otherwise be overwritten."""


@dataclass(frozen=True, slots=True)
class ComplexityRoutingDocument:
    """Validated secret-free complexity-routing configuration snapshot."""

    schema_version: str
    config_version: str
    assessment_policy: ComplexityPolicy
    quality_policy: ComplexityQualityPolicy

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
        """Return validated content with deterministic workload-floor ordering."""
        assessment = self.assessment_policy
        quality = self.quality_policy
        return {
            "schema_version": self.schema_version,
            "config_version": self.config_version,
            "assessment_policy": {
                "policy_id": assessment.policy_id,
                "version": assessment.version,
                "medium_context_tokens": assessment.medium_context_tokens,
                "high_context_tokens": assessment.high_context_tokens,
                "medium_output_tokens": assessment.medium_output_tokens,
                "high_output_tokens": assessment.high_output_tokens,
                "tool_calling_floor": assessment.tool_calling_floor.value,
                "structured_output_floor": assessment.structured_output_floor.value,
                "vision_floor": assessment.vision_floor.value,
                "workload_floors": [
                    {"workload": rule.workload, "minimum": rule.minimum.value}
                    for rule in assessment.workload_floors
                ],
            },
            "quality_policy": {
                "policy_id": quality.policy_id,
                "version": quality.version,
                "low_min_quality": _canonical_decimal(quality.low_min_quality),
                "medium_min_quality": _canonical_decimal(quality.medium_min_quality),
                "high_min_quality": _canonical_decimal(quality.high_min_quality),
            },
        }


def load_complexity_routing_document(path: str | Path) -> ComplexityRoutingDocument:
    """Load and validate one UTF-8 complexity-routing configuration JSON file."""
    return load_complexity_routing_document_text(Path(path).read_text(encoding="utf-8"))


def load_complexity_routing_document_text(text: str) -> ComplexityRoutingDocument:
    """Parse complexity-routing JSON with duplicate-key and closed-schema validation."""
    try:
        payload: object = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except DuplicateComplexityRoutingKeyError:
        raise
    except json.JSONDecodeError as exc:
        raise ComplexityRoutingDocumentError(
            "complexity routing configuration is not valid JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ComplexityRoutingDocumentError("complexity routing configuration root must be an object")
    return _build_document(cast(Mapping[object, object], payload))


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateComplexityRoutingKeyError(
                f"duplicate complexity routing configuration key: {key!r}"
            )
        result[key] = value
    return result


def _build_document(payload: Mapping[object, object]) -> ComplexityRoutingDocument:
    _require_exact_fields(payload, _ROOT_FIELDS, "document")
    schema_version = _require_string(payload["schema_version"], "schema_version")
    if schema_version != _SCHEMA_VERSION:
        raise ComplexityRoutingDocumentError(
            f"complexity routing schema_version must be {_SCHEMA_VERSION!r}"
        )
    config_version = _require_identifier(payload["config_version"], "config_version")
    assessment_payload = _require_mapping(payload["assessment_policy"], "assessment_policy")
    quality_payload = _require_mapping(payload["quality_policy"], "quality_policy")

    return ComplexityRoutingDocument(
        schema_version=schema_version,
        config_version=config_version,
        assessment_policy=_parse_assessment_policy(assessment_payload),
        quality_policy=_parse_quality_policy(quality_payload),
    )


def _parse_assessment_policy(payload: Mapping[object, object]) -> ComplexityPolicy:
    _require_exact_fields(payload, _ASSESSMENT_FIELDS, "assessment_policy")
    workload_floors = _parse_workload_floors(payload["workload_floors"])
    try:
        return ComplexityPolicy(
            policy_id=_require_identifier(payload["policy_id"], "assessment_policy.policy_id"),
            version=_require_identifier(payload["version"], "assessment_policy.version"),
            medium_context_tokens=_require_int(
                payload["medium_context_tokens"],
                "assessment_policy.medium_context_tokens",
            ),
            high_context_tokens=_require_int(
                payload["high_context_tokens"],
                "assessment_policy.high_context_tokens",
            ),
            medium_output_tokens=_require_int(
                payload["medium_output_tokens"],
                "assessment_policy.medium_output_tokens",
            ),
            high_output_tokens=_require_int(
                payload["high_output_tokens"],
                "assessment_policy.high_output_tokens",
            ),
            tool_calling_floor=_require_complexity(
                payload["tool_calling_floor"],
                "assessment_policy.tool_calling_floor",
            ),
            structured_output_floor=_require_complexity(
                payload["structured_output_floor"],
                "assessment_policy.structured_output_floor",
            ),
            vision_floor=_require_complexity(
                payload["vision_floor"],
                "assessment_policy.vision_floor",
            ),
            workload_floors=workload_floors,
        )
    except ValueError as exc:
        raise ComplexityRoutingDocumentError(str(exc)) from exc


def _parse_workload_floors(value: object) -> tuple[WorkloadComplexityFloor, ...]:
    if not isinstance(value, list):
        raise ComplexityRoutingDocumentError("assessment_policy.workload_floors must be an array")
    floors: list[WorkloadComplexityFloor] = []
    for index, raw_floor in enumerate(value):
        label = f"assessment_policy.workload_floors[{index}]"
        payload = _require_mapping(raw_floor, label)
        _require_exact_fields(payload, _WORKLOAD_FLOOR_FIELDS, label)
        try:
            floors.append(
                WorkloadComplexityFloor(
                    workload=_require_string(payload["workload"], f"{label}.workload"),
                    minimum=_require_complexity(payload["minimum"], f"{label}.minimum"),
                )
            )
        except ValueError as exc:
            raise ComplexityRoutingDocumentError(str(exc)) from exc
    return tuple(floors)


def _parse_quality_policy(payload: Mapping[object, object]) -> ComplexityQualityPolicy:
    _require_exact_fields(payload, _QUALITY_FIELDS, "quality_policy")
    try:
        return ComplexityQualityPolicy(
            policy_id=_require_identifier(payload["policy_id"], "quality_policy.policy_id"),
            version=_require_identifier(payload["version"], "quality_policy.version"),
            low_min_quality=_require_decimal(
                payload["low_min_quality"], "quality_policy.low_min_quality"
            ),
            medium_min_quality=_require_decimal(
                payload["medium_min_quality"], "quality_policy.medium_min_quality"
            ),
            high_min_quality=_require_decimal(
                payload["high_min_quality"], "quality_policy.high_min_quality"
            ),
        )
    except ValueError as exc:
        raise ComplexityRoutingDocumentError(str(exc)) from exc


def _require_mapping(value: object, label: str) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise ComplexityRoutingDocumentError(f"{label} must be an object")
    return cast(Mapping[object, object], value)


def _require_exact_fields(
    payload: Mapping[object, object],
    expected: frozenset[str],
    label: str,
) -> None:
    actual = frozenset(payload)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected, key=str)
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("extra=" + ",".join(repr(item) for item in extra))
        raise ComplexityRoutingDocumentError(
            f"complexity routing {label} fields are invalid: " + "; ".join(details)
        )


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ComplexityRoutingDocumentError(f"{label} must be a non-empty normalized string")
    return value


def _require_identifier(value: object, label: str) -> str:
    text = _require_string(value, label)
    if _IDENTIFIER.fullmatch(text) is None:
        raise ComplexityRoutingDocumentError(f"{label} must be a normalized identifier")
    return text


def _require_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ComplexityRoutingDocumentError(f"{label} must be an integer")
    return value


def _require_complexity(value: object, label: str) -> TaskComplexity:
    text = _require_string(value, label)
    try:
        return TaskComplexity(text)
    except ValueError as exc:
        raise ComplexityRoutingDocumentError(
            f"{label} must use the provider-neutral complexity vocabulary"
        ) from exc


def _require_decimal(value: object, label: str) -> Decimal:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ComplexityRoutingDocumentError(f"{label} must be a normalized decimal string")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ComplexityRoutingDocumentError(f"{label} must be a valid decimal string") from exc


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")
