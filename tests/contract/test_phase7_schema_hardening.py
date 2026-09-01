import pytest
from governed_llm_gateway_contracts import (
    Message,
    MessageRole,
    StructuredOutputSchema,
    ToolDefinition,
)
from governed_llm_gateway_core.application import ProviderRequest
from governed_llm_gateway_core.domain import InvalidSchemaError


def _request(schema: dict[str, object]) -> ProviderRequest:
    return ProviderRequest(
        model="test-model",
        messages=(Message(role=MessageRole.USER, content="return structured data"),),
        structured_output=StructuredOutputSchema(name="safe_schema", schema=schema),
    )


def test_pattern_keyword_is_rejected_before_provider_execution() -> None:
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string", "pattern": "^(a+)+$"}},
        "required": ["value"],
        "additionalProperties": False,
    }

    with pytest.raises(InvalidSchemaError, match="cannot contain pattern in Phase 7"):
        _request(schema)


def test_pattern_properties_keyword_is_rejected_before_provider_execution() -> None:
    schema = {
        "type": "object",
        "patternProperties": {"^(a+)+$": {"type": "string"}},
        "additionalProperties": False,
    }

    with pytest.raises(InvalidSchemaError, match="cannot contain patternProperties in Phase 7"):
        _request(schema)


def test_format_keyword_is_rejected_instead_of_being_silently_unchecked() -> None:
    schema = {
        "type": "object",
        "properties": {"email": {"type": "string", "format": "email"}},
        "required": ["email"],
        "additionalProperties": False,
    }

    with pytest.raises(InvalidSchemaError, match="cannot contain format in Phase 7"):
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


def test_tool_schema_uses_the_same_bounded_keyword_subset() -> None:
    tool = ToolDefinition(
        name="lookup",
        description="Look up one value.",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string", "pattern": "^(a+)+$"}},
            "required": ["query"],
            "additionalProperties": False,
        },
    )

    with pytest.raises(InvalidSchemaError, match="cannot contain pattern in Phase 7"):
        ProviderRequest(
            model="test-model",
            messages=(Message(role=MessageRole.USER, content="lookup"),),
            tools=(tool,),
        )
