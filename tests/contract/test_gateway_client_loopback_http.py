"""Contract tests for the thin client local-development transport boundary."""

import os
import unittest
from unittest.mock import patch

from governed_llm_gateway_client import GatewayClient, GatewayClientConfig
from governed_llm_gateway_client.errors import GatewayConfigurationError

_API_KEY = "pc35-test-gateway-key"


class GatewayClientLoopbackHTTPTests(unittest.TestCase):
    def test_accepts_https_and_literal_loopback_http(self) -> None:
        accepted = (
            ("https://gateway.example/", "https://gateway.example"),
            ("http://127.0.0.1:8000/", "http://127.0.0.1:8000"),
            ("http://127.0.0.2:8000", "http://127.0.0.2:8000"),
            ("http://[::1]:8000/", "http://[::1]:8000"),
        )

        for value, expected in accepted:
            with self.subTest(value=value):
                config = GatewayClientConfig(base_url=value, api_key=_API_KEY)
                self.assertEqual(config.base_url, expected)

    def test_rejects_non_loopback_plain_http(self) -> None:
        rejected = (
            "http://localhost:8000",
            "http://gateway.example",
            "http://10.0.0.1:8000",
            "http://172.16.0.1:8000",
            "http://192.168.1.10:8000",
            "http://169.254.1.1:8000",
        )

        for value in rejected:
            with self.subTest(value=value), self.assertRaises(GatewayConfigurationError):
                GatewayClientConfig(base_url=value, api_key=_API_KEY)

    def test_loopback_exception_does_not_relax_url_shape_validation(self) -> None:
        rejected = (
            "http://user:secret@127.0.0.1:8000",
            "http://127.0.0.1:8000?target=other",
            "http://127.0.0.1:8000#fragment",
        )

        for value in rejected:
            with self.subTest(value=value), self.assertRaises(GatewayConfigurationError):
                GatewayClientConfig(base_url=value, api_key=_API_KEY)

    def test_from_env_supports_pc33_loopback_profile_with_gateway_values_only(self) -> None:
        environment = {
            "GOVERNED_LLM_GATEWAY_URL": "http://127.0.0.1:8000",
            "GOVERNED_LLM_GATEWAY_API_KEY": _API_KEY,
            "OPENAI_API_KEY": "provider-secret-must-remain-irrelevant",
            "GEMINI_API_KEY": "provider-secret-must-remain-irrelevant-too",
            "POLICY_ROUTER_DEMO_API_KEY": "pdp-secret-must-remain-irrelevant",
        }

        with patch.dict(os.environ, environment, clear=True):
            client = GatewayClient.from_env()

        self.addCleanup(lambda: None)
        self.assertEqual(client.base_url, "http://127.0.0.1:8000")
        self.assertNotIn(_API_KEY, repr(client))


if __name__ == "__main__":
    unittest.main()
