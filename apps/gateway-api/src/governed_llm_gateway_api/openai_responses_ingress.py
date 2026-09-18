"""OpenAI Responses-compatible northbound adapter over governed execution.

The request ``model`` is a response alias only. It never bypasses workload authentication,
external PDP authorization, registry eligibility, or deterministic ranking.
"""

import base64
import binascii
import json
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from governed_llm_gateway_contracts import (
    AudioBlock,
    AudioMediaType,
    Base64Source,
    ClientProtocol,
    DocumentBlock,
    DocumentMediaType,
    HttpsUrlSource,
    ImageBlock,
    ImageMediaType,
    Message,
    MessageRole,
    StreamEventType,
    StructuredOutputSchema,
    TextBlock,
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolResultBlock,
    ToolUseBlock,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .deadline_response import DeadlineStreamingResponse, TerminalFailureFrame
from .protocol_common import (
    ProtocolGenerationPayload,
    build_protocol_payload,
    resolve_protocol_credential,
    resolve_workload,
    safe_http_error_code,
    safe_provenance_headers,
)
from .stream_generate import GenerateCoordinator, PreparedStreamingExecution, prepare_generation

OPENAI_RESPONSES_PATH = "/v1/responses"


class OpenAIInputTextModel(BaseModel):
    """Responses-shaped input text part."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["input_text"]
    text: str = Field(min_length=1)


class OpenAIOutputTextModel(BaseModel):
    """A prior assistant text part replayed by a stateless Codex client."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["output_text"]
    text: str = Field(min_length=1)


class OpenAIInputImageModel(BaseModel):
    """Responses-shaped image part using HTTPS or a bounded data URL."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["input_image"]
    image_url: str = Field(min_length=1, max_length=6 * 1024 * 1024)
    detail: Literal["auto", "low", "high", "original"] = "auto"

    def to_contract(self) -> ImageBlock:
        """Translate an image without fetching it or resolving a provider file."""
        if self.image_url.startswith("data:"):
            media_type, data = _parse_data_url(self.image_url, allowed_prefix="image/")
            return ImageBlock(
                media_type=ImageMediaType(media_type),
                source=Base64Source(data),
            )
        return ImageBlock(
            media_type=None,
            source=HttpsUrlSource(self.image_url),
        )


class OpenAIInputAudioDataModel(BaseModel):
    """Bounded inline audio payload and controlled encoding label."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    data: str = Field(min_length=1, max_length=6 * 1024 * 1024)
    format: Literal["mp3", "wav", "ogg", "webm"]


class OpenAIInputAudioModel(BaseModel):
    """Inline audio accepted in the SDK and Codex wire representations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["input_audio"]
    input_audio: OpenAIInputAudioDataModel | None = None
    audio_url: str | None = Field(default=None, min_length=1, max_length=6 * 1024 * 1024)

    @model_validator(mode="after")
    def _validate_source(self) -> "OpenAIInputAudioModel":
        if (self.input_audio is None) == (self.audio_url is None):
            raise ValueError("input audio requires exactly one inline source")
        return self

    def to_contract(self) -> AudioBlock:
        """Translate inline audio into the canonical capability-gated form."""
        if self.input_audio is not None:
            media_types = {
                "mp3": AudioMediaType.MPEG,
                "wav": AudioMediaType.WAV,
                "ogg": AudioMediaType.OGG,
                "webm": AudioMediaType.WEBM,
            }
            return AudioBlock(
                media_type=media_types[self.input_audio.format],
                source=Base64Source(self.input_audio.data),
            )
        if self.audio_url is None:  # pragma: no cover - guaranteed by model validation
            raise ValueError("input audio requires an inline source")
        media_type, data = _parse_data_url(self.audio_url, allowed_prefix="audio/")
        return AudioBlock(media_type=AudioMediaType(media_type), source=Base64Source(data))


class OpenAIInputFileModel(BaseModel):
    """Responses-shaped inline document; provider IDs and URLs are not accepted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["input_file"]
    file_data: str = Field(min_length=1, max_length=6 * 1024 * 1024)
    filename: str | None = Field(default=None, max_length=255)

    def to_contract(self) -> DocumentBlock:
        """Translate a bounded document data URL into the canonical form."""
        media_type, data = _parse_data_url(self.file_data, allowed_prefix=None)
        return DocumentBlock(
            media_type=DocumentMediaType(media_type),
            source=Base64Source(data),
            filename=self.filename,
        )


OpenAIMessageContentModel = Annotated[
    OpenAIInputTextModel
    | OpenAIOutputTextModel
    | OpenAIInputImageModel
    | OpenAIInputAudioModel
    | OpenAIInputFileModel,
    Field(discriminator="type"),
]


class OpenAIMessageItemModel(BaseModel):
    """One Responses input message item."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["message"] = "message"
    id: str | None = Field(default=None, min_length=1, max_length=256)
    role: Literal["system", "developer", "user", "assistant"]
    content: str | tuple[OpenAIMessageContentModel, ...]
    phase: Literal["commentary", "final_answer"] | None = None

    @model_validator(mode="after")
    def _validate_content_roles(self) -> "OpenAIMessageItemModel":
        if isinstance(self.content, tuple):
            if not self.content:
                raise ValueError("message content must not be empty")
            has_output = any(isinstance(block, OpenAIOutputTextModel) for block in self.content)
            if has_output and self.role != "assistant":
                raise ValueError("output_text is supported only for assistant messages")
            has_input_media = any(
                isinstance(
                    block,
                    OpenAIInputImageModel | OpenAIInputAudioModel | OpenAIInputFileModel,
                )
                for block in self.content
            )
            if has_input_media and self.role not in {"user"}:
                raise ValueError("input media is supported only for user messages")
        return self

    def to_contract(self) -> Message:
        """Translate a message and map developer instructions to canonical system role."""
        role = MessageRole.SYSTEM if self.role == "developer" else MessageRole(self.role)
        blocks: tuple[TextBlock | ImageBlock | AudioBlock | DocumentBlock, ...]
        if isinstance(self.content, str):
            blocks = (TextBlock(self.content),)
        else:
            blocks = tuple(_openai_content_block(block) for block in self.content)
        return Message(role=role, content="", blocks=blocks)


class OpenAIFunctionCallItemModel(BaseModel):
    """Prior model function call retained for stateless continuation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["function_call"]
    id: str | None = Field(default=None, min_length=1, max_length=256)
    call_id: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=128)
    arguments: str
    namespace: None = None

    def to_contract(self) -> Message:
        """Parse arguments exactly and preserve provider correlation identity."""
        try:
            arguments = json.loads(self.arguments)
        except json.JSONDecodeError as exc:
            raise ValueError("function_call arguments must be valid JSON") from exc
        if not isinstance(arguments, dict):
            raise ValueError("function_call arguments must be a JSON object")
        return Message(
            role=MessageRole.ASSISTANT,
            content="",
            blocks=(
                ToolUseBlock(ToolCall(call_id=self.call_id, name=self.name, arguments=arguments)),
            ),
        )


class OpenAIFunctionOutputTextModel(BaseModel):
    """Text-only function output part used by Codex turn replay."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["input_text"]
    text: str


class OpenAIFunctionCallOutputItemModel(BaseModel):
    """Application function output re-entering the agent loop."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["function_call_output"]
    id: str | None = Field(default=None, min_length=1, max_length=256)
    call_id: str = Field(min_length=1, max_length=256)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    namespace: None = None
    output: str | tuple[OpenAIFunctionOutputTextModel, ...]

    @model_validator(mode="after")
    def _validate_output(self) -> "OpenAIFunctionCallOutputItemModel":
        if isinstance(self.output, tuple) and not self.output:
            raise ValueError("function output content must not be empty")
        return self

    def to_contract(self) -> Message:
        """Translate output without executing or interpreting the business tool."""
        content = (
            self.output
            if isinstance(self.output, str)
            else "\n".join(part.text for part in self.output)
        )
        return Message(
            role=MessageRole.TOOL,
            content="",
            blocks=(ToolResultBlock(ToolResult(call_id=self.call_id, content=content)),),
        )


OpenAIInputItemModel = Annotated[
    OpenAIMessageItemModel | OpenAIFunctionCallItemModel | OpenAIFunctionCallOutputItemModel,
    Field(discriminator="type"),
]


class OpenAIFunctionToolModel(BaseModel):
    """Responses function-tool declaration; Codex commonly emits non-strict schemas."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["function"]
    name: str
    description: str
    parameters: dict[str, object]
    strict: bool = True
    defer_loading: Literal[False] | None = None

    def to_contract(self) -> ToolDefinition:
        """Translate the function schema without granting tool execution authority."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.parameters,
            strict=self.strict,
        )


class OpenAIJsonSchemaFormatModel(BaseModel):
    """Strict Responses JSON Schema output format."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["json_schema"]
    name: str
    schema_definition: dict[str, object] = Field(alias="schema")
    strict: Literal[True] = True


class OpenAITextConfigModel(BaseModel):
    """Responses text-output configuration wrapper."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: OpenAIJsonSchemaFormatModel | None = None
    verbosity: Literal["low", "medium", "high"] | None = None


class OpenAIReasoningModel(BaseModel):
    """Bounded Codex reasoning metadata; deployment policy remains authoritative."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    effort: Literal["none", "minimal", "low", "medium", "high", "xhigh"] | None = None
    summary: None = None
    context: None = None


class OpenAIStreamOptionsModel(BaseModel):
    """Known stream framing option; obfuscation is not security authority."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    include_obfuscation: bool = False
    reasoning_summary_delivery: None = None


class OpenAIResponsesRequestModel(BaseModel):
    """Bounded Responses subset used by stateless Codex-style agent loops."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1, max_length=256)
    input: str | tuple[OpenAIInputItemModel, ...]
    instructions: str | None = None
    max_output_tokens: int = Field(default=2000, gt=0)
    stream: bool = False
    tools: tuple[OpenAIFunctionToolModel, ...] = ()
    tool_choice: Literal["auto"] | None = None
    parallel_tool_calls: bool = False
    text: OpenAITextConfigModel | None = None
    store: Literal[False] = False
    stream_options: OpenAIStreamOptionsModel | None = None
    prompt_cache_key: str | None = Field(default=None, max_length=256)
    safety_identifier: str | None = Field(default=None, max_length=256)
    reasoning: OpenAIReasoningModel | None = None
    include: tuple[Literal["reasoning.encrypted_content"], ...] = ()
    service_tier: Literal["default"] | None = None
    client_metadata: dict[str, str] | None = Field(default=None, max_length=32)
    access_programs: None = None
    background: Literal[False] = False
    truncation: Literal["disabled"] = "disabled"

    @model_validator(mode="after")
    def _validate(self) -> "OpenAIResponsesRequestModel":
        if self.parallel_tool_calls and not self.tools:
            raise ValueError("parallel_tool_calls requires tools")
        if len(set(self.include)) != len(self.include):
            raise ValueError("include values must not be duplicated")
        if self.client_metadata is not None:
            if any(not key or len(key) > 128 for key in self.client_metadata):
                raise ValueError("client_metadata keys must contain 1-128 characters")
            if sum(len(key) + len(value) for key, value in self.client_metadata.items()) > 65536:
                raise ValueError("client_metadata exceeds the size limit")
        return self

    def to_generation_payload(self, *, workload: str) -> ProtocolGenerationPayload:
        """Translate the request into the one governed coordinator payload."""
        messages: list[Message] = []
        if self.instructions:
            messages.append(
                Message(
                    role=MessageRole.SYSTEM,
                    content="",
                    blocks=(TextBlock(self.instructions),),
                )
            )
        if isinstance(self.input, str):
            messages.append(
                Message(
                    role=MessageRole.USER,
                    content="",
                    blocks=(TextBlock(self.input),),
                )
            )
        else:
            messages.extend(item.to_contract() for item in self.input)
        structured_output = None
        if self.text is not None and self.text.format is not None:
            structured_output = StructuredOutputSchema(
                name=self.text.format.name,
                schema=self.text.format.schema_definition,
            )
        translated = build_protocol_payload(
            request_id=uuid4(),
            workload=workload,
            messages=tuple(messages),
            max_output_tokens=self.max_output_tokens,
            tools=tuple(tool.to_contract() for tool in self.tools),
            structured_output=structured_output,
            parallel_tool_calling=self.parallel_tool_calls,
            client_protocol=ClientProtocol.OPENAI_RESPONSES,
        )
        controls = tuple(
            name
            for name, present in (
                ("reasoning", self.reasoning is not None),
                ("include", bool(self.include)),
                ("service_tier", self.service_tier is not None),
                ("client_metadata", self.client_metadata is not None),
                ("text.verbosity", self.text is not None and self.text.verbosity is not None),
            )
            if present
        )
        return ProtocolGenerationPayload(
            request=translated.request,
            context_tokens_estimated=translated.context_tokens_estimated,
            max_output_tokens=translated.max_output_tokens,
            provider_timeout_seconds=translated.provider_timeout_seconds,
            client_controls=controls,
        )


def attach_openai_responses_route(app: FastAPI, coordinator: GenerateCoordinator) -> None:
    """Attach ``POST /v1/responses`` without introducing another execution path."""

    @app.post(OPENAI_RESPONSES_PATH, include_in_schema=False)
    async def responses(
        payload: OpenAIResponsesRequestModel,
        authorization: Annotated[str | None, Header()] = None,
        gateway_api_key: Annotated[str | None, Header(alias="X-Gateway-API-Key")] = None,
        gateway_workload: Annotated[str | None, Header(alias="X-Gateway-Workload")] = None,
    ) -> Response:
        try:
            credential = resolve_protocol_credential(
                authorization=authorization,
                x_api_key=None,
                gateway_api_key=gateway_api_key,
            )
            translated = payload.to_generation_payload(
                workload=resolve_workload(gateway_workload),
            )
            prepared = await prepare_generation(
                coordinator,
                api_key=credential,
                payload=translated,
            )
        except HTTPException as exc:
            return _openai_error(exc.status_code, safe_http_error_code(exc))
        except ValueError:
            return _openai_error(422, "invalid_request")

        response_id = f"resp_{translated.request_id.hex}"
        headers = {
            "Cache-Control": "no-store",
            "x-request-id": str(translated.request_id),
            "X-Accel-Buffering": "no",
            **safe_provenance_headers(prepared.decision.routing),
        }
        if payload.stream:
            return DeadlineStreamingResponse(
                _openai_stream(
                    coordinator,
                    prepared,
                    response_id=response_id,
                    model_alias=payload.model,
                ),
                media_type="text/event-stream",
                deadline=prepared.plan.deadline,
                headers=headers,
            )
        body = await _openai_aggregate(
            coordinator,
            prepared,
            response_id=response_id,
            model_alias=payload.model,
        )
        if isinstance(body, JSONResponse):
            body.headers.update(headers)
            return body
        return JSONResponse(content=body, headers=headers)


async def _openai_aggregate(
    coordinator: GenerateCoordinator,
    prepared: PreparedStreamingExecution,
    *,
    response_id: str,
    model_alias: str,
) -> dict[str, object] | JSONResponse:
    text: list[str] = []
    calls: list[ToolCall] = []
    input_tokens = 0
    output_tokens = 0
    async with aclosing(coordinator.stream(prepared)) as events:
        async for event in events:
            if event.event_type is StreamEventType.CONTENT_DELTA and event.delta is not None:
                text.append(event.delta)
            elif (
                event.event_type is StreamEventType.TOOL_CALL_COMPLETED
                and event.tool_call is not None
            ):
                calls.append(event.tool_call)
            elif event.event_type is StreamEventType.USAGE_COMPLETED and event.usage is not None:
                input_tokens = event.usage.input_tokens
                output_tokens = event.usage.output_tokens
            elif event.event_type is StreamEventType.RESPONSE_FAILED:
                code = event.error.code if event.error is not None else "gateway_stream_failed"
                return _openai_error(504 if code == "execution_deadline_exceeded" else 502, code)
    output: list[dict[str, object]] = []
    if text:
        output.append(
            _message_output_item(
                "".join(text),
                item_id=f"msg_{response_id[5:]}",
            )
        )
    output.extend(_function_output_item(call) for call in calls)
    return _response_object(
        response_id=response_id,
        model_alias=model_alias,
        status="completed",
        output=output,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


async def _openai_stream(
    coordinator: GenerateCoordinator,
    prepared: PreparedStreamingExecution,
    *,
    response_id: str,
    model_alias: str,
) -> AsyncGenerator[str]:
    sequence = 0
    text: list[str] = []
    tool_indexes: dict[str, int] = {}
    completed_output: dict[int, dict[str, object]] = {}
    input_tokens = 0
    output_tokens = 0
    text_started = False
    usage_seen = False
    text_index = 0
    next_output_index = 0
    message_id = f"msg_{response_id[5:]}"

    async with aclosing(coordinator.stream(prepared)) as events:
        async for event in events:
            if event.event_type is StreamEventType.RESPONSE_STARTED:
                sequence += 1
                yield _openai_sse(
                    "response.created",
                    {
                        "type": "response.created",
                        "sequence_number": sequence,
                        "response": _response_object(
                            response_id=response_id,
                            model_alias=model_alias,
                            status="in_progress",
                            output=[],
                        ),
                    },
                )
            elif event.event_type is StreamEventType.CONTENT_DELTA and event.delta is not None:
                if not text_started:
                    text_started = True
                    text_index = next_output_index
                    next_output_index += 1
                    sequence += 1
                    yield _openai_sse(
                        "response.output_item.added",
                        {
                            "type": "response.output_item.added",
                            "sequence_number": sequence,
                            "output_index": text_index,
                            "item": _message_output_item(
                                "",
                                item_id=message_id,
                                status="in_progress",
                            ),
                        },
                    )
                    sequence += 1
                    yield _openai_sse(
                        "response.content_part.added",
                        {
                            "type": "response.content_part.added",
                            "sequence_number": sequence,
                            "item_id": message_id,
                            "output_index": text_index,
                            "content_index": 0,
                            "part": {"type": "output_text", "text": "", "annotations": []},
                        },
                    )
                text.append(event.delta)
                sequence += 1
                yield _openai_sse(
                    "response.output_text.delta",
                    {
                        "type": "response.output_text.delta",
                        "sequence_number": sequence,
                        "item_id": message_id,
                        "output_index": text_index,
                        "content_index": 0,
                        "delta": event.delta,
                    },
                )
            elif event.event_type is StreamEventType.TOOL_CALL_STARTED:
                if event.tool_call_id is not None and event.tool_name is not None:
                    output_index = next_output_index
                    next_output_index += 1
                    tool_indexes[event.tool_call_id] = output_index
                    sequence += 1
                    yield _openai_sse(
                        "response.output_item.added",
                        {
                            "type": "response.output_item.added",
                            "sequence_number": sequence,
                            "output_index": output_index,
                            "item": {
                                "id": f"fc_{event.tool_call_id}",
                                "type": "function_call",
                                "status": "in_progress",
                                "call_id": event.tool_call_id,
                                "name": event.tool_name,
                                "arguments": "",
                            },
                        },
                    )
            elif event.event_type is StreamEventType.TOOL_CALL_ARGUMENTS_DELTA:
                if event.tool_call_id is not None and event.delta is not None:
                    sequence += 1
                    yield _openai_sse(
                        "response.function_call_arguments.delta",
                        {
                            "type": "response.function_call_arguments.delta",
                            "sequence_number": sequence,
                            "item_id": f"fc_{event.tool_call_id}",
                            "output_index": tool_indexes[event.tool_call_id],
                            "delta": event.delta,
                        },
                    )
            elif event.event_type is StreamEventType.TOOL_CALL_COMPLETED:
                if event.tool_call is not None:
                    output_index = tool_indexes[event.tool_call.call_id]
                    completed_item = _function_output_item(event.tool_call)
                    completed_output[output_index] = completed_item
                    sequence += 1
                    yield _openai_sse(
                        "response.function_call_arguments.done",
                        {
                            "type": "response.function_call_arguments.done",
                            "sequence_number": sequence,
                            "item_id": f"fc_{event.tool_call.call_id}",
                            "output_index": output_index,
                            "arguments": json.dumps(
                                event.tool_call.arguments,
                                separators=(",", ":"),
                            ),
                        },
                    )
                    sequence += 1
                    yield _openai_sse(
                        "response.output_item.done",
                        {
                            "type": "response.output_item.done",
                            "sequence_number": sequence,
                            "output_index": output_index,
                            "item": completed_item,
                        },
                    )
            elif event.event_type is StreamEventType.USAGE_COMPLETED and event.usage is not None:
                usage_seen = True
                input_tokens = event.usage.input_tokens
                output_tokens = event.usage.output_tokens
            elif event.event_type is StreamEventType.RESPONSE_COMPLETED:
                if text_started:
                    sequence += 1
                    yield _openai_sse(
                        "response.output_text.done",
                        {
                            "type": "response.output_text.done",
                            "sequence_number": sequence,
                            "item_id": message_id,
                            "output_index": text_index,
                            "content_index": 0,
                            "text": "".join(text),
                        },
                    )
                    final_text = "".join(text)
                    final_part = {"type": "output_text", "text": final_text, "annotations": []}
                    sequence += 1
                    yield _openai_sse(
                        "response.content_part.done",
                        {
                            "type": "response.content_part.done",
                            "sequence_number": sequence,
                            "item_id": message_id,
                            "output_index": text_index,
                            "content_index": 0,
                            "part": final_part,
                        },
                    )
                    completed_message = _message_output_item(final_text, item_id=message_id)
                    completed_output[text_index] = completed_message
                    sequence += 1
                    yield _openai_sse(
                        "response.output_item.done",
                        {
                            "type": "response.output_item.done",
                            "sequence_number": sequence,
                            "output_index": text_index,
                            "item": completed_message,
                        },
                    )
                output = [completed_output[index] for index in sorted(completed_output)]
                sequence += 1
                yield _openai_sse(
                    "response.completed",
                    {
                        "type": "response.completed",
                        "sequence_number": sequence,
                        "response": _response_object(
                            response_id=response_id,
                            model_alias=model_alias,
                            status="completed",
                            output=output,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                        ),
                    },
                )
            elif event.event_type is StreamEventType.RESPONSE_FAILED:
                code = event.error.code if event.error is not None else "gateway_stream_failed"
                sequence += 1
                yield _openai_sse(
                    "response.failed",
                    {
                        "type": "response.failed",
                        "sequence_number": sequence,
                        "response": {
                            **_response_object(
                                response_id=response_id,
                                model_alias=model_alias,
                                status="failed",
                                output=[],
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                            ),
                            "usage": (
                                {
                                    "input_tokens": input_tokens,
                                    "output_tokens": output_tokens,
                                    "total_tokens": input_tokens + output_tokens,
                                }
                                if usage_seen
                                else None
                            ),
                            "error": {"code": code, "message": "governed gateway execution failed"},
                        },
                    },
                )


def _openai_content_block(
    block: OpenAIMessageContentModel,
) -> TextBlock | ImageBlock | AudioBlock | DocumentBlock:
    if isinstance(block, OpenAIInputTextModel | OpenAIOutputTextModel):
        return TextBlock(block.text)
    if isinstance(block, OpenAIInputImageModel):
        return block.to_contract()
    if isinstance(block, OpenAIInputAudioModel):
        return block.to_contract()
    return block.to_contract()


def _parse_data_url(value: str, *, allowed_prefix: str | None) -> tuple[str, str]:
    header, separator, data = value.partition(",")
    if separator != "," or not header.startswith("data:") or not header.endswith(";base64"):
        raise ValueError("inline media must use a base64 data URL")
    media_type = header[5:-7]
    if allowed_prefix is not None and not media_type.startswith(allowed_prefix):
        raise ValueError("inline media type is not allowed for this content block")
    try:
        base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("inline media contains invalid base64") from exc
    return media_type, data


def _response_object(
    *,
    response_id: str,
    model_alias: str,
    status: Literal["in_progress", "completed", "failed"],
    output: list[dict[str, object]],
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> dict[str, object]:
    return {
        "id": response_id,
        "object": "response",
        "status": status,
        "model": model_alias,
        "output": output,
        "output_text": _extract_output_text(output),
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
        "error": None,
        "incomplete_details": None,
    }


def _message_output_item(
    text: str,
    *,
    item_id: str,
    status: Literal["in_progress", "completed"] = "completed",
) -> dict[str, object]:
    return {
        "id": item_id,
        "type": "message",
        "status": status,
        "role": "assistant",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def _extract_output_text(output: list[dict[str, object]]) -> str:
    """Read only validated message text from locally constructed response items."""
    parts: list[str] = []
    for item in output:
        if item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list) or not content or not isinstance(content[0], dict):
            continue
        text = content[0].get("text")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _function_output_item(call: ToolCall) -> dict[str, object]:
    return {
        "id": f"fc_{call.call_id}",
        "type": "function_call",
        "status": "completed",
        "call_id": call.call_id,
        "name": call.name,
        "arguments": json.dumps(call.arguments, separators=(",", ":")),
    }


def _openai_sse(event: str, payload: dict[str, object]) -> str:
    frame = f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
    return TerminalFailureFrame(frame) if event == "response.failed" else frame


def _openai_error(status_code: int, code: str) -> JSONResponse:
    if status_code == 401:
        error_type = "authentication_error"
    elif status_code == 429:
        error_type = "rate_limit_error"
    elif status_code in {400, 413, 415, 422}:
        error_type = "invalid_request_error"
    else:
        error_type = "api_error"
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": f"governed gateway rejected the request: {code}",
                "type": error_type,
                "param": None,
                "code": code,
            }
        },
    )
