import json
import unittest
from unittest.mock import patch

from governed_llm_gateway_core.adapters.policy_router import (
    PolicyTransportFailure,
    PolicyTransportFailureKind,
    StdlibPolicyTransport,
)


class FakePolicyHTTPResponse:
    def __init__(
        self,
        *,
        status: int,
        payload: object,
        headers: tuple[tuple[str, str], ...] = (),
        raw: bytes | None = None,
    ) -> None:
        self.status = status
        self._raw = raw if raw is not None else json.dumps(payload).encode("utf-8")
        self._headers = dict(headers)

    def read(self, amount: int | None = None) -> bytes:
        if amount is None:
            return self._raw
        return self._raw[:amount]

    def getheader(self, name: str) -> str | None:
        return self._headers.get(name)


class FakePolicyHTTPSConnection:
    response = FakePolicyHTTPResponse(status=200, payload={"ok": True})
    request_error: BaseException | None = None
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
        if self.request_error is not None:
            raise self.request_error
        type(self).last_request = (method, path, body, headers)

    def getresponse(self) -> FakePolicyHTTPResponse:
        return self.response

    def close(self) -> None:
        pass


class StdlibPolicyTransportSecurityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        FakePolicyHTTPSConnection.response = FakePolicyHTTPResponse(
            status=200, payload={"ok": True}
        )
        FakePolicyHTTPSConnection.request_error = None
        FakePolicyHTTPSConnection.last_request = None

    async def test_https_transport_posts_json_without_exposing_request_headers_in_response(
        self,
    ) -> None:
        with patch(
            "governed_llm_gateway_core.adapters.policy_router.http.client.HTTPSConnection",
            FakePolicyHTTPSConnection,
        ):
            response = await StdlibPolicyTransport().post_json(
                url="https://policy.example/route",
                headers={"x-api-key": "secret-key"},
                payload={"workload": "rag.answer"},
                timeout_seconds=5.0,
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload, {"ok": True})
        assert FakePolicyHTTPSConnection.last_request is not None
        self.assertEqual(FakePolicyHTTPSConnection.last_request[0], "POST")
        self.assertEqual(FakePolicyHTTPSConnection.last_request[1], "/route")

    async def test_non_422_error_body_is_not_parsed_or_retained(self) -> None:
        FakePolicyHTTPSConnection.response = FakePolicyHTTPResponse(
            status=500,
            payload={"error": "raw-secret-provider-detail"},
            headers=(("Retry-After", "2"), ("Set-Cookie", "secret-cookie")),
        )
        with patch(
            "governed_llm_gateway_core.adapters.policy_router.http.client.HTTPSConnection",
            FakePolicyHTTPSConnection,
        ):
            response = await StdlibPolicyTransport().post_json(
                url="https://policy.example/route",
                headers={"x-api-key": "secret-key"},
                payload={},
                timeout_seconds=5.0,
            )
        self.assertIsNone(response.payload)
        self.assertEqual(response.retry_after, "2")
        self.assertFalse(hasattr(response, "headers"))

    async def test_422_body_is_parsed_for_rejection_provenance(self) -> None:
        payload = {"error": {"code": "no_viable_model_group"}, "decision": {"id": "d1"}}
        FakePolicyHTTPSConnection.response = FakePolicyHTTPResponse(status=422, payload=payload)
        with patch(
            "governed_llm_gateway_core.adapters.policy_router.http.client.HTTPSConnection",
            FakePolicyHTTPSConnection,
        ):
            response = await StdlibPolicyTransport().post_json(
                url="https://policy.example/route",
                headers={},
                payload={},
                timeout_seconds=5.0,
            )
        self.assertEqual(response.payload, payload)

    async def test_insecure_or_credential_bearing_endpoint_is_rejected(self) -> None:
        for endpoint in (
            "http://policy.example/route",
            "https://user:password@policy.example/route",
            "https://policy.example/route#fragment",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                await StdlibPolicyTransport().post_json(
                    url=endpoint,
                    headers={},
                    payload={},
                    timeout_seconds=5.0,
                )

    async def test_timeout_is_sanitized(self) -> None:
        FakePolicyHTTPSConnection.request_error = TimeoutError("socket secret detail")
        with (
            patch(
                "governed_llm_gateway_core.adapters.policy_router.http.client.HTTPSConnection",
                FakePolicyHTTPSConnection,
            ),
            self.assertRaises(PolicyTransportFailure) as caught,
        ):
            await StdlibPolicyTransport().post_json(
                url="https://policy.example/route",
                headers={"x-api-key": "secret-key"},
                payload={},
                timeout_seconds=5.0,
            )
        self.assertEqual(caught.exception.kind, PolicyTransportFailureKind.TIMEOUT)
        self.assertNotIn("socket secret detail", str(caught.exception))
        self.assertNotIn("secret-key", str(caught.exception))

    async def test_response_size_is_bounded(self) -> None:
        FakePolicyHTTPSConnection.response = FakePolicyHTTPResponse(
            status=200,
            payload={},
            raw=b"x" * ((512 * 1024) + 1),
        )
        with (
            patch(
                "governed_llm_gateway_core.adapters.policy_router.http.client.HTTPSConnection",
                FakePolicyHTTPSConnection,
            ),
            self.assertRaises(PolicyTransportFailure) as caught,
        ):
            await StdlibPolicyTransport().post_json(
                url="https://policy.example/route",
                headers={},
                payload={},
                timeout_seconds=5.0,
            )
        self.assertEqual(caught.exception.kind, PolicyTransportFailureKind.INVALID_RESPONSE)
