"""Credential-free contracts for the opt-in live-development smoke harness."""

import contextlib
import io
import unittest
from unittest.mock import patch
from uuid import UUID

from governed_llm_gateway_contracts import (
    ExecutionStatus,
    GatewayResponse,
    PolicyProvenance,
    ProviderExecution,
    RoutingProvenance,
    Usage,
)
from scripts import live_development_smoke

_REQUEST_ID = UUID("44444444-4444-4444-8444-444444444444")


def _response(
    *,
    authorized_model_group: str = "balanced",
    deployment: str = "openai-gpt-5-6-luna-dev",
    provider: str = "openai",
    model: str = "gpt-5.6-luna",
    content: str | None = "bounded answer",
) -> GatewayResponse:
    usage = Usage(input_tokens=12, output_tokens=4)
    routing = RoutingProvenance(
        routing_decision_id="routing-decision-1",
        policy=PolicyProvenance(
            decision_id="policy-decision-1",
            policy_id="gateway-generic-routing",
            policy_version="1.0.0",
            policy_digest="sha256:" + "a" * 64,
        ),
        authorized_model_group=authorized_model_group,
        model_registry_digest="sha256:" + "b" * 64,
        ranking_policy_version="pc33-live-development-v1",
        provider=provider,
        model=model,
        deployment=deployment,
        fallback_sequence=("openai-gpt-5-6-luna-dev", "google-gemini-3-8-flash-dev"),
    )
    execution = ProviderExecution(
        provider=provider,
        model=model,
        deployment=deployment,
        status=ExecutionStatus.SUCCEEDED,
        latency_ms=42,
        usage=usage,
        attempt_number=1,
        fallback_index=0,
        api_family="openai-responses" if provider == "openai" else "gemini-generate-content",
        max_output_tokens=128,
    )
    return GatewayResponse(
        request_id=_REQUEST_ID,
        status=ExecutionStatus.SUCCEEDED,
        content=content,
        routing=routing,
        execution=execution,
    )


class LiveDevelopmentSmokeTests(unittest.TestCase):
    def test_missing_live_flag_returns_before_async_or_network_execution(self) -> None:
        stderr = io.StringIO()
        with (
            patch("scripts.live_development_smoke.asyncio.run") as run,
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = live_development_smoke.main([])

        self.assertEqual(exit_code, 2)
        run.assert_not_called()
        self.assertIn("pass --live", stderr.getvalue())

    def test_valid_terminal_evidence_produces_metadata_only_summary(self) -> None:
        summary = live_development_smoke._validate_response(_response())
        payload = summary.as_dict()

        self.assertEqual(payload["authorized_model_group"], "balanced")
        self.assertEqual(payload["deployment"], "openai-gpt-5-6-luna-dev")
        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["model"], "gpt-5.6-luna")
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["input_tokens"], 12)
        self.assertEqual(payload["output_tokens"], 4)
        self.assertNotIn("content", payload)
        self.assertNotIn("prompt", payload)
        self.assertNotIn("api_key", payload)

    def test_unexpected_authorized_group_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            live_development_smoke.LiveDevelopmentSmokeError,
            "authorized model group",
        ):
            live_development_smoke._validate_response(
                _response(authorized_model_group="reasoning-strong")
            )

    def test_unreviewed_deployment_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            live_development_smoke.LiveDevelopmentSmokeError,
            "outside the reviewed profile",
        ):
            live_development_smoke._validate_response(
                _response(
                    deployment="unreviewed-deployment",
                    provider="openai",
                    model="gpt-5.6-luna",
                )
            )

    def test_contradictory_profile_identity_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            live_development_smoke.LiveDevelopmentSmokeError,
            "contradicts",
        ):
            live_development_smoke._validate_response(
                _response(
                    deployment="openai-gpt-5-6-luna-dev",
                    provider="google",
                    model="gemini-3.8-flash",
                )
            )

    def test_empty_completion_is_rejected_without_emitting_content(self) -> None:
        with self.assertRaisesRegex(
            live_development_smoke.LiveDevelopmentSmokeError,
            "without model content",
        ):
            live_development_smoke._validate_response(_response(content=None))


if __name__ == "__main__":
    unittest.main()
