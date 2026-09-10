"""OpenAI-compatible ingress: `POST /v1/chat/completions`.

Adoption friction, not a second execution path. This route translates an
OpenAI-shaped request into the existing `GenerateRequestModel` and hands it to the same
`GenerateCoordinator` that serves `/v1/generate`, so authentication, PDP authorization,
deterministic ranking, retry/fallback and evidence are byte-for-byte the governed path.
Nothing here can authorize anything.

Two translation decisions carry the governance weight:

`model` is the **workload**, never a provider model. Shape validation catches the
obvious confusions — `openai/gpt-4` and any undotted or uppercase name are refused
outright — but it is deliberately not the protection that matters. A dotted model name
such as `gpt-5.6-luna` is shaped exactly like a workload and passes, and it must:
what refuses it is authorization, not syntax. An unregistered workload is absent from
every client-auth binding's `allowed_workloads` and from the Policy Router's decision, so
it fails closed there. Relying on the pattern alone would be a protection that only looks
like one.

`risk_level` and `data_classification` have no OpenAI equivalent, so they come from the
deployment-owned client-auth binding rather than from the caller. The request presents
the lowest possible pair and the binding's minimums raise it; a caller can never lower
its own classification through this surface. Callers that must declare a higher
sensitivity per request use `/v1/generate`, which requires both fields explicitly.
"""

import json
import re
import time
from collections.abc import AsyncGenerator, Mapping, Sequence
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayStreamEvent,
    MessageRole,
    RiskLevel,
    StreamEventType,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .stream_generate import (
    GenerateCoordinator,
    GenerateMessageModel,
    GenerateRequestModel,
    PreparedStreamingExecution,
    prepare_generation,
)

OPENAI_CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
DEFAULT_MAX_OUTPUT_TOKENS = 2000
_OBJECT_COMPLETION = "chat.completion"
_OBJECT_CHUNK = "chat.completion.chunk"
_WORKLOAD_PATTERN = r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
# Rough parity with the estimate a native caller is asked to supply; four characters per
# token is the usual English approximation and this value only feeds PDP ceilings.
_CHARS_PER_TOKEN = 4


class OpenAIChatMessageModel(BaseModel):
    """One OpenAI-shaped chat message with text content only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)

    def to_gateway_message(self) -> GenerateMessageModel:
        """Project onto the provider-neutral message the governed path already accepts."""
        return GenerateMessageModel(role=MessageRole(self.role), content=self.content)


class OpenAIChatCompletionRequestModel(BaseModel):
    """The bounded subset of the OpenAI chat-completions request this gateway accepts.

    Unknown fields are rejected rather than ignored. Sampling controls in particular
    (`temperature`, `top_p`, `seed`, `n`) are deployment-owned here: silently dropping
    them would let a caller believe it had influenced execution when it had not.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=3, max_length=128)
    messages: tuple[OpenAIChatMessageModel, ...] = Field(min_length=1)
    stream: bool = False
    max_tokens: int | None = Field(default=None, gt=0)
    max_completion_tokens: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _validate(self) -> "OpenAIChatCompletionRequestModel":
        """Reject a provider model in the workload field and ambiguous token budgets."""
        if re.fullmatch(_WORKLOAD_PATTERN, self.model) is None:
            raise ValueError(
                "model must be a governed workload identifier such as 'rag.answer'. "
                "This gateway selects the provider and model itself; whatever is sent "
                "here is interpreted as a workload and must be authorized as one."
            )
        if self.max_tokens is not None and self.max_completion_tokens is not None:
            raise ValueError("supply at most one of max_tokens or max_completion_tokens")
        return self

    @property
    def output_token_budget(self) -> int:
        """Return the caller's output budget, or the documented governed default."""
        return self.max_tokens or self.max_completion_tokens or DEFAULT_MAX_OUTPUT_TOKENS

    def to_generate_request(self, *, request_id: UUID) -> GenerateRequestModel:
        """Translate onto the native contract without widening anything it validates."""
        return GenerateRequestModel(
            request_id=request_id,
            workload=self.model,
            # The client-auth binding's minimums raise these; the caller cannot lower them.
            risk_level=RiskLevel.LOW,
            data_classification=DataClassification.PUBLIC,
            messages=tuple(message.to_gateway_message() for message in self.messages),
            context_tokens_estimated=_estimate_context_tokens(self.messages),
            max_output_tokens=self.output_token_budget,
        )


def _estimate_context_tokens(messages: Sequence[OpenAIChatMessageModel]) -> int:
    return sum(len(message.content) for message in messages) // _CHARS_PER_TOKEN


def _bearer_credential(
    authorization: str | None,
    gateway_api_key: str | None,
) -> str:
    """Accept the SDK's Authorization header or the gateway's own header, never both."""
    bearer: str | None = None
    if authorization is not None:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() != "bearer" or not value.strip():
            raise _openai_error(
                status_code=401,
                message="Authorization must use the Bearer scheme.",
                error_type="invalid_request_error",
                code="invalid_gateway_credential",
            )
        bearer = value.strip()
    if bearer is not None and gateway_api_key is not None and bearer != gateway_api_key:
        raise _openai_error(
            status_code=400,
            message="Conflicting gateway credentials were presented.",
            error_type="invalid_request_error",
            code="ambiguous_gateway_credential",
        )
    credential = bearer or gateway_api_key
    if credential is None:
        raise _openai_error(
            status_code=401,
            message="A gateway credential is required.",
            error_type="invalid_request_error",
            code="invalid_gateway_credential",
        )
    return credential


def _openai_error(
    *,
    status_code: int,
    message: str,
    error_type: str,
    code: str,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"message": message, "type": error_type, "code": code}},
    )


def _gateway_evidence(event: GatewayStreamEvent) -> dict[str, object]:
    """Expose terminal execution evidence without disturbing OpenAI-shaped parsing."""
    evidence: dict[str, object] = {}
    if event.routing is not None:
        evidence["routing_decision_id"] = event.routing.routing_decision_id
        evidence["model_group"] = event.routing.authorized_model_group
        evidence["ranking_policy_version"] = event.routing.ranking_policy_version
    if event.execution is not None:
        evidence["provider"] = event.execution.provider
        evidence["model"] = event.execution.model
        evidence["deployment"] = event.execution.deployment
        evidence["attempt_number"] = event.execution.attempt_number
        evidence["fallback_index"] = event.execution.fallback_index
        if event.execution.trace_id is not None:
            evidence["trace_id"] = event.execution.trace_id
    return evidence


def _completion_envelope(
    *,
    completion_id: str,
    created: int,
    workload: str,
    object_type: str,
) -> dict[str, object]:
    return {
        "id": completion_id,
        "object": object_type,
        "created": created,
        # The workload is what the caller asked for; the deployment that served it is
        # reported as evidence under x_gateway rather than substituted here.
        "model": workload,
    }


def attach_openai_compatible_route(
    app: FastAPI,
    coordinator: GenerateCoordinator,
) -> None:
    """Attach the OpenAI-compatible ingress onto the already-governed generate path."""

    @app.post(OPENAI_CHAT_COMPLETIONS_PATH, include_in_schema=False)
    async def chat_completions(
        request: Request,
        payload: OpenAIChatCompletionRequestModel,
        authorization: Annotated[str | None, Header()] = None,
        gateway_api_key: Annotated[str | None, Header(alias="X-Gateway-API-Key")] = None,
    ) -> Response:
        del request
        credential = _bearer_credential(authorization, gateway_api_key)
        request_id = uuid4()
        prepared = await prepare_generation(
            coordinator,
            api_key=credential,
            payload=payload.to_generate_request(request_id=request_id),
        )
        completion_id = f"chatcmpl-{request_id.hex}"
        created = int(time.time())

        if payload.stream:
            return StreamingResponse(
                _chunk_stream(
                    coordinator,
                    prepared,
                    completion_id=completion_id,
                    created=created,
                    workload=payload.model,
                ),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
            )

        body = await _aggregate_completion(
            coordinator,
            prepared,
            completion_id=completion_id,
            created=created,
            workload=payload.model,
        )
        return JSONResponse(content=body, headers={"Cache-Control": "no-store"})


async def _aggregate_completion(
    coordinator: GenerateCoordinator,
    prepared: PreparedStreamingExecution,
    *,
    completion_id: str,
    created: int,
    workload: str,
) -> dict[str, object]:
    """Collapse the governed stream into one non-streaming OpenAI-shaped completion."""
    content: list[str] = []
    finish_reason = "stop"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    evidence: dict[str, object] = {}

    async for event in coordinator.stream(prepared):
        if event.event_type is StreamEventType.CONTENT_DELTA and event.delta is not None:
            content.append(event.delta)
        elif event.event_type is StreamEventType.USAGE_COMPLETED and event.usage is not None:
            usage = {
                "prompt_tokens": event.usage.input_tokens,
                "completion_tokens": event.usage.output_tokens,
                "total_tokens": event.usage.input_tokens + event.usage.output_tokens,
            }
        elif event.event_type is StreamEventType.RESPONSE_COMPLETED:
            finish_reason = event.finish_reason or "stop"
            evidence = _gateway_evidence(event)
        elif event.event_type is StreamEventType.RESPONSE_FAILED:
            raise _openai_error(
                status_code=502,
                message="The governed gateway could not complete this request.",
                error_type="api_error",
                code=event.error.code if event.error is not None else "gateway_stream_failed",
            )
        elif event.event_type is StreamEventType.RESPONSE_STARTED:
            evidence = _gateway_evidence(event)

    envelope = _completion_envelope(
        completion_id=completion_id,
        created=created,
        workload=workload,
        object_type=_OBJECT_COMPLETION,
    )
    envelope["choices"] = [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "".join(content)},
            "finish_reason": finish_reason,
        }
    ]
    envelope["usage"] = usage
    envelope["x_gateway"] = evidence
    return envelope


async def _chunk_stream(
    coordinator: GenerateCoordinator,
    prepared: PreparedStreamingExecution,
    *,
    completion_id: str,
    created: int,
    workload: str,
) -> AsyncGenerator[str]:
    """Emit OpenAI-shaped chunks, terminating with the sentinel SDKs expect."""
    async for event in coordinator.stream(prepared):
        chunk = _chunk_for(
            event,
            completion_id=completion_id,
            created=created,
            workload=workload,
        )
        if chunk is not None:
            yield f"data: {json.dumps(chunk, separators=(',', ':'))}\n\n"
    yield "data: [DONE]\n\n"


def _chunk_for(
    event: GatewayStreamEvent,
    *,
    completion_id: str,
    created: int,
    workload: str,
) -> Mapping[str, object] | None:
    envelope = _completion_envelope(
        completion_id=completion_id,
        created=created,
        workload=workload,
        object_type=_OBJECT_CHUNK,
    )
    if event.event_type is StreamEventType.CONTENT_DELTA and event.delta is not None:
        envelope["choices"] = [
            {"index": 0, "delta": {"content": event.delta}, "finish_reason": None}
        ]
        return envelope
    if event.event_type is StreamEventType.RESPONSE_COMPLETED:
        envelope["choices"] = [
            {"index": 0, "delta": {}, "finish_reason": event.finish_reason or "stop"}
        ]
        envelope["x_gateway"] = _gateway_evidence(event)
        return envelope
    if event.event_type is StreamEventType.USAGE_COMPLETED and event.usage is not None:
        envelope["choices"] = []
        envelope["usage"] = {
            "prompt_tokens": event.usage.input_tokens,
            "completion_tokens": event.usage.output_tokens,
            "total_tokens": event.usage.input_tokens + event.usage.output_tokens,
        }
        return envelope
    if event.event_type is StreamEventType.RESPONSE_FAILED:
        # The stream is already committed with HTTP 200, so a failure is reported in
        # band rather than as a status code the caller can no longer receive.
        envelope["choices"] = [{"index": 0, "delta": {}, "finish_reason": "error"}]
        envelope["x_gateway"] = {
            "error": event.error.code if event.error is not None else "gateway_stream_failed",
            "partial": event.partial,
        }
        return envelope
    return None
