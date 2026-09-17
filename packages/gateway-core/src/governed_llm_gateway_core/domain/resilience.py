"""Phase 6 runtime resilience state and safety semantics."""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class CircuitState(StrEnum):
    """Per-deployment circuit-breaker state."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class HealthStatus(StrEnum):
    """Coarse runtime health derived from recent execution outcomes."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True, slots=True)
class DeploymentHealthSnapshot:
    """Metadata-only per-deployment runtime health snapshot."""

    deployment_id: str
    status: HealthStatus
    circuit_state: CircuitState
    request_count: int = 0
    success_count: int = 0
    transient_failure_count: int = 0
    timeout_count: int = 0
    rate_limit_count: int = 0
    server_error_count: int = 0
    consecutive_transient_failures: int = 0
    last_latency_ms: int | None = None

    def __post_init__(self) -> None:
        """Reject malformed counters rather than normalize impossible telemetry."""
        if not self.deployment_id or self.deployment_id.strip() != self.deployment_id:
            raise ValueError("deployment_id must be a non-empty normalized string")
        counters = (
            self.request_count,
            self.success_count,
            self.transient_failure_count,
            self.timeout_count,
            self.rate_limit_count,
            self.server_error_count,
            self.consecutive_transient_failures,
        )
        if any(value < 0 for value in counters):
            raise ValueError("runtime health counters must be non-negative")
        if self.success_count > self.request_count:
            raise ValueError("success_count cannot exceed request_count")
        if self.transient_failure_count > self.request_count:
            raise ValueError("transient_failure_count cannot exceed request_count")
        if self.last_latency_ms is not None and self.last_latency_ms < 0:
            raise ValueError("last_latency_ms must be non-negative")
        if self.circuit_state is CircuitState.OPEN and self.status is not HealthStatus.UNHEALTHY:
            raise ValueError("open circuit must be reported as unhealthy")


@dataclass(frozen=True, slots=True)
class CircuitBreakerPolicy:
    """Bounded initial per-process circuit-breaker policy."""

    failure_threshold: int = 3
    cooldown_seconds: float = 30.0
    probe_lease_seconds: float = 60.0

    def __post_init__(self) -> None:
        """Require a positive threshold and cooldown."""
        if self.failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if not isfinite(self.cooldown_seconds) or self.cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds must be finite and positive")
        if not isfinite(self.probe_lease_seconds) or self.probe_lease_seconds <= 0:
            raise ValueError("probe_lease_seconds must be finite and positive")


@dataclass(frozen=True, slots=True)
class HealthAdmission:
    """Attempt-owned circuit admission; not authorization or public telemetry."""

    deployment_id: str
    attempt_id: str
    generation: str
    probe_timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        """Reject malformed handles rather than accept unbounded execution metadata."""
        for value in (self.deployment_id, self.attempt_id, self.generation):
            if not value or value.strip() != value:
                raise ValueError("health admission IDs must be non-empty normalized strings")
        if len(self.attempt_id) > 128 or len(self.generation) > 128:
            raise ValueError("health admission owner/generation must be at most 128 characters")
        if self.probe_timeout_seconds is not None and (
            not isfinite(self.probe_timeout_seconds) or self.probe_timeout_seconds <= 0
        ):
            raise ValueError("probe_timeout_seconds must be finite and positive")

    @property
    def is_probe(self) -> bool:
        """Distinguish bounded HALF_OPEN probes from concurrent CLOSED attempts."""
        return self.probe_timeout_seconds is not None


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded retry/fallback controls for one gateway execution."""

    max_attempts_per_deployment: int = 2
    max_fallbacks: int = 2
    base_delay_seconds: float = 0.1
    max_delay_seconds: float = 2.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        """Reject unbounded or nonsensical retry settings."""
        if self.max_attempts_per_deployment <= 0:
            raise ValueError("max_attempts_per_deployment must be positive")
        if self.max_fallbacks < 0:
            raise ValueError("max_fallbacks must be non-negative")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must be non-negative")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must be >= base_delay_seconds")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class FallbackSafetyState:
    """Execution state that determines whether automatic replay remains safe."""

    provider_output_observed: bool = False
    external_side_effect_executed: bool = False
    opaque_reasoning_state_established: bool = False

    @property
    def automatic_replay_allowed(self) -> bool:
        """Allow retry/fallback only before output, side effects, or opaque continuation state."""
        return not (
            self.provider_output_observed
            or self.external_side_effect_executed
            or self.opaque_reasoning_state_established
        )
