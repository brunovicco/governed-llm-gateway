"""Contract tests for the explicit local-only Policy Router HTTP boundary."""

import json
import unittest
from collections.abc import Mapping
from unittest.mock import patch

import pytest
from governed_llm_gateway_core.adapters.policy_router import PolicyHttpResponse
from governed_llm_gateway_core.adapters.policy_router_loopback import LoopbackHttpPolicyTransport
from governed_llm_gateway_core.adapters.policy_router_runtime import (
    EnvironmentPolicyRouterSecretResolver,
    PolicyRouterCredentialBinding,
    PolicyRouterRuntimeConfig,
    PolicyRouterRuntimeConfigurationError,
    build_policy_router_adapter,
)


class FakePolicyHTTPResponse:
    status = 200

    def read(self, amount: int | None = None) -> bytes:
        raw = json.dumps({"ok": True}).encode("utf-8")
        return raw if amount is None else raw[:amount]

    def getheader(self, name: str) -> str | None:
        return None


class FakePolicyHTTPConnection:
    last_request: tuple[str, str, bytes | None, dict[str, str]] | None = None

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
        type(self).last_request = (method, path, body, headers)

    def getresponse(self) -> FakePolicyHTTPResponse:
        return FakePolicyHTTPResponse()

    def close(self) -> None:
        pass


def _runtime(endpoint: str) -> PolicyRouterRuntimeConfig:
    return PolicyRouterRuntimeConfig(
        enabled=True,
        endpoint=endpoint,
        timeout_seconds=5.0,
        bindings=(
            PolicyRouterCredentialBinding(
                client_id="gateway-demo",
                credential_reference="GATEWAY_DEMO_POLICY_ROUTER_API_KEY",
            ),
        ),
    )


@pytest.mark.parametrize(
    "endpoint",
    (
        "http://127.0.0.1:8001/route",
        "http://127.20.30.40:8001/route",
        "http://[::1]:8001/route",
    ),
)
def test_runtime_accepts_only_literal_loopback_http_variants(endpoint: str) -> None:
    runtime = _runtime(endpoint)

    adapter = build_policy_router_adapter(
        runtime,
        EnvironmentPolicyRouterSecretResolver(
            {"GATEWAY_DEMO_POLICY_ROUTER_API_KEY": "opaque-policy-value"}
        ),
    )

    assert adapter is not None


@pytest.mark.parametrize(
    "endpoint",
    (
        "http://localhost:8001/route",
        "http://192.168.1.10:8001/route",
        "http://policy-router.example/route",
    ),
)
def test_runtime_rejects_non_literal_or_non_loopback_http(endpoint: str) -> None:
    with pytest.raises(PolicyRouterRuntimeConfigurationError, match="HTTPS"):
        _runtime(endpoint)


@pytest.mark.parametrize(
    "endpoint",
    (
        "http://user:password@127.0.0.1:8001/route",
        "http://127.0.0.1:8001/route?credential=forbidden",
        "http://127.0.0.1:8001/route#fragment",
    ),
)
def test_runtime_keeps_endpoint_secret_and_query_guards(endpoint: str) -> None:
    with pytest.raises(PolicyRouterRuntimeConfigurationError):
        _runtime(endpoint)


class LoopbackHttpPolicyTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_transport_posts_only_to_literal_loopback_http(self) -> None:
        FakePolicyHTTPConnection.last_request = None
        with patch(
            "governed_llm_gateway_core.adapters.policy_router_loopback.http.client.HTTPConnection",
            FakePolicyHTTPConnection,
        ):
            response: PolicyHttpResponse = await LoopbackHttpPolicyTransport().post_json(
                url="http://127.0.0.1:8001/route",
                headers={"x-api-key": "opaque-policy-value"},
                payload={"workload": "rag.answer"},
                timeout_seconds=5.0,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload, {"ok": True})
        assert FakePolicyHTTPConnection.last_request is not None
        self.assertEqual(FakePolicyHTTPConnection.last_request[0], "POST")
        self.assertEqual(FakePolicyHTTPConnection.last_request[1], "/route")

    async def test_transport_revalidates_endpoint_before_opening_connection(self) -> None:
        endpoints = (
            "http://localhost:8001/route",
            "http://10.0.0.10:8001/route",
            "https://127.0.0.1:8001/route",
            "http://127.0.0.1:8001/route?x=1",
        )
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                await LoopbackHttpPolicyTransport().post_json(
                    url=endpoint,
                    headers={},
                    payload={},
                    timeout_seconds=5.0,
                )
