"""Gateway domain primitives."""

from .authorization import (
    AuthorizationBoundaryViolation,
    PolicyAuthorization,
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
from .trust import AuthenticatedWorkloadIdentity, EffectivePolicyContext

__all__ = [
    "AuthenticatedWorkloadIdentity",
    "AuthorizationBoundaryViolation",
    "DuplicateRegistryKeyError",
    "EffectivePolicyContext",
    "ModelDeployment",
    "ModelRegistry",
    "ModelRegistryError",
    "PolicyAuthorization",
    "PricingMetadata",
    "build_model_registry",
    "enforce_allowed_subset",
    "enforce_selected_group",
]
