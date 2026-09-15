"""Anthropic Messages-compatible northbound adapter over the governed execution path.

This is a protocol translator, never a router. The client-supplied ``model`` is echoed as an
alias; the authenticated workload, external PDP, registry and deterministic ranker retain all
authority over the concrete provider/model deployment.
"""

import json
from collections.abc import AsyncGenerator
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse, StreamingResponse
from governed_llm_gateway_contracts import (
    Base64Source,
    ClientProtocol,
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

from .protocol_common import (
    ProtocolGenerationPayload,
    build_protocol_payload,
    resolve_protocol_credential,
    resolve_workload,
    safe_http_error_code,
    safe_provenance_headers,
)
from .stream_generate import GenerateCoordinator, PreparedStreamingExecution, prepare_generation

ANTHROPIC_MESSAGES_PATH = "/v1/messages"


class AnthropicCacheControlModel(BaseModel):
    """Known prompt-cache hint accepted as non-semantic client metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["ephemeral"]
    ttl: Literal["5m", "1h"] | None = None


class AnthropicTextBlockModel(BaseModel):
    """Anthropic-shaped text content block."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["text"]
    text: str = Field(min_length=1)
    cache_control: AnthropicCacheControlModel | None = None


class AnthropicUrlSourceModel(BaseModel):
    """Anthropic-shaped HTTPS image source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["url"]
    url: str = Field(min_length=1, max_length=2048)


class AnthropicBase64SourceModel(BaseModel):
    """Anthropic-shaped inline image source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["base64"]
    media_type: ImageMediaType
    data: str = Field(min_length=1, max_length=6 * 1024 * 1024)


AnthropicImageSourceModel = Annotated[
    AnthropicUrlSourceModel | AnthropicBase64SourceModel,
    Field(discriminator="type"),
]


class AnthropicImageBlockModel(BaseModel):
    """Anthropic-shaped image content block."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["image"]
    source: AnthropicImageSourceModel
    cache_control: AnthropicCacheControlModel | None = None


class AnthropicToolUseBlockModel(BaseModel):
    """Anthropic-shaped prior assistant tool call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["tool_use"]
    id: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=128)
    input: dict[str, object]
    cache_control: AnthropicCacheControlModel | None = None


class AnthropicToolResultBlockModel(BaseModel):
    """Anthropic-shaped application tool result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["tool_result"]
    tool_use_id: str = Field(min_length=1, max_length=256)
    content: str | tuple[AnthropicTextBlockModel, ...]
    is_error: bool = False
    cache_control: AnthropicCacheControlModel | None = None

    @property
    def text(self) -> str:
        """Normalize a string or text-block result without executing the tool."""
        if isinstance(self.content, str):
            return self.content
        return "\n".join(block.text for block in self.content)


AnthropicContentBlockModel = Annotated[
    AnthropicTextBlockModel
    | AnthropicImageBlockModel
    | AnthropicToolUseBlockModel
    | AnthropicToolResultBlockModel,
    Field(discriminator="type"),
]


class AnthropicMessageModel(BaseModel):
    """One bounded Anthropic-shaped input message."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["user", "assistant", "system"]
    content: str | tuple[AnthropicContentBlockModel, ...]

    def to_contract(self) -> Message:
        """Translate known blocks into immutable provider-neutral contracts."""
        blocks: list[TextBlock | ImageBlock | ToolUseBlock | ToolResultBlock] = []
        if isinstance(self.content, str):
            blocks.append(TextBlock(self.content))
        else:
            for block in self.content:
                if isinstance(block, AnthropicTextBlockModel):
                    blocks.append(TextBlock(block.text))
                elif isinstance(block, AnthropicImageBlockModel):
                    source: HttpsUrlSource | Base64Source
                    if isinstance(block.source, AnthropicUrlSourceModel):
                        source = HttpsUrlSource(block.source.url)
                        media_type = None
                    else:
                        source = Base64Source(block.source.data)
                        media_type = block.source.media_type
                    blocks.append(ImageBlock(media_type=media_type, source=source))
                elif isinstance(block, AnthropicToolUseBlockModel):
                    blocks.append(
                        ToolUseBlock(
                            ToolCall(
                                call_id=block.id,
                                name=block.name,
                                arguments=block.input,
                            )
                        )
                    )
                else:
                    blocks.append(
                        ToolResultBlock(
                            ToolResult(
                                call_id=block.tool_use_id,
                                content=block.text,
                                is_error=block.is_error,
                            )
                        )
                    )
        return Message(role=MessageRole(self.role), content="", blocks=tuple(blocks))


class AnthropicToolModel(BaseModel):
    """One Anthropic-shaped function tool declaration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str
    input_schema: dict[str, object]
    strict: bool = False
    cache_control: AnthropicCacheControlModel | None = None

    def to_contract(self) -> ToolDefinition:
        """Translate a function schema without changing client strictness semantics."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema,
            strict=self.strict,
        )


class AnthropicOutputFormatModel(BaseModel):
    """Anthropic structured-output JSON Schema format."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["json_schema"]
    schema_definition: dict[str, object] = Field(alias="schema")


class AnthropicOutputConfigModel(BaseModel):
    """Anthropic structured-output configuration wrapper."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: AnthropicOutputFormatModel


class AnthropicToolChoiceModel(BaseModel):
    """The only tool-choice mode with safe cross-provider semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["auto"]
    disable_parallel_tool_use: bool = True


class AnthropicMetadataModel(BaseModel):
    """Bounded non-authoritative client metadata accepted for compatibility."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str | None = Field(default=None, max_length=256)


class AnthropicMessagesRequestModel(BaseModel):
    """Bounded Messages subset required by Claude-style agent loops."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1, max_length=256)
    max_tokens: int = Field(gt=0)
    messages: tuple[AnthropicMessageModel, ...] = Field(min_length=1)
    system: str | tuple[AnthropicTextBlockModel, ...] | None = None
    stream: bool = False
    tools: tuple[AnthropicToolModel, ...] = ()
    tool_choice: AnthropicToolChoiceModel | None = None
    output_config: AnthropicOutputConfigModel | None = None
    metadata: AnthropicMetadataModel | None = None

    @model_validator(mode="after")
    def _validate(self) -> "AnthropicMessagesRequestModel":
        if self.tool_choice is not None and not self.tools:
            raise ValueError("tool_choice requires tools")
        return self

    def to_generation_payload(
        self,
        *,
        workload: str,
    ) -> ProtocolGenerationPayload:
        """Translate the request into the one governed coordinator payload."""
        messages: list[Message] = []
        if isinstance(self.system, str):
            messages.append(
                Message(
                    role=MessageRole.SYSTEM,
                    content="",
                    blocks=(TextBlock(self.system),),
                )
            )
        elif self.system:
            messages.append(
                Message(
                    role=MessageRole.SYSTEM,
                    content="",
                    blocks=tuple(TextBlock(block.text) for block in self.system),
                )
            )
        messages.extend(message.to_contract() for message in self.messages)
        structured_output = None
        if self.output_config is not None:
            structured_output = StructuredOutputSchema(
                name="response",
                schema=self.output_config.format.schema_definition,
            )
        parallel = bool(
            self.tool_choice is not None and not self.tool_choice.disable_parallel_tool_use
        )
        return build_protocol_payload(
            request_id=uuid4(),
            workload=workload,
            messages=tuple(messages),
            max_output_tokens=self.max_tokens,
            tools=tuple(tool.to_contract() for tool in self.tools),
            structured_output=structured_output,
            parallel_tool_calling=parallel,
            client_protocol=ClientProtocol.ANTHROPIC_MESSAGES,
        )


def attach_anthropic_messages_route(app: FastAPI, coordinator: GenerateCoordinator) -> None:
    """Attach ``POST /v1/messages`` without introducing a second execution path."""

    @app.post(ANTHROPIC_MESSAGES_PATH, include_in_schema=False)
    async def messages(
        payload: AnthropicMessagesRequestModel,
        authorization: Annotated[str | None, Header()] = None,
        x_api_key: Annotated[str | None, Header(alias="x-api-key")] = None,
        gateway_api_key: Annotated[str | None, Header(alias="X-Gateway-API-Key")] = None,
        gateway_workload: Annotated[str | None, Header(alias="X-Gateway-Workload")] = None,
        anthropic_version: Annotated[str | None, Header(alias="anthropic-version")] = None,
    ) -> Response:
        if anthropic_version is not None and anthropic_version != "2023-06-01":
            return _anthropic_error(400, "unsupported_anthropic_version")
        try:
            credential = resolve_protocol_credential(
                authorization=authorization,
                x_api_key=x_api_key,
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
            return _anthropic_error(exc.status_code, safe_http_error_code(exc))
        except ValueError:
            return _anthropic_error(422, "invalid_request")

        response_id = f"msg_{translated.request_id.hex}"
        headers = {
            "Cache-Control": "no-store",
            "request-id": str(translated.request_id),
            "X-Accel-Buffering": "no",
            **safe_provenance_headers(prepared.decision.routing),
        }
        if payload.stream:
            return StreamingResponse(
                _anthropic_stream(
                    coordinator,
                    prepared,
                    response_id=response_id,
                    model_alias=payload.model,
                ),
                media_type="text/event-stream",
                headers=headers,
            )
        body = await _anthropic_aggregate(
            coordinator,
            prepared,
            response_id=response_id,
            model_alias=payload.model,
        )
        if isinstance(body, JSONResponse):
            body.headers.update(headers)
            return body
        return JSONResponse(content=body, headers=headers)


async def _anthropic_aggregate(
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
    finish_reason = "end_turn"
    async for event in coordinator.stream(prepared):
        if event.event_type is StreamEventType.CONTENT_DELTA and event.delta is not None:
            text.append(event.delta)
        elif (
            event.event_type is StreamEventType.TOOL_CALL_COMPLETED and event.tool_call is not None
        ):
            calls.append(event.tool_call)
        elif event.event_type is StreamEventType.USAGE_COMPLETED and event.usage is not None:
            input_tokens = event.usage.input_tokens
            output_tokens = event.usage.output_tokens
        elif event.event_type is StreamEventType.RESPONSE_COMPLETED:
            finish_reason = _anthropic_stop_reason(event.finish_reason, calls=bool(calls))
        elif event.event_type is StreamEventType.RESPONSE_FAILED:
            code = event.error.code if event.error is not None else "gateway_stream_failed"
            return _anthropic_error(502, code)
    content: list[dict[str, object]] = []
    if text:
        content.append({"type": "text", "text": "".join(text)})
    content.extend(
        {
            "type": "tool_use",
            "id": call.call_id,
            "name": call.name,
            "input": dict(call.arguments),
        }
        for call in calls
    )
    return {
        "id": response_id,
        "type": "message",
        "role": "assistant",
        "content": content,
        "model": model_alias,
        "stop_reason": finish_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


async def _anthropic_stream(
    coordinator: GenerateCoordinator,
    prepared: PreparedStreamingExecution,
    *,
    response_id: str,
    model_alias: str,
) -> AsyncGenerator[str]:
    index = 0
    open_text_index: int | None = None
    tool_indexes: dict[str, int] = {}
    output_tokens = 0
    calls_seen = False
    started = False
    async for event in coordinator.stream(prepared):
        if event.event_type is StreamEventType.RESPONSE_STARTED:
            started = True
            yield _anthropic_sse(
                "message_start",
                {
                    "type": "message_start",
                    "message": {
                        "id": response_id,
                        "type": "message",
                        "role": "assistant",
                        "content": [],
                        "model": model_alias,
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {"input_tokens": 0, "output_tokens": 0},
                    },
                },
            )
        elif event.event_type is StreamEventType.CONTENT_DELTA and event.delta is not None:
            if open_text_index is None:
                open_text_index = index
                index += 1
                yield _anthropic_sse(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": open_text_index,
                        "content_block": {"type": "text", "text": ""},
                    },
                )
            yield _anthropic_sse(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": open_text_index,
                    "delta": {"type": "text_delta", "text": event.delta},
                },
            )
        elif event.event_type is StreamEventType.TOOL_CALL_STARTED:
            calls_seen = True
            if open_text_index is not None:
                yield _anthropic_block_stop(open_text_index)
                open_text_index = None
            if event.tool_call_id is not None and event.tool_name is not None:
                tool_indexes[event.tool_call_id] = index
                yield _anthropic_sse(
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": index,
                        "content_block": {
                            "type": "tool_use",
                            "id": event.tool_call_id,
                            "name": event.tool_name,
                            "input": {},
                        },
                    },
                )
                index += 1
        elif event.event_type is StreamEventType.TOOL_CALL_ARGUMENTS_DELTA:
            if event.tool_call_id is not None and event.delta is not None:
                yield _anthropic_sse(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": tool_indexes[event.tool_call_id],
                        "delta": {"type": "input_json_delta", "partial_json": event.delta},
                    },
                )
        elif event.event_type is StreamEventType.TOOL_CALL_COMPLETED:
            if event.tool_call is not None:
                yield _anthropic_block_stop(tool_indexes[event.tool_call.call_id])
        elif event.event_type is StreamEventType.USAGE_COMPLETED and event.usage is not None:
            output_tokens = event.usage.output_tokens
        elif event.event_type is StreamEventType.RESPONSE_COMPLETED:
            if open_text_index is not None:
                yield _anthropic_block_stop(open_text_index)
                open_text_index = None
            yield _anthropic_sse(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {
                        "stop_reason": _anthropic_stop_reason(
                            event.finish_reason,
                            calls=calls_seen,
                        ),
                        "stop_sequence": None,
                    },
                    "usage": {"output_tokens": output_tokens},
                },
            )
            yield _anthropic_sse("message_stop", {"type": "message_stop"})
        elif event.event_type is StreamEventType.RESPONSE_FAILED:
            code = event.error.code if event.error is not None else "gateway_stream_failed"
            yield _anthropic_sse(
                "error",
                {
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": f"governed gateway failure: {code}",
                    },
                },
            )
    if not started:
        return


def _anthropic_sse(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def _anthropic_block_stop(index: int) -> str:
    return _anthropic_sse(
        "content_block_stop",
        {"type": "content_block_stop", "index": index},
    )


def _anthropic_stop_reason(value: str | None, *, calls: bool) -> str:
    if calls:
        return "tool_use"
    if value in {"max_tokens", "length"}:
        return "max_tokens"
    return "end_turn"


def _anthropic_error(status_code: int, code: str) -> JSONResponse:
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
            "type": "error",
            "error": {
                "type": error_type,
                "message": f"governed gateway rejected the request: {code}",
            },
        },
    )
