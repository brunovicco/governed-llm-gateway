"""Malformed provider payloads must fail closed, never crash or pass through.

Provider responses are the gateway's untrusted input: an adapter parses JSON written by
a third party. Every rejection path here was previously unexercised, which is the worst
combination for code whose whole job is to distrust its input.
"""

import asyncio
import json
import unittest
from collections.abc import AsyncIterator, Mapping

from governed_llm_gateway_contracts import Message, MessageRole, ToolDefinition
from governed_llm_gateway_core.adapters import OpenAICompatibleAdapter
from governed_llm_gateway_core.adapters.gemini_streaming import GeminiStreamingAdapter
from governed_llm_gateway_core.adapters.http_json import JsonHttpResponse
from governed_llm_gateway_core.adapters.http_sse import SseEvent, SseStream
from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderRequest,
)

WEATHER_TOOL = ToolDefinition(
    name="get_weather",
    description="Return the weather for one city.",
    input_schema={
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
        "additionalProperties": False,
    },
)


class _FakeTransport:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self.payload = payload

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        del url, headers, payload, timeout_seconds
        return JsonHttpResponse(status_code=200, headers={}, payload=self.payload)


def _adapter(payload: Mapping[str, object]) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(
        provider="groq",
        api_key="secret-groq",
        endpoint="https://example.test/v1/chat/completions",
        supports_native_tool_calling=True,
        transport=_FakeTransport(payload),
    )


def _request() -> ProviderRequest:
    return ProviderRequest(
        model="compatible-model",
        messages=(Message(role=MessageRole.USER, content="weather in Recife?"),),
        max_output_tokens=64,
        tools=(WEATHER_TOOL,),
    )


def _response_with_tool_calls(tool_calls: object) -> dict[str, object]:
    return {
        "id": "chat_1",
        "choices": [
            {"message": {"content": None, "tool_calls": tool_calls}, "finish_reason": "tool_calls"}
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": 4},
    }


def _valid_tool_call(**overrides: object) -> dict[str, object]:
    call: dict[str, object] = {
        "id": "call_1",
        "function": {"name": "get_weather", "arguments": '{"city": "Recife"}'},
    }
    call.update(overrides)
    return call


class OpenAICompatibleToolCallHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def _reject(self, tool_calls: object) -> ProviderError:
        adapter = _adapter(_response_with_tool_calls(tool_calls))
        with self.assertRaises(ProviderError) as raised:
            await adapter.generate(_request())
        return raised.exception

    async def test_a_well_formed_tool_call_is_accepted(self) -> None:
        """The negative cases below only mean something if the positive one passes."""
        adapter = _adapter(_response_with_tool_calls([_valid_tool_call()]))

        response = await adapter.generate(_request())

        self.assertEqual(len(response.tool_calls), 1)
        self.assertEqual(response.tool_calls[0].name, "get_weather")
        self.assertEqual(response.tool_calls[0].arguments, {"city": "Recife"})

    async def test_tool_calls_must_be_a_list(self) -> None:
        error = await self._reject({"not": "a list"})

        self.assertIs(error.code, ProviderErrorCode.INVALID_TOOL_CALL)

    async def test_each_tool_call_must_be_an_object(self) -> None:
        error = await self._reject(["just a string"])

        self.assertIs(error.code, ProviderErrorCode.INVALID_TOOL_CALL)

    async def test_tool_call_identity_must_be_present_and_typed(self) -> None:
        error = await self._reject([_valid_tool_call(id=17)])

        self.assertIs(error.code, ProviderErrorCode.INVALID_TOOL_CALL)

    async def test_tool_function_fields_must_be_strings(self) -> None:
        error = await self._reject(
            [{"id": "call_1", "function": {"name": "get_weather", "arguments": {"city": "Recife"}}}]
        )

        self.assertIs(error.code, ProviderErrorCode.INVALID_TOOL_CALL)

    async def test_tool_arguments_must_be_valid_json(self) -> None:
        error = await self._reject(
            [{"id": "call_1", "function": {"name": "get_weather", "arguments": "{not json"}}]
        )

        self.assertIs(error.code, ProviderErrorCode.INVALID_TOOL_CALL)

    async def test_tool_arguments_must_decode_to_an_object(self) -> None:
        error = await self._reject(
            [{"id": "call_1", "function": {"name": "get_weather", "arguments": "[1, 2, 3]"}}]
        )

        self.assertIs(error.code, ProviderErrorCode.INVALID_TOOL_CALL)

    async def test_a_tool_the_caller_never_offered_is_rejected(self) -> None:
        """A provider must not be able to invent a tool the request did not declare."""
        error = await self._reject(
            [{"id": "call_1", "function": {"name": "delete_everything", "arguments": "{}"}}]
        )

        self.assertIs(error.code, ProviderErrorCode.INVALID_TOOL_CALL)

    async def test_arguments_violating_the_declared_schema_are_rejected(self) -> None:
        error = await self._reject(
            [{"id": "call_1", "function": {"name": "get_weather", "arguments": '{"city": 42}'}}]
        )

        self.assertIs(error.code, ProviderErrorCode.INVALID_TOOL_CALL)

    async def test_rejection_never_leaks_the_raw_provider_payload(self) -> None:
        sentinel = "sk-" + "should-never-appear-in-an-error"
        error = await self._reject(
            [{"id": "call_1", "function": {"name": "get_weather", "arguments": f'"{sentinel}"'}}]
        )

        self.assertNotIn(sentinel, str(error))


class _FakeSseStream:
    def __init__(self, events: list[SseEvent]) -> None:
        self.events = events
        self.status_code = 200
        self.headers: Mapping[str, str] = {"content-type": "text/event-stream"}
        self.closed = False
        self._index = 0

    def __aiter__(self) -> AsyncIterator[SseEvent]:
        return self

    async def __anext__(self) -> SseEvent:
        if self._index >= len(self.events):
            raise StopAsyncIteration
        event = self.events[self._index]
        self._index += 1
        return event

    async def aclose(self) -> None:
        self.closed = True


class _FakeSseTransport:
    def __init__(self, stream: _FakeSseStream) -> None:
        self.stream = stream

    async def open_sse(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> SseStream:
        del url, headers, payload, timeout_seconds
        return self.stream


def _gemini_request() -> ProviderRequest:
    return ProviderRequest(
        model="gemini-model",
        messages=(Message(role=MessageRole.USER, content="hello"),),
        max_output_tokens=64,
    )


async def _drain_gemini(payload: Mapping[str, object]) -> None:
    stream = _FakeSseStream([SseEvent(event=None, data=json.dumps(payload, separators=(",", ":")))])
    adapter = GeminiStreamingAdapter(api_key="secret", sse_transport=_FakeSseTransport(stream))
    async for _ in adapter.stream(_gemini_request()):
        pass


class GeminiStreamErrorMappingTests(unittest.TestCase):
    """A provider error payload must map to a stable category, never leak, never hang."""

    def _drain(self, payload: Mapping[str, object]) -> ProviderError:
        with self.assertRaises(ProviderError) as raised:
            asyncio.run(_drain_gemini(payload))
        return raised.exception

    def test_rate_limit_maps_to_a_retryable_provider_error(self) -> None:
        error = self._drain({"error": {"code": 429, "message": "quota"}})

        self.assertIs(error.code, ProviderErrorCode.RATE_LIMIT)
        self.assertTrue(error.retryable)
        self.assertEqual(error.status_code, 429)

    def test_server_error_maps_to_retryable_unavailable(self) -> None:
        error = self._drain({"error": {"code": 503, "message": "down"}})

        self.assertIs(error.code, ProviderErrorCode.UNAVAILABLE)
        self.assertTrue(error.retryable)

    def test_client_error_is_not_silently_retried(self) -> None:
        error = self._drain({"error": {"code": 400, "message": "bad"}})

        self.assertIs(error.code, ProviderErrorCode.INVALID_RESPONSE)
        self.assertFalse(error.retryable)

    def test_non_object_error_metadata_is_rejected(self) -> None:
        error = self._drain({"error": "boom"})

        self.assertIs(error.code, ProviderErrorCode.INVALID_RESPONSE)

    def test_boolean_status_is_not_mistaken_for_an_http_code(self) -> None:
        error = self._drain({"error": {"code": True}})

        self.assertIs(error.code, ProviderErrorCode.INVALID_RESPONSE)

    def test_provider_error_message_never_carries_the_upstream_text(self) -> None:
        error = self._drain({"error": {"code": 429, "message": "quota for project acme-prod-42"}})

        self.assertNotIn("acme-prod-42", str(error))


if __name__ == "__main__":
    unittest.main()
