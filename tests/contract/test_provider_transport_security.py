import json
import unittest
from unittest.mock import patch

from governed_llm_gateway_core.adapters.http_json import StdlibJsonTransport


class _Response:
    status = 429

    def read(self, amount: int | None = None) -> bytes:
        raw = json.dumps({"error": "raw-provider-detail"}).encode("utf-8")
        return raw if amount is None else raw[:amount]

    def getheaders(self) -> list[tuple[str, str]]:
        return [
            ("Retry-After", "3"),
            ("Set-Cookie", "sensitive-cookie"),
            ("X-Provider-Debug", "sensitive-debug"),
        ]


class _Connection:
    def __init__(self, host: str, *, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None,
        headers: dict[str, str],
    ) -> None:
        pass

    def getresponse(self) -> _Response:
        return _Response()

    def close(self) -> None:
        pass


class ProviderTransportSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_allowlisted_response_headers_cross_transport_boundary(self) -> None:
        with patch(
            "governed_llm_gateway_core.adapters.http_json.http.client.HTTPSConnection",
            _Connection,
        ):
            response = await StdlibJsonTransport().post_json(
                url="https://provider.example/v1/generate",
                headers={"authorization": "Bearer request-secret"},
                payload={"prompt": "secret-input"},
                timeout_seconds=5.0,
            )

        self.assertEqual(response.status_code, 429)
        self.assertIsNone(response.payload)
        self.assertEqual(response.headers, {"retry-after": "3"})
        self.assertNotIn("set-cookie", response.headers)
        self.assertNotIn("x-provider-debug", response.headers)


if __name__ == "__main__":
    unittest.main()
