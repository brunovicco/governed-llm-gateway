import unittest

from governed_llm_gateway_client import GatewayClientConfig
from governed_llm_gateway_client.errors import GatewayConfigurationError
from scripts.architecture_check import client_forbidden_imports


class GatewayClientArchitectureBoundaryTests(unittest.TestCase):
    def test_client_import_allowlist_accepts_only_declared_boundary(self) -> None:
        allowed = {
            "json",
            "httpx",
            "governed_llm_gateway_client",
            "governed_llm_gateway_contracts",
            "__relative_import__",
        }
        self.assertEqual(client_forbidden_imports(allowed), set())

    def test_client_import_allowlist_rejects_arbitrary_and_dynamic_imports(self) -> None:
        blocked = client_forbidden_imports({"requests", "__dynamic_import__"})
        self.assertEqual(blocked, {"requests", "__dynamic_import__"})

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
