"""Deterministic metadata-only task-complexity assessment."""

import hashlib
import json
from dataclasses import dataclass
from re import fullmatch

from governed_llm_gateway_contracts import ComplexityAssessment, GatewayRequest, TaskComplexity

_IDENTIFIER_PATTERN = r"[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?"
_WORKLOAD_PATTERN = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+"
_COMPLEXITY_RANK = {
    TaskComplexity.LOW: 0,
    TaskComplexity.MEDIUM: 1,
    TaskComplexity.HIGH: 2,
}


@dataclass(frozen=True, slots=True)
class WorkloadComplexityFloor:
    """Explicit minimum complexity assigned to one normalized workload."""

    workload: str
    minimum: TaskComplexity

    def __post_init__(self) -> None:
        """Reject ambiguous workload rules before they can influence an assessment."""
        if fullmatch(_WORKLOAD_PATTERN, self.workload) is None:
            raise ValueError("complexity workload floor must use a normalized workload identifier")
        if not isinstance(self.minimum, TaskComplexity):
            raise ValueError("complexity workload floor must use the provider-neutral vocabulary")


@dataclass(frozen=True, slots=True)
class ComplexityPolicy:
    """Immutable explicit policy for deterministic metadata-only complexity assessment."""

    policy_id: str
    version: str
    medium_context_tokens: int
    high_context_tokens: int
    medium_output_tokens: int
    high_output_tokens: int
    tool_calling_floor: TaskComplexity
    structured_output_floor: TaskComplexity
    vision_floor: TaskComplexity
    workload_floors: tuple[WorkloadComplexityFloor, ...] = ()

    def __post_init__(self) -> None:
        """Fail closed on malformed thresholds, floors, or duplicate workload rules."""
        _validate_identifier(self.policy_id, "policy_id")
        _validate_identifier(self.version, "version")
        _validate_threshold_pair(
            self.medium_context_tokens,
            self.high_context_tokens,
            "context token",
        )
        _validate_threshold_pair(
            self.medium_output_tokens,
            self.high_output_tokens,
            "output token",
        )
        for field_name, floor in (
            ("tool_calling_floor", self.tool_calling_floor),
            ("structured_output_floor", self.structured_output_floor),
            ("vision_floor", self.vision_floor),
        ):
            if not isinstance(floor, TaskComplexity):
                raise ValueError(f"complexity {field_name} must use the provider-neutral vocabulary")
        workloads = tuple(rule.workload for rule in self.workload_floors)
        if len(workloads) != len(set(workloads)):
            raise ValueError("complexity workload floors must not contain duplicate workloads")
        if workloads != tuple(sorted(workloads)):
            raise ValueError("complexity workload floors must be sorted by workload")


class DeterministicComplexityEvaluator:
    """Assess complexity from explicit metadata without model-selection authority."""

    def __init__(self, policy: ComplexityPolicy) -> None:
        """Bind one immutable versioned assessment policy."""
        self._policy = policy

    def assess(
        self,
        request: GatewayRequest,
        *,
        context_tokens_estimated: int,
        max_output_tokens_estimated: int,
    ) -> ComplexityAssessment:
        """Return deterministic metadata-only complexity evidence for one request."""
        if context_tokens_estimated < 0:
            raise ValueError("context_tokens_estimated must be non-negative")
        if max_output_tokens_estimated <= 0:
            raise ValueError("max_output_tokens_estimated must be positive")

        effective_context_tokens = max(
            context_tokens_estimated,
            request.requirements.min_context_tokens,
        )
        level = TaskComplexity.LOW
        level = _max_complexity(
            level,
            _threshold_level(
                effective_context_tokens,
                medium=self._policy.medium_context_tokens,
                high=self._policy.high_context_tokens,
            ),
        )
        level = _max_complexity(
            level,
            _threshold_level(
                max_output_tokens_estimated,
                medium=self._policy.medium_output_tokens,
                high=self._policy.high_output_tokens,
            ),
        )
        if request.requirements.tool_calling:
            level = _max_complexity(level, self._policy.tool_calling_floor)
        if request.requirements.structured_output:
            level = _max_complexity(level, self._policy.structured_output_floor)
        if request.requirements.vision:
            level = _max_complexity(level, self._policy.vision_floor)
        workload_floor = _workload_floor(self._policy.workload_floors, request.workload)
        if workload_floor is not None:
            level = _max_complexity(level, workload_floor)

        assessment_id = _assessment_id(
            self._policy,
            request,
            context_tokens_estimated=context_tokens_estimated,
            effective_context_tokens=effective_context_tokens,
            max_output_tokens_estimated=max_output_tokens_estimated,
            level=level,
        )
        return ComplexityAssessment(
            level=level,
            assessment_id=assessment_id,
            evaluator_id=self._policy.policy_id,
            evaluator_version=self._policy.version,
        )


def _validate_identifier(value: str, field_name: str) -> None:
    if fullmatch(_IDENTIFIER_PATTERN, value) is None:
        raise ValueError(f"complexity {field_name} must be a normalized identifier")


def _validate_threshold_pair(medium: int, high: int, label: str) -> None:
    if medium <= 0:
        raise ValueError(f"complexity medium {label} threshold must be positive")
    if high <= medium:
        raise ValueError(f"complexity high {label} threshold must exceed medium threshold")


def _threshold_level(value: int, *, medium: int, high: int) -> TaskComplexity:
    if value >= high:
        return TaskComplexity.HIGH
    if value >= medium:
        return TaskComplexity.MEDIUM
    return TaskComplexity.LOW


def _max_complexity(left: TaskComplexity, right: TaskComplexity) -> TaskComplexity:
    return left if _COMPLEXITY_RANK[left] >= _COMPLEXITY_RANK[right] else right


def _workload_floor(
    rules: tuple[WorkloadComplexityFloor, ...],
    workload: str,
) -> TaskComplexity | None:
    for rule in rules:
        if rule.workload == workload:
            return rule.minimum
    return None


def _assessment_id(
    policy: ComplexityPolicy,
    request: GatewayRequest,
    *,
    context_tokens_estimated: int,
    effective_context_tokens: int,
    max_output_tokens_estimated: int,
    level: TaskComplexity,
) -> str:
    payload = {
        "assessment": {
            "level": level.value,
            "workload": request.workload,
            "context_tokens_estimated": context_tokens_estimated,
            "effective_context_tokens": effective_context_tokens,
            "max_output_tokens_estimated": max_output_tokens_estimated,
            "requirements": {
                "tool_calling": request.requirements.tool_calling,
                "structured_output": request.requirements.structured_output,
                "vision": request.requirements.vision,
                "streaming": request.requirements.streaming,
                "min_context_tokens": request.requirements.min_context_tokens,
            },
        },
        "policy": {
            "policy_id": policy.policy_id,
            "version": policy.version,
            "medium_context_tokens": policy.medium_context_tokens,
            "high_context_tokens": policy.high_context_tokens,
            "medium_output_tokens": policy.medium_output_tokens,
            "high_output_tokens": policy.high_output_tokens,
            "tool_calling_floor": policy.tool_calling_floor.value,
            "structured_output_floor": policy.structured_output_floor.value,
            "vision_floor": policy.vision_floor.value,
            "workload_floors": [
                {"workload": rule.workload, "minimum": rule.minimum.value}
                for rule in policy.workload_floors
            ],
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
