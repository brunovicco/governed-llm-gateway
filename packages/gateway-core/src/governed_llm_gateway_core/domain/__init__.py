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
from .structured import (
    InvalidSchemaError,
    StructuredContractError,
    StructuredOutputValidationError,
    ToolCallValidationError,
    parse_and_validate_structured_output,
    validate_structured_output_schema,
    validate_tool_call,
    validate_tool_definitions,
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
    "InvalidSchemaError",
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
    "StructuredContractError",
    "StructuredOutputValidationError",
    "ToolCallValidationError",
    "WorkloadRankingPolicy",
    "authorized_registry_candidates",
    "build_model_registry",
    "build_ranking_policy",
    "enforce_allowed_subset",
    "enforce_selected_group",
    "parse_and_validate_structured_output",
    "validate_structured_output_schema",
    "validate_tool_call",
    "validate_tool_definitions",
]
