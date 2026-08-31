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
    "authorized_registry_candidates",
    "build_model_registry",
    "enforce_allowed_subset",
    "enforce_selected_group",
]
