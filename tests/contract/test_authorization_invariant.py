import unittest

from governed_llm_gateway_core.domain import (
    AuthorizationBoundaryViolation,
    PolicyAuthorization,
    enforce_allowed_subset,
    enforce_selected_group,
)


class AuthorizationInvariantTests(unittest.TestCase):
    def test_gateway_may_restrict_policy_authorization(self) -> None:
        enforce_allowed_subset(
            frozenset({"balanced"}),
            frozenset({"balanced", "reasoning-strong"}),
        )

    def test_gateway_may_not_broaden_policy_authorization(self) -> None:
        with self.assertRaises(AuthorizationBoundaryViolation):
            enforce_allowed_subset(
                frozenset({"balanced", "agentic-strong"}),
                frozenset({"balanced"}),
            )

    def test_selected_group_must_be_authorized(self) -> None:
        authorization = PolicyAuthorization(
            decision_id="decision-1",
            authorized_model_groups=frozenset({"agentic-strong"}),
        )
        enforce_selected_group("agentic-strong", authorization)
        with self.assertRaises(AuthorizationBoundaryViolation):
            enforce_selected_group("reasoning-strong", authorization)


if __name__ == "__main__":
    unittest.main()
