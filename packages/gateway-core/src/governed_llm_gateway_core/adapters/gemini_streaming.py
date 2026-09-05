"""Streaming variant of the native Google Gemini generateContent adapter."""

import json
from collections.abc import AsyncGenerator, Mapping
from urllib.parse import quote

from governed_llm_gateway_contracts import MessageRole, ToolCall

from governed_llm_gateway_core.application.provider import (
    ProviderContentDelta,
    ProviderError,
    ProviderErrorCode,
    ProviderFeatureSupport,
    ProviderRequest,
    ProviderResponseCompleted,
    ProviderResponseStarted,
    ProviderStreamEvent,
    ProviderToolCallArgumentsDelta,
    ProviderToolCallCompleted,
    ProviderToolCallStarted,
    ProviderUsage,
    ProviderUsageCompleted,
)
from governed_llm_gateway_core.domain.structured import (
    StructuredOutputValidationError,
    ToolCallValidationError,
    parse_and_validate_structured_output,
    validate_tool_call,
)

from .gemini import GeminiAdapter
from .http_json import JsonTransport, TransportFailure
from .http_sse import HttpxSseTransport, SseTransport
from .provider_common import (
    normalize_transport_failure,
    require_non_negative_int,
    require_supported_request_features,
)
from .streaming_common import open_provider_sse, parse_sse_json


class GeminiStreamingAdapter(GeminiAdapter):
    """Gemini adapter using ``streamGenerateContent`` with normalized SSE events."""

    feature_support = ProviderFeatureSupport(
        native_structured_output=True,
        native_tool_calling=True,
        native_streaming=True,
        streaming_usage=True,
    )

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/models",
        transport: JsonTransport | None = None,
        sse_transport: SseTransport | None = None,
    ) -> None:
        """Configure native Gemini streaming with an injectable SSE transport."""
        super().__init__(api_key=api_key, base_url=base_url, transport=transport)
        self._sse_transport = sse_transport or HttpxSseTransport()

    async def stream(self, request: ProviderRequest) -> AsyncGenerator[ProviderStreamEvent]:
        """Yield normalized Gemini stream events and require final usage metadata."""
        require_supported_request_features("google", request, self.feature_support)
        system = "\n\n".join(
            message.content for message in request.messages if message.role is MessageRole.SYSTEM
        )
        contents = [
            {
                "role": "model" if message.role is MessageRole.ASSISTANT else "user",
                "parts": [{"text": message.content}],
            }
            for message in request.messages
            if message.role is not MessageRole.SYSTEM
        ]
        if not contents:
            raise _invalid_request("google request requires at least one non-system message")

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
        endpoint = f"{self._base_url}/{model_path}:streamGenerateContent?alt=sse"
        upstream = await open_provider_sse(
            provider="google",
            transport=self._sse_transport,
            url=endpoint,
            headers={
                "x-goog-api-key": self._api_key,
                "accept": "text/event-stream",
                "content-type": "application/json",
            },
            payload=payload,
            timeout_seconds=request.timeout_seconds,
        )

        response_id: str | None = None
        finish_reason: str | None = None
        usage: ProviderUsage | None = None
        text_parts: list[str] = []
        completed_call_ids: set[str] = set()
        semantic_output = False
        started = False

        try:
            async for raw_event in upstream:
                data = parse_sse_json("google", raw_event)
                _raise_google_stream_error(data)
                candidate_response_id = data.get("responseId")
                if isinstance(candidate_response_id, str) and candidate_response_id:
                    response_id = candidate_response_id
                if not started:
                    started = True
                    yield ProviderResponseStarted(response_id=response_id)

                candidates = data.get("candidates")
                if candidates is not None:
                    if not isinstance(candidates, list):
                        raise _invalid_response("google stream candidates was not a list")
                    for candidate in candidates:
                        if not isinstance(candidate, dict):
                            raise _invalid_response("google stream candidate was invalid")
                        reason = candidate.get("finishReason")
                        if isinstance(reason, str) and reason:
                            finish_reason = reason
                        async for event in _candidate_events(
                            candidate,
                            request=request,
                            completed_call_ids=completed_call_ids,
                            text_parts=text_parts,
                        ):
                            semantic_output = True
                            yield event

                usage_payload = data.get("usageMetadata")
                if usage_payload is not None:
                    if not isinstance(usage_payload, dict):
                        raise _invalid_response("google stream usage metadata was invalid")
                    usage = ProviderUsage(
                        input_tokens=require_non_negative_int(
                            usage_payload.get("promptTokenCount", 0),
                            provider="google",
                            field="promptTokenCount",
                        ),
                        output_tokens=require_non_negative_int(
                            usage_payload.get("candidatesTokenCount", 0),
                            provider="google",
                            field="candidatesTokenCount",
                        ),
                    )
        except TransportFailure as exc:
            raise normalize_transport_failure("google", exc) from exc
        finally:
            await upstream.aclose()

        if not started:
            raise _invalid_response("google stream ended before the first response event")
        if not semantic_output:
            raise _invalid_response("google stream completed without semantic output")
        if finish_reason is None:
            raise _invalid_response("google stream ended without a finish reason")
        if request.structured_output is not None and not completed_call_ids:
            try:
                parse_and_validate_structured_output(
                    "".join(text_parts),
                    request.structured_output,
                )
            except StructuredOutputValidationError as exc:
                raise ProviderError(
                    provider="google",
                    code=ProviderErrorCode.INVALID_STRUCTURED_OUTPUT,
                    message=str(exc),
                    retryable=False,
                ) from exc
        if usage is None:
            raise _invalid_response("google stream ended without final usage metadata")
        yield ProviderUsageCompleted(usage=usage)
        yield ProviderResponseCompleted(
            response_id=response_id,
            finish_reason=finish_reason,
        )


async def _candidate_events(
    candidate: Mapping[str, object],
    *,
    request: ProviderRequest,
    completed_call_ids: set[str],
    text_parts: list[str],
) -> AsyncIterator[ProviderStreamEvent]:
    content = candidate.get("content")
    if content is None:
        return
    if not isinstance(content, dict):
        raise _invalid_response("google stream candidate content was invalid")
    parts = content.get("parts")
    if not isinstance(parts, list):
        raise _invalid_response("google stream candidate parts was invalid")

    for part in parts:
        if not isinstance(part, dict):
            raise _invalid_response("google stream content part was invalid")
        text = part.get("text")
        if isinstance(text, str) and text:
            text_parts.append(text)
            yield ProviderContentDelta(delta=text)

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
        if call_id in completed_call_ids:
            raise _invalid_tool_call("google repeated a completed function-call correlation id")
        if not isinstance(name, str) or not name or not isinstance(arguments, dict):
            raise _invalid_tool_call("google functionCall contained invalid fields")
        try:
            call = ToolCall(call_id=call_id, name=name, arguments=arguments)
            validate_tool_call(call, request.tools)
        except (ValueError, ToolCallValidationError) as exc:
            raise _invalid_tool_call(str(exc)) from exc
        serialized_arguments = json.dumps(
            arguments,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        completed_call_ids.add(call_id)
        yield ProviderToolCallStarted(call_id=call_id, name=name)
        if serialized_arguments:
            yield ProviderToolCallArgumentsDelta(
                call_id=call_id,
                delta=serialized_arguments,
            )
        yield ProviderToolCallCompleted(call=call)


def _raise_google_stream_error(data: Mapping[str, object]) -> None:
    error = data.get("error")
    if error is None:
        return
    if not isinstance(error, dict):
        raise _invalid_response("google stream error metadata was invalid")
    status = error.get("code")
    if isinstance(status, int) and not isinstance(status, bool):
        if status == 429:
            raise ProviderError(
                provider="google",
                code=ProviderErrorCode.RATE_LIMIT,
                message="google stream was rate limited",
                retryable=True,
                status_code=status,
            )
        if status >= 500:
            raise ProviderError(
                provider="google",
                code=ProviderErrorCode.UNAVAILABLE,
                message="google stream failed with a server error",
                retryable=True,
                status_code=status,
            )
    raise _invalid_response("google stream terminated with an error payload")


def _invalid_request(message: str) -> ProviderError:
    return ProviderError(
        provider="google",
        code=ProviderErrorCode.INVALID_REQUEST,
        message=message,
        retryable=False,
    )


def _invalid_response(message: str) -> ProviderError:
    return ProviderError(
        provider="google",
        code=ProviderErrorCode.INVALID_RESPONSE,
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
