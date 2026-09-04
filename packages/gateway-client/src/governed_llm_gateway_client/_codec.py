"""Bounded codec for the gateway's provider-neutral SSE protocol."""

import json
from collections.abc import AsyncIterator
from decimal import Decimal, InvalidOperation
from typing import cast
from uuid import UUID

import httpx
from governed_llm_gateway_contracts import (
    CandidateRejection,
    GatewayError,
    GatewayStreamEvent,
    PolicyProvenance,
    RejectionReason,
    RoutingProvenance,
    StreamEventType,
    ToolCall,
    Usage,
)

from .errors import GatewayProtocolError

_EVENT_FIELDS = frozenset(
    {
        "event_type",
        "request_id",
        "sequence_number",
        "routing",
        "delta",
        "tool_call_id",
        "tool_name",
        "tool_call",
        "usage",
        "finish_reason",
        "error",
        "partial",
    }
)
_ROUTING_FIELDS = frozenset(
    {
        "routing_decision_id",
        "policy",
        "authorized_model_group",
        "model_registry_digest",
        "ranking_policy_version",
        "ranking_policy_digest",
        "score_snapshot_id",
        "benchmark_snapshot_id",
        "score_provenance_mode",
        "manual_override_id",
        "provider",
        "model",
        "deployment",
        "rejected_candidates",
        "fallback_sequence",
    }
)
_POLICY_FIELDS = frozenset({"decision_id", "policy_id", "policy_version", "policy_digest"})
_REJECTION_FIELDS = frozenset({"deployment", "reason", "detail"})
_TOOL_CALL_FIELDS = frozenset({"call_id", "name", "arguments"})
_USAGE_FIELDS = frozenset({"input_tokens", "output_tokens", "total_cost_usd"})
_ERROR_FIELDS = frozenset({"code", "message", "retryable"})
_TERMINAL_EVENTS = frozenset(
    {StreamEventType.RESPONSE_COMPLETED, StreamEventType.RESPONSE_FAILED}
)


class _DuplicateJsonKeyError(ValueError):
    pass


async def _iter_sse_events(
    response: httpx.Response,
    *,
    max_event_bytes: int,
) -> AsyncIterator[GatewayStreamEvent]:
    expected_sequence = 1
    terminal = False
    async for frame in _iter_sse_frames(response, max_event_bytes=max_event_bytes):
        if terminal:
            raise GatewayProtocolError("gateway emitted an event after the terminal SSE event")
        event_name, event_id, payload = _parse_sse_frame(frame)
        event = _decode_event(payload)
        if event.event_type.value != event_name:
            raise GatewayProtocolError("SSE event name does not match event payload")
        if event.sequence_number != event_id:
            raise GatewayProtocolError("SSE id does not match event sequence_number")
        if event.sequence_number != expected_sequence:
            raise GatewayProtocolError("gateway SSE sequence is not contiguous")
        expected_sequence += 1
        if event.event_type in _TERMINAL_EVENTS:
            terminal = True
        yield event
    if not terminal:
        raise GatewayProtocolError("gateway SSE stream ended before a terminal event")


async def _iter_sse_frames(
    response: httpx.Response,
    *,
    max_event_bytes: int,
) -> AsyncIterator[bytes]:
    if max_event_bytes <= 0:
        raise GatewayProtocolError("max SSE event size must be positive")
    buffer = bytearray()
    async for chunk in response.aiter_bytes():
        buffer.extend(chunk)
        while True:
            extracted = _extract_frame(buffer)
            if extracted is None:
                break
            if len(extracted) > max_event_bytes:
                raise GatewayProtocolError("gateway SSE event exceeds configured size limit")
            if extracted.strip():
                yield extracted
        if len(buffer) > max_event_bytes:
            raise GatewayProtocolError("gateway SSE event exceeds configured size limit")
    if buffer.strip(b"\r\n\t "):
        raise GatewayProtocolError("gateway SSE stream ended with an unterminated event")


def _extract_frame(buffer: bytearray) -> bytes | None:
    delimiters = (b"\r\n\r\n", b"\n\n", b"\r\r")
    matches = [(index, delimiter) for delimiter in delimiters if (index := buffer.find(delimiter)) >= 0]
    if not matches:
        return None
    index, delimiter = min(matches, key=lambda item: item[0])
    frame = bytes(buffer[:index])
    del buffer[: index + len(delimiter)]
    return frame


def _parse_sse_frame(frame: bytes) -> tuple[str, int, dict[str, object]]:
    try:
        text = frame.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise GatewayProtocolError("gateway SSE event is not valid UTF-8") from exc

    event_name: str | None = None
    event_id: str | None = None
    data_lines: list[str] = []
    for line in text.splitlines():
        if not line or line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            if event_name is not None:
                raise GatewayProtocolError("gateway SSE event contains duplicate event fields")
            event_name = value
        elif field == "id":
            if event_id is not None:
                raise GatewayProtocolError("gateway SSE event contains duplicate id fields")
            event_id = value
        elif field == "data":
            data_lines.append(value)
        else:
            raise GatewayProtocolError(f"unsupported gateway SSE field: {field}")

    if event_name is None or not event_name:
        raise GatewayProtocolError("gateway SSE event is missing event name")
    if event_id is None or not event_id:
        raise GatewayProtocolError("gateway SSE event is missing id")
    if not data_lines:
        raise GatewayProtocolError("gateway SSE event is missing data")
    try:
        parsed_id = int(event_id)
    except ValueError as exc:
        raise GatewayProtocolError("gateway SSE id is not an integer") from exc
    if parsed_id <= 0:
        raise GatewayProtocolError("gateway SSE id must be positive")

    payload = _load_json_object("\n".join(data_lines))
    return event_name, parsed_id, payload


def _load_json_object(text: str) -> dict[str, object]:
    try:
        value = cast(object, json.loads(text, object_pairs_hook=_unique_json_object))
    except (json.JSONDecodeError, _DuplicateJsonKeyError) as exc:
        raise GatewayProtocolError("gateway SSE data is not valid strict JSON") from exc
    return _as_object(value, "gateway SSE data")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(key)
        result[key] = value
    return result


def _decode_event(payload: dict[str, object]) -> GatewayStreamEvent:
    _check_fields(payload, _EVENT_FIELDS, "gateway stream event")
    try:
        event_type = StreamEventType(_required_str(payload, "event_type"))
        request_id = UUID(_required_str(payload, "request_id"))
        sequence_number = _required_int(payload, "sequence_number")
        routing_value = payload.get("routing")
        tool_call_value = payload.get("tool_call")
        usage_value = payload.get("usage")
        error_value = payload.get("error")
        return GatewayStreamEvent(
            event_type=event_type,
            request_id=request_id,
            sequence_number=sequence_number,
            routing=_decode_routing(_as_object(routing_value, "routing"))
            if routing_value is not None
            else None,
            delta=_optional_str(payload, "delta"),
            tool_call_id=_optional_str(payload, "tool_call_id"),
            tool_name=_optional_str(payload, "tool_name"),
            tool_call=_decode_tool_call(_as_object(tool_call_value, "tool_call"))
            if tool_call_value is not None
            else None,
            usage=_decode_usage(_as_object(usage_value, "usage"))
            if usage_value is not None
            else None,
            finish_reason=_optional_str(payload, "finish_reason"),
            error=_decode_error(_as_object(error_value, "error"))
            if error_value is not None
            else None,
            partial=_optional_bool(payload, "partial", default=False),
        )
    except (ValueError, TypeError) as exc:
        raise GatewayProtocolError("gateway stream event violates the provider-neutral contract") from exc


def _decode_routing(payload: dict[str, object]) -> RoutingProvenance:
    _check_fields(payload, _ROUTING_FIELDS, "routing provenance")
    policy = _as_object(payload.get("policy"), "routing policy provenance")
    _check_fields(policy, _POLICY_FIELDS, "policy provenance")

    rejected_value = payload.get("rejected_candidates", [])
    rejected_items = _as_list(rejected_value, "rejected_candidates")
    fallback_items = _as_list(payload.get("fallback_sequence", []), "fallback_sequence")

    return RoutingProvenance(
        routing_decision_id=_required_str(payload, "routing_decision_id"),
        policy=PolicyProvenance(
            decision_id=_required_str(policy, "decision_id"),
            policy_id=_required_str(policy, "policy_id"),
            policy_version=_required_str(policy, "policy_version"),
            policy_digest=_required_str(policy, "policy_digest"),
        ),
        authorized_model_group=_required_str(payload, "authorized_model_group"),
        model_registry_digest=_required_str(payload, "model_registry_digest"),
        ranking_policy_version=_required_str(payload, "ranking_policy_version"),
        ranking_policy_digest=_optional_str(payload, "ranking_policy_digest"),
        score_snapshot_id=_optional_str(payload, "score_snapshot_id"),
        benchmark_snapshot_id=_optional_str(payload, "benchmark_snapshot_id"),
        score_provenance_mode=_optional_str(payload, "score_provenance_mode"),
        manual_override_id=_optional_str(payload, "manual_override_id"),
        provider=_optional_str(payload, "provider"),
        model=_optional_str(payload, "model"),
        deployment=_optional_str(payload, "deployment"),
        rejected_candidates=tuple(
            _decode_rejection(_as_object(item, "rejected candidate")) for item in rejected_items
        ),
        fallback_sequence=tuple(_string_value(item, "fallback deployment") for item in fallback_items),
    )


def _decode_rejection(payload: dict[str, object]) -> CandidateRejection:
    _check_fields(payload, _REJECTION_FIELDS, "candidate rejection")
    return CandidateRejection(
        deployment=_required_str(payload, "deployment"),
        reason=RejectionReason(_required_str(payload, "reason")),
        detail=_optional_str(payload, "detail"),
    )


def _decode_tool_call(payload: dict[str, object]) -> ToolCall:
    _check_fields(payload, _TOOL_CALL_FIELDS, "tool call")
    return ToolCall(
        call_id=_required_str(payload, "call_id"),
        name=_required_str(payload, "name"),
        arguments=_as_object(payload.get("arguments"), "tool call arguments"),
    )


def _decode_usage(payload: dict[str, object]) -> Usage:
    _check_fields(payload, _USAGE_FIELDS, "usage")
    cost_value = payload.get("total_cost_usd")
    cost: Decimal | None = None
    if cost_value is not None:
        if not isinstance(cost_value, str):
            raise GatewayProtocolError("usage total_cost_usd must be a decimal string")
        try:
            cost = Decimal(cost_value)
        except InvalidOperation as exc:
            raise GatewayProtocolError("usage total_cost_usd is not a valid decimal") from exc
    return Usage(
        input_tokens=_required_int(payload, "input_tokens"),
        output_tokens=_required_int(payload, "output_tokens"),
        total_cost_usd=cost,
    )


def _decode_error(payload: dict[str, object]) -> GatewayError:
    _check_fields(payload, _ERROR_FIELDS, "gateway error")
    retryable = payload.get("retryable")
    if not isinstance(retryable, bool):
        raise GatewayProtocolError("gateway error retryable must be boolean")
    return GatewayError(
        code=_required_str(payload, "code"),
        message=_required_str(payload, "message"),
        retryable=retryable,
    )


def _check_fields(payload: dict[str, object], allowed: frozenset[str], context: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise GatewayProtocolError(f"{context} contains unsupported fields: {sorted(unknown)!r}")


def _as_object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise GatewayProtocolError(f"{context} must be a JSON object")
    return cast(dict[str, object], value)


def _as_list(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise GatewayProtocolError(f"{context} must be a JSON array")
    return cast(list[object], value)


def _required_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise GatewayProtocolError(f"{key} must be a non-empty string")
    return value


def _optional_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise GatewayProtocolError(f"{key} must be a non-empty string when present")
    return value


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise GatewayProtocolError(f"{key} must be an integer")
    return value


def _optional_bool(payload: dict[str, object], key: str, *, default: bool) -> bool:
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise GatewayProtocolError(f"{key} must be boolean")
    return value


def _string_value(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise GatewayProtocolError(f"{context} must be a non-empty string")
    return value
