import asyncio
from collections.abc import Mapping
from dataclasses import fields

import pytest
from governed_llm_gateway_contracts import (
    Message,
    MessageRole,
    StructuredOutputSchema,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from governed_llm_gateway_core.adapters import (
    AnthropicMessagesAdapter,
    GeminiAdapter,
    OpenAICompatibleAdapter,
    OpenAIResponsesAdapter,
)
from governed_llm_gateway_core.adapters.http_json import JsonHttpResponse
from governed_llm_gateway_core.application import ProviderError, ProviderErrorCode, ProviderRequest
from governed_llm_gateway_core.domain import (
    InvalidSchemaError,
    StructuredOutputValidationError,
    ToolCallValidationError,
    parse_and_validate_structured_output,
    validate_tool_call,
)

STRICT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}
TOOL_SCHEMA = {
    "type": "object",
    "properties": {"city": {"type": "string"}},
    "required": ["city"],
    "additionalProperties": False,
}


class FakeTransport:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self.response = JsonHttpResponse(status_code=200, headers={}, payload=payload)
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
        return self.response


class NeverCalledTransport:
    def __init__(self) -> None:
        self.calls = 0

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        del url, headers, payload, timeout_seconds
        self.calls += 1
        raise AssertionError("transport must not be called")


def structured_schema() -> StructuredOutputSchema:
    return StructuredOutputSchema(name="answer_schema", schema=STRICT_OUTPUT_SCHEMA)


def weather_tool() -> ToolDefinition:
    return ToolDefinition(
        name="get_weather",
        description="Get weather for one city.",
        input_schema=TOOL_SCHEMA,
    )


def request(
    *,
    structured: bool = False,
    tools: bool = False,
    model: str = "test-model",
) -> ProviderRequest:
    return ProviderRequest(
        model=model,
        messages=(Message(role=MessageRole.USER, content="What is the weather?"),),
        structured_output=structured_schema() if structured else None,
        tools=(weather_tool(),) if tools else (),
    )


def test_structured_output_is_validated_after_provider_text() -> None:
    spec = structured_schema()

    assert parse_and_validate_structured_output('{"answer":"ok"}', spec) == {"answer": "ok"}
    with pytest.raises(StructuredOutputValidationError):
        parse_and_validate_structured_output('{"wrong":"field"}', spec)
    with pytest.raises(StructuredOutputValidationError):
        parse_and_validate_structured_output("not-json", spec)


def test_remote_schema_reference_is_rejected_before_provider_execution() -> None:
    spec = StructuredOutputSchema(
        name="unsafe_schema",
        schema={"$ref": "https://attacker.invalid/schema.json"},
    )

    with pytest.raises(InvalidSchemaError, match="remote \\$ref"):
        ProviderRequest(
            model="test-model",
            messages=(Message(role=MessageRole.USER, content="hello"),),
            structured_output=spec,
        )


def test_tool_call_arguments_are_validated_against_known_definition() -> None:
    tool = weather_tool()
    validate_tool_call(
        ToolCall(call_id="call-1", name="get_weather", arguments={"city": "Sao Paulo"}),
        (tool,),
    )

    with pytest.raises(ToolCallValidationError, match="did not match"):
        validate_tool_call(
            ToolCall(call_id="call-2", name="get_weather", arguments={"city": 123}),
            (tool,),
        )
    with pytest.raises(ToolCallValidationError, match="unknown tool"):
        validate_tool_call(
            ToolCall(call_id="call-3", name="delete_database", arguments={}),
            (tool,),
        )


def test_tool_contracts_contain_no_execution_hook() -> None:
    assert {field.name for field in fields(ToolDefinition)} == {
        "name",
        "description",
        "input_schema",
    }
    assert {field.name for field in fields(ToolCall)} == {"call_id", "name", "arguments"}
    assert {field.name for field in fields(ToolResult)} == {"call_id", "content", "is_error"}


def test_openai_native_structured_output_maps_and_validates() -> None:
    transport = FakeTransport(
        {
            "id": "resp-1",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '{"answer":"sunny"}'}],
                }
            ],
        }
    )
    adapter = OpenAIResponsesAdapter(api_key="secret", transport=transport)

    response = asyncio.run(adapter.generate(request(structured=True)))

    assert response.structured_output == {"answer": "sunny"}
    payload = transport.calls[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["text"] == {
        "format": {
            "type": "json_schema",
            "name": "answer_schema",
            "strict": True,
            "schema": STRICT_OUTPUT_SCHEMA,
        }
    }


def test_openai_rejects_invalid_structured_output_even_after_native_enforcement() -> None:
    transport = FakeTransport(
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '{"answer":42}'}],
                }
            ],
        }
    )
    adapter = OpenAIResponsesAdapter(api_key="secret", transport=transport)

    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(adapter.generate(request(structured=True)))

    assert exc_info.value.code is ProviderErrorCode.INVALID_STRUCTURED_OUTPUT
    assert exc_info.value.retryable is False


def test_openai_normalizes_and_validates_tool_call_without_executing_it() -> None:
    transport = FakeTransport(
        {
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call-weather",
                    "name": "get_weather",
                    "arguments": '{"city":"Sao Paulo"}',
                }
            ],
        }
    )
    adapter = OpenAIResponsesAdapter(api_key="secret", transport=transport)

    response = asyncio.run(adapter.generate(request(tools=True)))

    assert response.text is None
    assert response.tool_calls == (
        ToolCall(
            call_id="call-weather",
            name="get_weather",
            arguments={"city": "Sao Paulo"},
        ),
    )
    payload = transport.calls[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["tools"] == [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get weather for one city.",
            "parameters": TOOL_SCHEMA,
            "strict": True,
        }
    ]


def test_anthropic_maps_current_output_config_and_tool_schema() -> None:
    transport = FakeTransport(
        {
            "id": "msg-1",
            "content": [{"type": "text", "text": '{"answer":"ok"}'}],
            "stop_reason": "end_turn",
        }
    )
    adapter = AnthropicMessagesAdapter(api_key="secret", transport=transport)

    response = asyncio.run(adapter.generate(request(structured=True, tools=True)))

    assert response.structured_output == {"answer": "ok"}
    payload = transport.calls[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["output_config"] == {
        "format": {"type": "json_schema", "schema": STRICT_OUTPUT_SCHEMA}
    }
    assert payload["tools"] == [
        {
            "name": "get_weather",
            "description": "Get weather for one city.",
            "input_schema": TOOL_SCHEMA,
            "strict": True,
        }
    ]


def test_anthropic_normalizes_tool_use_and_rejects_bad_arguments() -> None:
    valid_transport = FakeTransport(
        {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu-1",
                    "name": "get_weather",
                    "input": {"city": "Recife"},
                }
            ]
        }
    )
    response = asyncio.run(
        AnthropicMessagesAdapter(api_key="secret", transport=valid_transport).generate(
            request(tools=True)
        )
    )
    assert response.tool_calls[0].arguments == {"city": "Recife"}

    invalid_transport = FakeTransport(
        {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu-2",
                    "name": "get_weather",
                    "input": {"city": 12},
                }
            ]
        }
    )
    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(
            AnthropicMessagesAdapter(api_key="secret", transport=invalid_transport).generate(
                request(tools=True)
            )
        )
    assert exc_info.value.code is ProviderErrorCode.INVALID_TOOL_CALL


def test_gemini_maps_json_schema_and_function_declaration() -> None:
    transport = FakeTransport(
        {
            "candidates": [
                {
                    "content": {"parts": [{"text": '{"answer":"ok"}'}]},
                    "finishReason": "STOP",
                }
            ]
        }
    )
    adapter = GeminiAdapter(api_key="secret", transport=transport)

    response = asyncio.run(adapter.generate(request(structured=True, tools=True)))

    assert response.structured_output == {"answer": "ok"}
    payload = transport.calls[0]["payload"]
    assert isinstance(payload, dict)
    generation_config = payload["generationConfig"]
    assert isinstance(generation_config, dict)
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["responseJsonSchema"] == STRICT_OUTPUT_SCHEMA
    assert payload["tools"] == [
        {
            "functionDeclarations": [
                {
                    "name": "get_weather",
                    "description": "Get weather for one city.",
                    "parametersJsonSchema": TOOL_SCHEMA,
                }
            ]
        }
    ]


def test_gemini_function_call_requires_provider_correlation_id() -> None:
    transport = FakeTransport(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "get_weather",
                                    "args": {"city": "Salvador"},
                                }
                            }
                        ]
                    }
                }
            ]
        }
    )

    with pytest.raises(ProviderError) as exc_info:
        adapter = GeminiAdapter(api_key="secret", transport=transport)
        asyncio.run(adapter.generate(request(tools=True)))

    assert exc_info.value.code is ProviderErrorCode.INVALID_TOOL_CALL


def test_openai_compatible_does_not_fake_feature_support() -> None:
    transport = NeverCalledTransport()
    adapter = OpenAICompatibleAdapter(
        provider="custom",
        api_key="secret",
        endpoint="https://example.test/v1/chat/completions",
        transport=transport,
    )

    with pytest.raises(ProviderError) as exc_info:
        asyncio.run(adapter.generate(request(structured=True)))

    assert exc_info.value.code is ProviderErrorCode.INVALID_REQUEST
    assert transport.calls == 0


def test_openai_compatible_explicit_feature_opt_in_translates_native_contract() -> None:
    transport = FakeTransport(
        {
            "choices": [
                {
                    "message": {"content": '{"answer":"ok"}'},
                    "finish_reason": "stop",
                }
            ]
        }
    )
    adapter = OpenAICompatibleAdapter(
        provider="verified-compatible",
        api_key="secret",
        endpoint="https://example.test/v1/chat/completions",
        supports_native_structured_output=True,
        supports_native_tool_calling=True,
        transport=transport,
    )

    response = asyncio.run(adapter.generate(request(structured=True, tools=True)))

    assert response.structured_output == {"answer": "ok"}
    payload = transport.calls[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "answer_schema",
            "strict": True,
            "schema": STRICT_OUTPUT_SCHEMA,
        },
    }
    assert "tools" in payload
