import pytest
from governed_llm_gateway_contracts import (
    Message,
    MessageRole,
    StructuredOutputSchema,
    ToolCall,
    ToolDefinition,
)
from governed_llm_gateway_core.application import ProviderRequest
from governed_llm_gateway_core.domain import (
    InvalidSchemaError,
    StructuredOutputValidationError,
    ToolCallValidationError,
    parse_and_validate_structured_output,
    validate_tool_call,
)
from governed_llm_gateway_core.domain import structured as structured_domain

ARTIFACT_PATTERN = r'^(?!__.*__$)[^\p{Cc}\p{Cf}\p{Zl}\p{Zp}"\\./[\]]{1,200}$'


def _request(schema: dict[str, object]) -> ProviderRequest:
    return ProviderRequest(
        model="test-model",
        messages=(Message(role=MessageRole.USER, content="return structured data"),),
        structured_output=StructuredOutputSchema(name="safe_schema", schema=schema),
    )


def test_unicode_property_pattern_is_supported_and_enforced() -> None:
    schema = {
        "type": "object",
        "properties": {
            "value": {
                "type": "string",
                "pattern": ARTIFACT_PATTERN,
            }
        },
        "required": ["value"],
        "additionalProperties": False,
    }
    spec = StructuredOutputSchema(name="artifact", schema=schema)

    _request(schema)

    assert parse_and_validate_structured_output(
        '{"value":"artifact_123"}',
        spec,
    ) == {"value": "artifact_123"}

    with pytest.raises(StructuredOutputValidationError):
        parse_and_validate_structured_output(
            '{"value":"__forbidden__"}',
            spec,
        )

    with pytest.raises(StructuredOutputValidationError):
        parse_and_validate_structured_output(
            '{"value":"folder/name"}',
            spec,
        )


def test_pattern_evaluation_timeout_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = {
        "type": "object",
        "properties": {
            "value": {
                "type": "string",
                "pattern": "^(a+)+$",
            }
        },
        "required": ["value"],
        "additionalProperties": False,
    }
    spec = StructuredOutputSchema(name="bounded_pattern", schema=schema)

    _request(schema)

    def timeout_match(*args: object, **kwargs: object) -> bool:
        del args, kwargs
        raise TimeoutError

    monkeypatch.setattr(
        structured_domain,
        "_matches_pattern",
        timeout_match,
    )

    with pytest.raises(StructuredOutputValidationError):
        parse_and_validate_structured_output(
            '{"value":"aaaaaaaa"}',
            spec,
        )


def test_pattern_length_is_bounded_before_provider_execution() -> None:
    schema = {
        "type": "object",
        "properties": {
            "value": {
                "type": "string",
                "pattern": "^" + ("a" * 513) + "$",
            }
        },
        "required": ["value"],
        "additionalProperties": False,
    }

    with pytest.raises(InvalidSchemaError, match="pattern exceeds"):
        _request(schema)


def test_pattern_properties_keyword_is_rejected_before_provider_execution() -> None:
    schema = {
        "type": "object",
        "patternProperties": {"^a+$": {"type": "string"}},
        "additionalProperties": False,
    }

    with pytest.raises(
        InvalidSchemaError,
        match="cannot contain patternProperties in Phase 7",
    ):
        _request(schema)


def test_uri_format_is_supported_and_enforced() -> None:
    schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "format": "uri",
            }
        },
        "required": ["url"],
        "additionalProperties": False,
    }
    spec = StructuredOutputSchema(name="uri_output", schema=schema)

    _request(schema)

    assert parse_and_validate_structured_output(
        '{"url":"https://example.com/path"}',
        spec,
    ) == {"url": "https://example.com/path"}

    with pytest.raises(StructuredOutputValidationError):
        parse_and_validate_structured_output(
            '{"url":"not a uri"}',
            spec,
        )


def test_unsupported_format_is_rejected_before_provider_execution() -> None:
    schema = {
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "format": "email",
            }
        },
        "required": ["email"],
        "additionalProperties": False,
    }

    with pytest.raises(
        InvalidSchemaError,
        match="unsupported format: email",
    ):
        _request(schema)


def test_property_named_pattern_is_not_confused_with_pattern_keyword() -> None:
    schema = {
        "type": "object",
        "properties": {"pattern": {"type": "string"}},
        "required": ["pattern"],
        "additionalProperties": False,
    }

    request = _request(schema)

    assert request.structured_output is not None
    assert request.structured_output.schema == schema


def test_tool_schema_uses_same_bounded_pattern_engine() -> None:
    tool = ToolDefinition(
        name="Artifact",
        description="Work with one artifact.",
        input_schema={
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "pattern": ARTIFACT_PATTERN,
                }
            },
            "required": ["field"],
            "additionalProperties": False,
        },
    )

    request = ProviderRequest(
        model="test-model",
        messages=(Message(role=MessageRole.USER, content="lookup"),),
        tools=(tool,),
    )

    validate_tool_call(
        ToolCall(
            call_id="tool-1",
            name="Artifact",
            arguments={"field": "artifact_123"},
        ),
        request.tools,
    )

    with pytest.raises(ToolCallValidationError):
        validate_tool_call(
            ToolCall(
                call_id="tool-2",
                name="Artifact",
                arguments={"field": "__forbidden__"},
            ),
            request.tools,
        )


def test_webfetch_tool_accepts_uri_format_and_enforces_it() -> None:
    tool = ToolDefinition(
        name="WebFetch",
        description="Fetch a URL.",
        input_schema={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "format": "uri",
                },
                "prompt": {
                    "type": "string",
                },
            },
            "required": ["url", "prompt"],
            "additionalProperties": False,
        },
    )

    request = ProviderRequest(
        model="test-model",
        messages=(Message(role=MessageRole.USER, content="fetch"),),
        tools=(tool,),
    )

    validate_tool_call(
        ToolCall(
            call_id="tool-1",
            name="WebFetch",
            arguments={
                "url": "https://example.com",
                "prompt": "Summarize",
            },
        ),
        request.tools,
    )

    with pytest.raises(ToolCallValidationError):
        validate_tool_call(
            ToolCall(
                call_id="tool-2",
                name="WebFetch",
                arguments={
                    "url": "not a uri",
                    "prompt": "Summarize",
                },
            ),
            request.tools,
        )
