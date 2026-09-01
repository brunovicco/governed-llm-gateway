"""Provider-neutral structured-output and tool-call validation."""

import json
from collections.abc import Mapping, Sequence

from governed_llm_gateway_contracts import StructuredOutputSchema, ToolCall, ToolDefinition
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

_MAX_SCHEMA_BYTES = 64 * 1024
_MAX_SCHEMA_DEPTH = 32
_SCHEMA_MAP_KEYWORDS = frozenset({"$defs", "definitions", "properties", "dependentSchemas"})
_SCHEMA_LIST_KEYWORDS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
_SCHEMA_SINGLE_KEYWORDS = frozenset(
    {
        "additionalProperties",
        "unevaluatedProperties",
        "propertyNames",
        "contains",
        "items",
        "not",
        "if",
        "then",
        "else",
        "unevaluatedItems",
        "contentSchema",
    }
)


class StructuredContractError(ValueError):
    """Base error for invalid schema, structured output, or tool-call arguments."""


class InvalidSchemaError(StructuredContractError):
    """Raised when a caller-provided JSON Schema is invalid or unsafe to evaluate."""


class StructuredOutputValidationError(StructuredContractError):
    """Raised when provider output is not valid JSON matching the requested schema."""


class ToolCallValidationError(StructuredContractError):
    """Raised when a model-produced tool call is unknown or violates its input schema."""


def validate_structured_output_schema(spec: StructuredOutputSchema) -> None:
    """Validate the bounded Phase 7 Draft 2020-12 subset without external resolution."""
    _validate_schema_document(spec.schema, label="structured output")


def validate_tool_definitions(tools: Sequence[ToolDefinition]) -> None:
    """Validate tool input schemas and duplicate identities before provider translation."""
    names: set[str] = set()
    for tool in tools:
        if tool.name in names:
            raise InvalidSchemaError(f"duplicate tool definition: {tool.name}")
        names.add(tool.name)
        _validate_schema_document(tool.input_schema, label=f"tool {tool.name}")


def parse_and_validate_structured_output(text: str, spec: StructuredOutputSchema) -> object:
    """Parse provider text as JSON and validate it against the caller-requested schema."""
    validate_structured_output_schema(spec)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StructuredOutputValidationError("provider returned invalid JSON") from exc

    try:
        Draft202012Validator(dict(spec.schema)).validate(value)
    except ValidationError as exc:
        raise StructuredOutputValidationError(
            "provider output did not match requested schema"
        ) from exc
    return value


def validate_tool_call(call: ToolCall, tools: Sequence[ToolDefinition]) -> None:
    """Require a known tool and schema-valid model-generated arguments."""
    definitions = {tool.name: tool for tool in tools}
    tool = definitions.get(call.name)
    if tool is None:
        raise ToolCallValidationError(f"provider requested unknown tool: {call.name}")
    _validate_schema_document(tool.input_schema, label=f"tool {tool.name}")
    try:
        Draft202012Validator(dict(tool.input_schema)).validate(dict(call.arguments))
    except ValidationError as exc:
        raise ToolCallValidationError(
            f"provider tool arguments did not match schema for {tool.name}"
        ) from exc


def _validate_schema_document(schema: Mapping[str, object], *, label: str) -> None:
    try:
        encoded = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise InvalidSchemaError(f"{label} schema must be JSON-serializable") from exc
    if len(encoded.encode("utf-8")) > _MAX_SCHEMA_BYTES:
        raise InvalidSchemaError(f"{label} schema exceeds {_MAX_SCHEMA_BYTES} bytes")

    _validate_schema_node(schema, label=label, depth=0)
    try:
        Draft202012Validator.check_schema(dict(schema))
    except SchemaError as exc:
        raise InvalidSchemaError(f"{label} schema is not valid Draft 2020-12 JSON Schema") from exc


def _validate_schema_node(value: object, *, label: str, depth: int) -> None:
    if depth > _MAX_SCHEMA_DEPTH:
        raise InvalidSchemaError(f"{label} schema exceeds maximum depth {_MAX_SCHEMA_DEPTH}")
    if isinstance(value, bool):
        return
    if not isinstance(value, Mapping):
        return

    for keyword in ("$ref", "$dynamicRef"):
        ref = value.get(keyword)
        if isinstance(ref, str) and not ref.startswith("#"):
            raise InvalidSchemaError(f"{label} schema cannot contain remote {keyword}")

    if isinstance(value.get("pattern"), str):
        raise InvalidSchemaError(f"{label} schema cannot contain pattern in Phase 7")
    if "patternProperties" in value:
        raise InvalidSchemaError(f"{label} schema cannot contain patternProperties in Phase 7")
    if isinstance(value.get("format"), str):
        raise InvalidSchemaError(f"{label} schema cannot contain format in Phase 7")

    for keyword, child in value.items():
        next_depth = depth + 1
        if keyword in _SCHEMA_MAP_KEYWORDS and isinstance(child, Mapping):
            for subschema in child.values():
                _validate_schema_node(subschema, label=label, depth=next_depth)
            continue
        if keyword in _SCHEMA_LIST_KEYWORDS and isinstance(child, list | tuple):
            for subschema in child:
                _validate_schema_node(subschema, label=label, depth=next_depth)
            continue
        if keyword in _SCHEMA_SINGLE_KEYWORDS:
            _validate_schema_node(child, label=label, depth=next_depth)
