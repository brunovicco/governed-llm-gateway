import unittest

from governed_llm_gateway_client import GatewayClientConfig
from governed_llm_gateway_client.errors import GatewayConfigurationError


class GatewayClientStreamLimitTests(unittest.TestCase):
    def test_stream_limit_must_cover_maximum_event(self) -> None:
        with self.assertRaises(GatewayConfigurationError):
            GatewayClientConfig(
                base_url="https://gateway.example",
                api_key="gateway-key",
                max_sse_event_bytes=2048,
                max_sse_stream_bytes=1024,
            )

    def test_stream_limit_has_hard_safety_ceiling(self) -> None:
        with self.assertRaises(GatewayConfigurationError):
            GatewayClientConfig(
                base_url="https://gateway.example",
                api_key="gateway-key",
                max_sse_stream_bytes=129 * 1024 * 1024,
            )

    def test_stream_limits_reject_boolean_values(self) -> None:
        with self.assertRaises(GatewayConfigurationError):
            GatewayClientConfig(
                base_url="https://gateway.example",
                api_key="gateway-key",
                max_sse_event_bytes=True,
            )
        with self.assertRaises(GatewayConfigurationError):
            GatewayClientConfig(
                base_url="https://gateway.example",
                api_key="gateway-key",
                max_sse_stream_bytes=True,
            )
