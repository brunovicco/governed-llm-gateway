"""Native Google Gemini generateContent adapter."""

from collections.abc import Mapping
from urllib.parse import quote

from governed_llm_gateway_contracts import (
    Base64Source,
    HttpsUrlSource,
    ImageBlock,
    MessageRole,
    TextBlock,
    ToolCall,
    ToolResultBlock,
    ToolUseBlock,
)

from governed_llm_gateway_core.adapters.http_json import (
    JsonTransport,
    StdlibJsonTransport,
    TransportFailure,
)
from governed_llm_gateway_core.adapters.provider_common import (
    normalize_transport_failure,
    require_non_negative_int,
    require_success_payload,
    require_supported_request_features,
)
from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderFeatureSupport,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)
from governed_llm_gateway_core.domain.structured import (
    StructuredOutputValidationError,
    ToolCallValidationError,
    parse_and_validate_structured_output,
    validate_tool_call,
)

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiAdapter:
    """Execute native Gemini generateContent requests with header-based API-key auth."""

    feature_support = ProviderFeatureSupport(
        native_structured_output=True,
        native_tool_calling=True,
        native_image_input=True,
        native_inline_image_input=True,
        native_tool_result_input=True,
    )

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        transport: JsonTransport | None = None,
    ) -> None:
        """Configure the native Gemini endpoint and credential."""
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._transport = transport or StdlibJsonTransport()

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Generate text, image analysis, structured output, or client-side function calls."""
        require_supported_request_features("google", request, self.feature_support)
        _require_external_url_image_model_support(request)
        system = "\n\n".join(
            message.text_content
            for message in request.messages
            if message.role is MessageRole.SYSTEM and message.text_content
        )
        contents = _google_contents(request)
        if not contents:
            raise ProviderError(
                provider="google",
                code=ProviderErrorCode.INVALID_REQUEST,
                message="google request requires at least one non-system message",
                retryable=False,
            )

        generation_config: dict[str, object] = {"maxOutputTokens": request.max_output_tokens}
        if request.structured_output is not None:
            generation_config.update(
                {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": dict(request.structured_output.schema),
                }
            )
        payload: dict[str, object] = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if request.tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parametersJsonSchema": dict(tool.input_schema),
                        }
                        for tool in request.tools
                    ]
                }
            ]

        model_path = quote(request.model.removeprefix("models/"), safe="-._")
        endpoint = f"{self._base_url}/{model_path}:generateContent"
        try:
            response = await self._transport.post_json(
                url=endpoint,
                headers={
                    "x-goog-api-key": self._api_key,
                    "content-type": "application/json",
                },
                payload=payload,
                timeout_seconds=request.timeout_seconds,
            )
        except TransportFailure as exc:
            raise normalize_transport_failure("google", exc) from exc

        data = require_success_payload("google", response)
        text, tool_calls, finish_reason = _extract_candidate(data, request)
        structured_output: object | None = None
        if request.structured_output is not None and not tool_calls:
            if not text:
                raise _invalid_structured_output("google response did not contain structured text")
            try:
                structured_output = parse_and_validate_structured_output(
                    text,
                    request.structured_output,
                )
            except StructuredOutputValidationError as exc:
                raise _invalid_structured_output(str(exc)) from exc
        if not text and not tool_calls:
            raise _invalid_response("google response did not contain text or function calls")
        return ProviderResponse(
            text=text or None,
            usage=_extract_usage(data),
            response_id=_optional_string(data.get("responseId")),
            finish_reason=finish_reason,
            structured_output=structured_output,
            tool_calls=tool_calls,
        )


def _google_contents(request: ProviderRequest) -> list[dict[str, object]]:
    """Translate provider-neutral messages into native Gemini content parts."""
    contents: list[dict[str, object]] = []
    tool_names = {
        block.call.call_id: block.call.name
        for message in request.messages
        for block in message.canonical_blocks
        if isinstance(block, ToolUseBlock)
    }
    for message in request.messages:
        if message.role is MessageRole.SYSTEM:
            continue
        parts: list[dict[str, object]] = []
        for block in message.canonical_blocks:
            if isinstance(block, TextBlock):
                parts.append({"text": block.text})
            elif isinstance(block, ImageBlock):
                if block.media_type is None:
                    raise _invalid_request(
                        "google requires a declared image media type for image input"
                    )
                if isinstance(block.source, HttpsUrlSource):
                    parts.append(
                        {
                            "fileData": {
                                "mimeType": block.media_type.value,
                                "fileUri": block.source.url,
                            }
                        }
                    )
                elif isinstance(block.source, Base64Source):
                    parts.append(
                        {
                            "inlineData": {
                                "mimeType": block.media_type.value,
                                "data": block.source.data,
                            }
                        }
                    )
            elif isinstance(block, ToolUseBlock):
                parts.append(
                    {
                        "functionCall": {
                            "id": block.call.call_id,
                            "name": block.call.name,
                            "args": dict(block.call.arguments),
                        }
                    }
                )
            elif isinstance(block, ToolResultBlock):
                parts.append(
                    {
                        "functionResponse": {
                            "id": block.result.call_id,
                            "name": tool_names[block.result.call_id],
                            "response": {
                                "output": block.result.content,
                                "is_error": block.result.is_error,
                            },
                        }
                    }
                )
        if not parts:
            continue
        contents.append(
            {
                "role": "model" if message.role is MessageRole.ASSISTANT else "user",
                "parts": parts,
            }
        )
    return contents


def _require_external_url_image_model_support(request: ProviderRequest) -> None:
    """Fail before provider I/O for Gemini 2.0, which lacks external-URL file input."""
    has_external_image = any(
        isinstance(block, ImageBlock) and isinstance(block.source, HttpsUrlSource)
        for message in request.messages
        for block in message.canonical_blocks
    )
    if not has_external_image:
        return
    model = request.model.removeprefix("models/")
    if model == "gemini-2.0" or model.startswith("gemini-2.0-"):
        raise ProviderError(
            provider="google",
            code=ProviderErrorCode.INVALID_REQUEST,
            message="google Gemini 2.0 models do not support external URL image input",
            retryable=False,
        )


def _extract_candidate(
    data: Mapping[str, object],
    request: ProviderRequest,
) -> tuple[str, tuple[ToolCall, ...], str | None]:
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise _invalid_response("google response did not contain a candidate")
    candidate = candidates[0]
    content = candidate.get("content")
    if not isinstance(content, dict):
        raise _invalid_response("google candidate did not contain content")
    parts = content.get("parts")
    if not isinstance(parts, list):
        raise _invalid_response("google candidate content did not contain parts")

    text_parts: list[str] = []
    calls: list[ToolCall] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            text_parts.append(text.strip())
        function_call = part.get("functionCall")
        if function_call is None:
            continue
        if not isinstance(function_call, dict):
            raise _invalid_tool_call("google functionCall was not an object")
        call_id = function_call.get("id")
        name = function_call.get("name")
        arguments = function_call.get("args", {})
        if not isinstance(call_id, str) or not call_id:
            raise _invalid_tool_call("google functionCall did not provide a correlation id")
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise _invalid_tool_call("google functionCall contained invalid fields")
        try:
            call = ToolCall(call_id=call_id, name=name, arguments=arguments)
            validate_tool_call(call, request.tools)
        except (ValueError, ToolCallValidationError) as exc:
            raise _invalid_tool_call(str(exc)) from exc
        calls.append(call)
    return (
        "\n".join(text_parts),
        tuple(calls),
        _optional_string(candidate.get("finishReason")),
    )


def _extract_usage(data: Mapping[str, object]) -> ProviderUsage:
    usage = data.get("usageMetadata")
    if usage is None:
        return ProviderUsage()
    if not isinstance(usage, dict):
        raise _invalid_response("google response contained invalid usage metadata")
    return ProviderUsage(
        input_tokens=require_non_negative_int(
            usage.get("promptTokenCount", 0), provider="google", field="promptTokenCount"
        ),
        output_tokens=require_non_negative_int(
            usage.get("candidatesTokenCount", 0), provider="google", field="candidatesTokenCount"
        ),
    )


def _invalid_response(message: str) -> ProviderError:
    return ProviderError(
        provider="google",
        code=ProviderErrorCode.INVALID_RESPONSE,
        message=message,
        retryable=False,
    )


def _invalid_request(message: str) -> ProviderError:
    return ProviderError(
        provider="google",
        code=ProviderErrorCode.INVALID_REQUEST,
        message=message,
        retryable=False,
    )


def _invalid_structured_output(message: str) -> ProviderError:
    return ProviderError(
        provider="google",
        code=ProviderErrorCode.INVALID_STRUCTURED_OUTPUT,
        message=message,
        retryable=False,
    )


def _invalid_tool_call(message: str) -> ProviderError:
    return ProviderError(
        provider="google",
        code=ProviderErrorCode.INVALID_TOOL_CALL,
        message=message,
        retryable=False,
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
