import unittest

import governed_llm_gateway_api
from governed_llm_gateway_client import GatewayClient, GatewayClientConfig


class WorkspaceSmokeTests(unittest.TestCase):
    def test_api_namespace_imports(self) -> None:
        self.assertIsNotNone(governed_llm_gateway_api.__doc__)

    def test_client_does_not_expose_provider_credentials(self) -> None:
        client = GatewayClient(GatewayClientConfig(base_url="https://gateway.example", api_key="x"))
        self.assertEqual(client.base_url, "https://gateway.example")
        self.assertNotIn("api_key", vars(client))


if __name__ == "__main__":
    unittest.main()
