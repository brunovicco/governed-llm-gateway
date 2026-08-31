"""Gateway domain primitives."""

from .authorization import (
    AuthorizationBoundaryViolation,
    PolicyAuthorization,
    enforce_allowed_subset,
    enforce_selected_group,
)
from .trust import AuthenticatedWorkloadIdentity, EffectivePolicyContext

__all__ = [
    "AuthenticatedWorkloadIdentity",
    "AuthorizationBoundaryViolation",
    "EffectivePolicyContext",
    "PolicyAuthorization",
    "enforce_allowed_subset",
    "enforce_selected_group",
]
