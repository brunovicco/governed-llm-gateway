"""Deterministic ranking-policy domain objects and canonical provenance."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

_IDENTIFIER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_ROOT_FIELDS = frozenset(
    {"schema_version", "policy_version", "score_snapshot_id", "source_date", "workloads"}
)
_WORKLOAD_FIELDS = frozenset({"weights", "deployments"})
_WEIGHT_FIELDS = frozenset({"quality", "reliability", "latency", "cost", "availability"})
_SCORE_FIELDS = frozenset(
    {
        "quality",
        "reliability",
        "latency",
        "cost",
        "availability",
        "expected_latency_ms",
    }
)


class RankingPolicyError(ValueError):
    """Raised when static ranking configuration is invalid or incomplete."""


class DuplicateRankingKeyError(RankingPolicyError):
    """Raised when ranking-policy YAML repeats a mapping key."""


class RankingDimension(StrEnum):
    """Stable dimensions used by the initial deterministic ranking score."""

    QUALITY = "quality"
    RELIABILITY = "reliability"
    LATENCY = "latency"
    COST = "cost"
    AVAILABILITY = "availability"


@dataclass(frozen=True, slots=True)
class RankingWeights:
    """Normalized workload-specific weights for deterministic score calculation."""

    quality: Decimal
    reliability: Decimal
    latency: Decimal
    cost: Decimal
    availability: Decimal

    def __post_init__(self) -> None:
        """Require finite weights in [0, 1] that sum exactly to one."""
        values = self.as_mapping()
        for name, value in values.items():
            if not value.is_finite() or value < 0 or value > 1:
                raise RankingPolicyError(f"ranking weight {name} must be between 0 and 1")
        if sum(values.values(), start=Decimal("0")) != Decimal("1"):
            raise RankingPolicyError("ranking weights must sum exactly to 1")

    def as_mapping(self) -> dict[str, Decimal]:
        """Return the five ranking weights keyed by stable dimension name."""
        return {
            RankingDimension.QUALITY.value: self.quality,
            RankingDimension.RELIABILITY.value: self.reliability,
            RankingDimension.LATENCY.value: self.latency,
            RankingDimension.COST.value: self.cost,
            RankingDimension.AVAILABILITY.value: self.availability,
        }


@dataclass(frozen=True, slots=True)
class StaticDeploymentScore:
    """Versioned Phase 5 score inputs for one deployment and workload."""

    deployment_id: str
    quality: Decimal
    reliability: Decimal
    latency: Decimal
    cost: Decimal
    availability: Decimal
    expected_latency_ms: int

    def __post_init__(self) -> None:
        """Require bounded static scores and positive expected latency."""
        for name, value in self.score_mapping().items():
            if not value.is_finite() or value < 0 or value > 1:
                raise RankingPolicyError(
                    f"deployment {self.deployment_id} score {name} must be between 0 and 1"
                )
        if self.expected_latency_ms <= 0:
            raise RankingPolicyError(
                f"deployment {self.deployment_id} expected_latency_ms must be positive"
            )

    def score_mapping(self) -> dict[str, Decimal]:
        """Return score dimensions without operational latency metadata."""
        return {
            RankingDimension.QUALITY.value: self.quality,
            RankingDimension.RELIABILITY.value: self.reliability,
            RankingDimension.LATENCY.value: self.latency,
            RankingDimension.COST.value: self.cost,
            RankingDimension.AVAILABILITY.value: self.availability,
        }


@dataclass(frozen=True, slots=True)
class WorkloadRankingPolicy:
    """Static deterministic ranking inputs for one workload."""

    workload: str
    weights: RankingWeights
    deployments: tuple[StaticDeploymentScore, ...]

    def score_for(self, deployment_id: str) -> StaticDeploymentScore | None:
        """Return the configured score inputs for a deployment when present."""
        for score in self.deployments:
            if score.deployment_id == deployment_id:
                return score
        return None


@dataclass(frozen=True, slots=True)
class RankingPolicy:
    """Strict, versioned Phase 5 ranking policy with deterministic digest."""

    schema_version: str
    policy_version: str
    score_snapshot_id: str
    source_date: date
    workloads: tuple[WorkloadRankingPolicy, ...]

    @property
    def digest(self) -> str:
        """Return a deterministic SHA-256 digest of canonical validated content."""
        canonical = json.dumps(
            self.canonical_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def for_workload(self, workload: str) -> WorkloadRankingPolicy:
        """Return workload ranking inputs or fail closed when not configured."""
        for policy in self.workloads:
            if policy.workload == workload:
                return policy
        raise RankingPolicyError(f"ranking policy has no workload entry for {workload!r}")

    def canonical_payload(self) -> dict[str, object]:
        """Return a canonical JSON-serializable representation."""
        workloads: dict[str, object] = {}
        for workload in sorted(self.workloads, key=lambda item: item.workload):
            deployments: dict[str, object] = {}
            for score in sorted(workload.deployments, key=lambda item: item.deployment_id):
                deployments[score.deployment_id] = {
                    **{
                        name: _canonical_decimal(value)
                        for name, value in score.score_mapping().items()
                    },
                    "expected_latency_ms": score.expected_latency_ms,
                }
            workloads[workload.workload] = {
                "weights": {
                    name: _canonical_decimal(value)
                    for name, value in workload.weights.as_mapping().items()
                },
                "deployments": deployments,
            }
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "score_snapshot_id": self.score_snapshot_id,
            "source_date": self.source_date.isoformat(),
            "workloads": workloads,
        }


def build_ranking_policy(payload: Mapping[object, object]) -> RankingPolicy:
    """Validate parsed ranking-policy data and construct immutable domain objects."""
    _require_fields(payload, _ROOT_FIELDS, _ROOT_FIELDS, "ranking policy")
    schema_version = _require_string(payload["schema_version"], "schema_version")
    if schema_version != "1.0":
        raise RankingPolicyError("ranking policy schema_version must be '1.0'")
    policy_version = _require_identifier(payload["policy_version"], "policy_version")
    score_snapshot_id = _require_identifier(payload["score_snapshot_id"], "score_snapshot_id")
    source_date = _require_date(payload["source_date"], "source_date")
    workloads_payload = _require_mapping(payload["workloads"], "workloads")

    workloads: list[WorkloadRankingPolicy] = []
    seen_workloads: set[str] = set()
    for raw_workload, raw_config in workloads_payload.items():
        workload = _require_workload_identifier(raw_workload, "workload")
        if workload in seen_workloads:
            raise RankingPolicyError(f"duplicate ranking workload: {workload}")
        seen_workloads.add(workload)
        workloads.append(_parse_workload(workload, _require_mapping(raw_config, workload)))

    return RankingPolicy(
        schema_version=schema_version,
        policy_version=policy_version,
        score_snapshot_id=score_snapshot_id,
        source_date=source_date,
        workloads=tuple(sorted(workloads, key=lambda item: item.workload)),
    )


def _parse_workload(workload: str, payload: Mapping[object, object]) -> WorkloadRankingPolicy:
    _require_fields(payload, _WORKLOAD_FIELDS, _WORKLOAD_FIELDS, f"workload {workload}")
    weights_payload = _require_mapping(payload["weights"], f"{workload}.weights")
    _require_fields(
        weights_payload,
        _WEIGHT_FIELDS,
        _WEIGHT_FIELDS,
        f"{workload}.weights",
    )
    weights = RankingWeights(
        quality=_require_decimal(weights_payload["quality"], f"{workload}.weights.quality"),
        reliability=_require_decimal(
            weights_payload["reliability"], f"{workload}.weights.reliability"
        ),
        latency=_require_decimal(weights_payload["latency"], f"{workload}.weights.latency"),
        cost=_require_decimal(weights_payload["cost"], f"{workload}.weights.cost"),
        availability=_require_decimal(
            weights_payload["availability"], f"{workload}.weights.availability"
        ),
    )

    deployments_payload = _require_mapping(payload["deployments"], f"{workload}.deployments")
    deployments: list[StaticDeploymentScore] = []
    seen_deployments: set[str] = set()
    for raw_deployment_id, raw_score in deployments_payload.items():
        deployment_id = _require_identifier(raw_deployment_id, "deployment_id")
        if deployment_id in seen_deployments:
            raise RankingPolicyError(
                f"duplicate ranking deployment for {workload}: {deployment_id}"
            )
        seen_deployments.add(deployment_id)
        score_payload = _require_mapping(raw_score, f"{workload}.deployments.{deployment_id}")
        _require_fields(
            score_payload,
            _SCORE_FIELDS,
            _SCORE_FIELDS,
            f"{workload}.deployments.{deployment_id}",
        )
        deployments.append(
            StaticDeploymentScore(
                deployment_id=deployment_id,
                quality=_require_decimal(score_payload["quality"], f"{deployment_id}.quality"),
                reliability=_require_decimal(
                    score_payload["reliability"], f"{deployment_id}.reliability"
                ),
                latency=_require_decimal(score_payload["latency"], f"{deployment_id}.latency"),
                cost=_require_decimal(score_payload["cost"], f"{deployment_id}.cost"),
                availability=_require_decimal(
                    score_payload["availability"], f"{deployment_id}.availability"
                ),
                expected_latency_ms=_require_positive_int(
                    score_payload["expected_latency_ms"],
                    f"{deployment_id}.expected_latency_ms",
                ),
            )
        )

    return WorkloadRankingPolicy(
        workload=workload,
        weights=weights,
        deployments=tuple(sorted(deployments, key=lambda item: item.deployment_id)),
    )


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
            raise RankingPolicyError(f"{location} field names must be strings")
        keys.add(key)
    unknown = sorted(keys - allowed)
    if unknown:
        raise RankingPolicyError(f"unknown {location} fields: {', '.join(unknown)}")
    missing = sorted(required - keys)
    if missing:
        raise RankingPolicyError(f"missing {location} fields: {', '.join(missing)}")


def _require_mapping(value: object, field: str) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise RankingPolicyError(f"{field} must be a mapping")
    return value


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise RankingPolicyError(f"{field} must be a string")
    return value


def _require_identifier(value: object, field: str) -> str:
    text = _require_string(value, field)
    if not text or text.strip() != text or not _IDENTIFIER_RE.fullmatch(text):
        raise RankingPolicyError(
            f"{field} must be a normalized lowercase identifier using '.', '_', or '-'"
        )
    return text


def _require_workload_identifier(value: object, field: str) -> str:
    text = _require_identifier(value, field)
    if "." not in text:
        raise RankingPolicyError(f"{field} must be a dotted workload identifier")
    return text


def _require_date(value: object, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = _require_string(value, field)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise RankingPolicyError(f"{field} must be an ISO date") from exc


def _require_decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, str | int | float | Decimal):
        raise RankingPolicyError(f"{field} must be decimal-compatible")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise RankingPolicyError(f"{field} must be a valid decimal") from exc
    if not parsed.is_finite():
        raise RankingPolicyError(f"{field} must be finite")
    return parsed


def _require_positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RankingPolicyError(f"{field} must be a positive integer")
    return value
