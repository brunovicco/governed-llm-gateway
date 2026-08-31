"""Authorization invariants owned by the gateway enforcement domain."""

from dataclasses import dataclass


class AuthorizationBoundaryViolation(ValueError):
    """Raised when operational selection attempts to broaden PDP authorization."""


@dataclass(frozen=True, slots=True)
class PolicyAuthorization:
    """Authorized logical model groups returned by the PDP."""

    decision_id: str
    authorized_model_groups: frozenset[str]

    def __post_init__(self) -> None:
        """Require the PDP to authorize at least one logical model group."""
        if not self.authorized_model_groups:
            raise ValueError("authorized_model_groups must not be empty")


def enforce_allowed_subset(
    gateway_allowed_groups: frozenset[str], policy_authorized_groups: frozenset[str]
) -> None:
    """Enforce Gateway allowed set ⊆ Policy Router authorized set."""
    if not gateway_allowed_groups <= policy_authorized_groups:
        raise AuthorizationBoundaryViolation(
            "gateway allowed set must be a subset of policy-router authorization"
        )


def enforce_selected_group(selected_group: str, authorization: PolicyAuthorization) -> None:
    """Reject any selected logical group outside PDP authorization."""
    if selected_group not in authorization.authorized_model_groups:
        raise AuthorizationBoundaryViolation(
            f"selected model group {selected_group!r} is outside PDP authorization"
        )
