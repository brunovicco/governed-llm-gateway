"""Explicit quality floors used to narrow candidates by assessed task complexity."""

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal

from governed_llm_gateway_contracts import TaskComplexity

_IDENTIFIER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")


class ComplexityQualityPolicyError(ValueError):
    """Raised when complexity quality-floor policy data is malformed or ambiguous."""


@dataclass(frozen=True, slots=True)
class ComplexityQualityPolicy:
    """Versioned monotonic minimum benchmark-quality floors by task complexity."""

    policy_id: str
    version: str
    low_min_quality: Decimal
    medium_min_quality: Decimal
    high_min_quality: Decimal

    def __post_init__(self) -> None:
        """Fail closed on malformed provenance or non-monotonic quality floors."""
        _validate_identifier(self.policy_id, "policy_id")
        _validate_identifier(self.version, "version")
        for field_name, value in (
            ("low_min_quality", self.low_min_quality),
            ("medium_min_quality", self.medium_min_quality),
            ("high_min_quality", self.high_min_quality),
        ):
            _validate_quality(value, field_name)
        if not self.low_min_quality <= self.medium_min_quality <= self.high_min_quality:
            raise ComplexityQualityPolicyError(
                "complexity quality floors must be monotonic: low <= medium <= high"
            )

    @property
    def digest(self) -> str:
        """Return deterministic SHA-256 provenance for the complete quality-floor policy."""
        canonical = json.dumps(
            {
                "policy_id": self.policy_id,
                "version": self.version,
                "low_min_quality": _canonical_decimal(self.low_min_quality),
                "medium_min_quality": _canonical_decimal(self.medium_min_quality),
                "high_min_quality": _canonical_decimal(self.high_min_quality),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def minimum_for(self, level: TaskComplexity) -> Decimal:
        """Return the explicit minimum benchmark-derived quality for one complexity level."""
        if not isinstance(level, TaskComplexity):
            raise ComplexityQualityPolicyError(
                "complexity level must use the provider-neutral vocabulary"
            )
        if level is TaskComplexity.LOW:
            return self.low_min_quality
        if level is TaskComplexity.MEDIUM:
            return self.medium_min_quality
        return self.high_min_quality


def _validate_identifier(value: object, field_name: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise ComplexityQualityPolicyError(
            f"complexity quality {field_name} must be a normalized identifier"
        )


def _validate_quality(value: object, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0 or value > 1:
        raise ComplexityQualityPolicyError(
            f"complexity quality {field_name} must be a finite Decimal between 0 and 1"
        )


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")
