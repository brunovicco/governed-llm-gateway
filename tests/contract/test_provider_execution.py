import json
import unittest
from collections.abc import Mapping
from unittest.mock import patch

from governed_llm_gateway_contracts import Message, MessageRole
from governed_llm_gateway_core.adapters import (
    AnthropicMessagesAdapter,
    GeminiAdapter,
    OpenAICompatibleAdapter,
    OpenAIResponsesAdapter,
)
from governed_llm_gateway_core.adapters.http_json import (
    JsonHttpResponse,
    StdlibJsonTransport,
    TransportFailure,
    TransportFailureKind,
)
from governed_llm_gateway_core.application import (
    ProviderError,
    ProviderErrorCode,
    ProviderRequest,
)


class FakeTransport:
    def __init__(
        self,
        *,
        response: JsonHttpResponse | None = None,
        failure: TransportFailure | None = None,
    ) -> None:
        self.response = response
        self.failure = failure
        self.calls: list[dict[str, object]] = []

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": dict(payload),
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.failure is not None:
            raise self.failure
        if self.response is None:
            raise AssertionError("fake transport requires a response or failure")
        return self.response


def provider_request(model: str = "test-model") -> ProviderRequest:
    return ProviderRequest(
        model=model,
        messages=(
            Message(role=MessageRole.SYSTEM, content="Be concise."),
            Message(role=MessageRole.USER, content="Hello"),
        ),
        max_output_tokens=64,
        timeout_seconds=7.5,
    )


def ok(payload: Mapping[str, object]) -> JsonHttpResponse:
    return JsonHttpResponse(status_code=200, headers={}, payload=payload)


class OpenAIResponsesAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_usage_and_native_payload(self) -> None:
        transport = FakeTransport(
            response=ok(
                {
                    "id": "resp_1",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": "Hello back"},
                            ],
                        }
                    ],
                    "usage": {"input_tokens": 5, "output_tokens": 3},
                }
            )
        )
        adapter = OpenAIResponsesAdapter(api_key="secret-openai", transport=transport)

        response = await adapter.generate(provider_request("gpt-test"))

        self.assertEqual(response.text, "Hello back")
        self.assertEqual(response.usage.input_tokens, 5)
        self.assertEqual(response.usage.output_tokens, 3)
        self.assertEqual(response.response_id, "resp_1")
        self.assertEqual(response.finish_reason, "completed")
        call = transport.calls[0]
        payload = call["payload"]
        self.assertIsInstance(payload, dict)
        assert isinstance(payload, dict)
        self.assertEqual(payload["instructions"], "Be concise.")
        self.assertEqual(payload["store"], False)
        self.assertEqual(payload["max_output_tokens"], 64)
        headers = call["headers"]
        assert isinstance(headers, dict)
        self.assertEqual(headers["authorization"], "Bearer secret-openai")

    async def test_incomplete_reason_is_preserved(self) -> None:
        transport = FakeTransport(
            response=ok(
                {
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "partial"}],
                        }
                    ],
                }
            )
        )
        response = await OpenAIResponsesAdapter(api_key="secret", transport=transport).generate(
            provider_request()
        )
        self.assertEqual(response.finish_reason, "max_output_tokens")

    async def test_empty_output_is_typed_invalid_response(self) -> None:
        adapter = OpenAIResponsesAdapter(
            api_key="secret",
            transport=FakeTransport(response=ok({"output": [], "usage": {}})),
        )
        with self.assertRaises(ProviderError) as caught:
            await adapter.generate(provider_request())
        self.assertEqual(caught.exception.code, ProviderErrorCode.INVALID_RESPONSE)


class OpenAICompatibleAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_usage_and_configurable_token_field(self) -> None:
        transport = FakeTransport(
            response=ok(
                {
                    "id": "chat_1",
                    "choices": [
                        {
                            "message": {"content": "compatible text"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 4},
                }
            )
        )
        adapter = OpenAICompatibleAdapter(
            provider="groq",
            api_key="secret-groq",
            endpoint="https://example.test/v1/chat/completions",
            max_tokens_field="max_completion_tokens",
            transport=transport,
        )

        response = await adapter.generate(provider_request("compatible-model"))

        self.assertEqual(response.text, "compatible text")
        self.assertEqual(response.usage.input_tokens, 8)
        self.assertEqual(response.usage.output_tokens, 4)
        call_payload = transport.calls[0]["payload"]
        assert isinstance(call_payload, dict)
        self.assertEqual(call_payload["max_completion_tokens"], 64)
        self.assertNotIn("max_tokens", call_payload)

    async def test_malformed_choice_is_rejected(self) -> None:
        adapter = OpenAICompatibleAdapter(
            provider="nvidia",
            api_key="secret",
            endpoint="https://example.test/v1/chat/completions",
            transport=FakeTransport(response=ok({"choices": []})),
        )
        with self.assertRaises(ProviderError) as caught:
            await adapter.generate(provider_request())
        self.assertEqual(caught.exception.code, ProviderErrorCode.INVALID_RESPONSE)


class GeminiAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_usage_roles_and_system_instruction(self) -> None:
        transport = FakeTransport(
            response=ok(
                {
                    "responseId": "gemini_1",
                    "candidates": [
                        {
                            "content": {"parts": [{"text": "Gemini text"}]},
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {"promptTokenCount": 6, "candidatesTokenCount": 2},
                }
            )
        )
        adapter = GeminiAdapter(api_key="secret-google", transport=transport)

        response = await adapter.generate(provider_request("models/gemini-test"))

        self.assertEqual(response.text, "Gemini text")
        self.assertEqual(response.usage.input_tokens, 6)
        self.assertEqual(response.usage.output_tokens, 2)
        self.assertEqual(response.finish_reason, "STOP")
        call = transport.calls[0]
        self.assertEqual(
            call["url"],
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent",
        )
        payload = call["payload"]
        assert isinstance(payload, dict)
        self.assertEqual(payload["systemInstruction"], {"parts": [{"text": "Be concise."}]})
        self.assertEqual(
            payload["contents"],
            [{"role": "user", "parts": [{"text": "Hello"}]}],
        )

    async def test_missing_candidate_is_rejected(self) -> None:
        adapter = GeminiAdapter(
            api_key="secret",
            transport=FakeTransport(response=ok({"candidates": []})),
        )
        with self.assertRaises(ProviderError) as caught:
            await adapter.generate(provider_request())
        self.assertEqual(caught.exception.code, ProviderErrorCode.INVALID_RESPONSE)


class AnthropicMessagesAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_usage_and_native_system_field(self) -> None:
        transport = FakeTransport(
            response=ok(
                {
                    "id": "msg_1",
                    "content": [{"type": "text", "text": "Claude text"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 7, "output_tokens": 3},
                }
            )
        )
        adapter = AnthropicMessagesAdapter(api_key="secret-anthropic", transport=transport)

        response = await adapter.generate(provider_request("claude-test"))

        self.assertEqual(response.text, "Claude text")
        self.assertEqual(response.usage.input_tokens, 7)
        self.assertEqual(response.usage.output_tokens, 3)
        self.assertEqual(response.finish_reason, "end_turn")
        payload = transport.calls[0]["payload"]
        assert isinstance(payload, dict)
        self.assertEqual(payload["system"], "Be concise.")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "Hello"}])
        headers = transport.calls[0]["headers"]
        assert isinstance(headers, dict)
        self.assertEqual(headers["anthropic-version"], "2023-06-01")

    async def test_missing_text_is_rejected(self) -> None:
        adapter = AnthropicMessagesAdapter(
            api_key="secret",
            transport=FakeTransport(response=ok({"content": []})),
        )
        with self.assertRaises(ProviderError) as caught:
            await adapter.generate(provider_request())
        self.assertEqual(caught.exception.code, ProviderErrorCode.INVALID_RESPONSE)


class ProviderFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_rate_limit_is_retryable_and_retry_after_is_bounded_metadata(self) -> None:
        transport = FakeTransport(
            response=JsonHttpResponse(
                status_code=429,
                headers={"retry-after": "2.5"},
                payload=None,
            )
        )
        adapter = OpenAIResponsesAdapter(api_key="super-secret", transport=transport)

        with self.assertRaises(ProviderError) as caught:
            await adapter.generate(provider_request())

        error = caught.exception
        self.assertEqual(error.code, ProviderErrorCode.RATE_LIMIT)
        self.assertTrue(error.retryable)
        self.assertEqual(error.retry_after_seconds, 2.5)
        self.assertNotIn("super-secret", str(error))

    async def test_authentication_error_never_contains_key_or_raw_body(self) -> None:
        transport = FakeTransport(
            response=JsonHttpResponse(status_code=401, headers={}, payload=None)
        )
        adapter = AnthropicMessagesAdapter(api_key="very-secret", transport=transport)

        with self.assertRaises(ProviderError) as caught:
            await adapter.generate(provider_request())

        self.assertEqual(caught.exception.code, ProviderErrorCode.AUTHENTICATION)
        self.assertFalse(caught.exception.retryable)
        self.assertNotIn("very-secret", str(caught.exception))

    async def test_5xx_is_retryable_unavailable(self) -> None:
        adapter = GeminiAdapter(
            api_key="secret",
            transport=FakeTransport(
                response=JsonHttpResponse(status_code=503, headers={}, payload=None)
            ),
        )
        with self.assertRaises(ProviderError) as caught:
            await adapter.generate(provider_request())
        self.assertEqual(caught.exception.code, ProviderErrorCode.UNAVAILABLE)
        self.assertTrue(caught.exception.retryable)

    async def test_transport_timeout_is_typed_and_sanitized(self) -> None:
        adapter = OpenAICompatibleAdapter(
            provider="openrouter",
            api_key="secret-openrouter",
            endpoint="https://openrouter.example/v1/chat/completions",
            transport=FakeTransport(
                failure=TransportFailure(TransportFailureKind.TIMEOUT, "internal detail")
            ),
        )
        with self.assertRaises(ProviderError) as caught:
            await adapter.generate(provider_request())
        self.assertEqual(caught.exception.code, ProviderErrorCode.TIMEOUT)
        self.assertTrue(caught.exception.retryable)
        self.assertNotIn("secret-openrouter", str(caught.exception))
        self.assertNotIn("internal detail", str(caught.exception))

    async def test_invalid_transport_response_is_not_retryable(self) -> None:
        adapter = OpenAIResponsesAdapter(
            api_key="secret",
            transport=FakeTransport(
                failure=TransportFailure(
                    TransportFailureKind.INVALID_RESPONSE,
                    "raw provider body must not escape",
                )
            ),
        )
        with self.assertRaises(ProviderError) as caught:
            await adapter.generate(provider_request())
        self.assertEqual(caught.exception.code, ProviderErrorCode.INVALID_RESPONSE)
        self.assertFalse(caught.exception.retryable)


class ProviderRequestTests(unittest.TestCase):
    def test_tool_messages_are_rejected_until_tool_normalization_phase(self) -> None:
        with self.assertRaisesRegex(ValueError, "tool-result"):
            ProviderRequest(
                model="model",
                messages=(Message(role=MessageRole.TOOL, content="result"),),
            )

    def test_invalid_limits_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_output_tokens"):
            ProviderRequest(
                model="model",
                messages=(Message(role=MessageRole.USER, content="hello"),),
                max_output_tokens=0,
            )
        with self.assertRaisesRegex(ValueError, "timeout_seconds"):
            ProviderRequest(
                model="model",
                messages=(Message(role=MessageRole.USER, content="hello"),),
                timeout_seconds=0,
            )


class FakeHTTPResponse:
    def __init__(
        self,
        *,
        status: int,
        payload: object,
        headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self.status = status
        self._raw = json.dumps(payload).encode("utf-8")
        self._headers = headers

    def read(self, amount: int | None = None) -> bytes:
        if amount is None:
            return self._raw
        return self._raw[:amount]

    def getheaders(self) -> list[tuple[str, str]]:
        return list(self._headers)


class FakeHTTPSConnection:
    response = FakeHTTPResponse(status=200, payload={"ok": True})
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

    def getresponse(self) -> FakeHTTPResponse:
        return self.response

    def close(self) -> None:
        pass


class StdlibJsonTransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        FakeHTTPSConnection.response = FakeHTTPResponse(status=200, payload={"ok": True})
        FakeHTTPSConnection.request_error = None
        FakeHTTPSConnection.last_request = None

    async def test_https_transport_parses_success_and_preserves_query(self) -> None:
        transport = StdlibJsonTransport()
        with patch(
            "governed_llm_gateway_core.adapters.http_json.http.client.HTTPSConnection",
            FakeHTTPSConnection,
        ):
            response = await transport.post_json(
                url="https://provider.example/v1/generate?mode=test",
                headers={"authorization": "Bearer secret"},
                payload={"hello": "world"},
                timeout_seconds=5.0,
            )
        self.assertEqual(response.payload, {"ok": True})
        assert FakeHTTPSConnection.last_request is not None
        self.assertEqual(FakeHTTPSConnection.last_request[1], "/v1/generate?mode=test")

    async def test_https_transport_does_not_parse_non_success_body(self) -> None:
        FakeHTTPSConnection.response = FakeHTTPResponse(
            status=500,
            payload={"error": "contains-secret-like-provider-detail"},
            headers=(("Retry-After", "1"),),
        )
        with patch(
            "governed_llm_gateway_core.adapters.http_json.http.client.HTTPSConnection",
            FakeHTTPSConnection,
        ):
            response = await StdlibJsonTransport().post_json(
                url="https://provider.example/v1/generate",
                headers={},
                payload={},
                timeout_seconds=5.0,
            )
        self.assertIsNone(response.payload)
        self.assertEqual(response.headers["retry-after"], "1")

    async def test_https_transport_rejects_insecure_endpoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            await StdlibJsonTransport().post_json(
                url="http://provider.example/v1/generate",
                headers={},
                payload={},
                timeout_seconds=5.0,
            )

    async def test_https_transport_classifies_timeout(self) -> None:
        FakeHTTPSConnection.request_error = TimeoutError("socket detail")
        with (
            patch(
                "governed_llm_gateway_core.adapters.http_json.http.client.HTTPSConnection",
                FakeHTTPSConnection,
            ),
            self.assertRaises(TransportFailure) as caught,
        ):
            await StdlibJsonTransport().post_json(
                url="https://provider.example/v1/generate",
                headers={},
                payload={},
                timeout_seconds=5.0,
            )
        self.assertEqual(caught.exception.kind, TransportFailureKind.TIMEOUT)

    async def test_https_transport_classifies_network_error(self) -> None:
        FakeHTTPSConnection.request_error = OSError("network detail")
        with (
            patch(
                "governed_llm_gateway_core.adapters.http_json.http.client.HTTPSConnection",
                FakeHTTPSConnection,
            ),
            self.assertRaises(TransportFailure) as caught,
        ):
            await StdlibJsonTransport().post_json(
                url="https://provider.example/v1/generate",
                headers={},
                payload={},
                timeout_seconds=5.0,
            )
        self.assertEqual(caught.exception.kind, TransportFailureKind.NETWORK)


if __name__ == "__main__":
    unittest.main()
