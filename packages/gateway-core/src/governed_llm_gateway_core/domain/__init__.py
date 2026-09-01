"""Gateway domain primitives."""

from .authorization import (
    AuthorizationBoundaryViolation,
    PolicyAuthorization,
    authorized_registry_candidates,
    enforce_allowed_subset,
    enforce_selected_group,
)
from .model_registry import (
    DuplicateRegistryKeyError,
    ModelDeployment,
    ModelRegistry,
    ModelRegistryError,
    PricingMetadata,
    build_model_registry,
)
from .ranking import (
    DuplicateRankingKeyError,
    RankingDimension,
    RankingPolicy,
    RankingPolicyError,
    RankingWeights,
    StaticDeploymentScore,
    WorkloadRankingPolicy,
    build_ranking_policy,
)
from .resilience import (
    CircuitBreakerPolicy,
    CircuitState,
    DeploymentHealthSnapshot,
    FallbackSafetyState,
    HealthStatus,
    RetryPolicy,
)
from .trust import AuthenticatedWorkloadIdentity, EffectivePolicyContext

__all__ = [
    "AuthenticatedWorkloadIdentity",
    "AuthorizationBoundaryViolation",
    "CircuitBreakerPolicy",
    "CircuitState",
    "DeploymentHealthSnapshot",
    "DuplicateRankingKeyError",
    "DuplicateRegistryKeyError",
    "EffectivePolicyContext",
    "FallbackSafetyState",
    "HealthStatus",
    "ModelDeployment",
    "ModelRegistry",
    "ModelRegistryError",
    "PolicyAuthorization",
    "PricingMetadata",
    "RankingDimension",
    "RankingPolicy",
    "RankingPolicyError",
    "RankingWeights",
    "RetryPolicy",
    "StaticDeploymentScore",
    "WorkloadRankingPolicy",
    "authorized_registry_candidates",
    "build_model_registry",
    "build_ranking_policy",
    "enforce_allowed_subset",
    "enforce_selected_group",
]
