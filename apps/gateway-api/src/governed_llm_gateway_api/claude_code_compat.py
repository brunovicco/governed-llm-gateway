"""Bounded compatibility shim for real Claude Code Messages requests.

Claude Code evolves its provider-shaped request surface independently of the Gateway's
canonical execution contract. This module accepts only reviewed, non-authoritative
compatibility controls observed on the wire and removes them before the strict
Anthropic ingress model parses the request. Unknown top-level fields remain untouched
so the downstream ``extra='forbid'`` boundary continues to fail closed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .generation_security import MAX_GENERATION_REQUEST_BODY_BYTES
from .protocol_error import boundary_error_response

_MESSAGES_PATH = "/v1/messages"
_MAX_CONTEXT_MANAGEMENT_BYTES = 16 * 1024
_ALLOWED_THINKING_TYPES = frozenset({"adaptive", "disabled", "enabled"})
_ALLOWED_EFFORT = frozenset({"low", "medium", "high", "xhigh", "max"})
_DEFAULT_TOOL_DESCRIPTION = "Claude Code tool"


class ClaudeCodeCompatibilityError(ValueError):
    """Raised when a known Claude Code compatibility field is malformed."""


class ClaudeCodeCompatibilityMiddleware:
    """Normalize reviewed Claude Code wire controls before strict protocol parsing."""

    def __init__(self, app: ASGIApp) -> None:
        """Bind the downstream ASGI application."""
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Normalize reviewed Messages fields and replay the bounded JSON body downstream."""
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != _MESSAGES_PATH
        ):
            await self._app(scope, receive, send)
            return

        body = await _read_body(receive)
        if body is None:
            response = boundary_error_response(
                _MESSAGES_PATH,
                status_code=413,
                code="generation_request_too_large",
            )
            await response(scope, receive, send)
            return

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            await self._app(scope, _replay(body, receive), send)
            return

        if not isinstance(payload, dict):
            await self._app(scope, _replay(body, receive), send)
            return

        try:
            normalized = normalize_claude_code_payload(payload)
        except ClaudeCodeCompatibilityError:
            response = boundary_error_response(
                _MESSAGES_PATH,
                status_code=422,
                code="invalid_request",
            )
            await response(scope, receive, send)
            return

        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        downstream_scope = dict(scope)
        downstream_scope["headers"] = _replace_content_length(
            tuple(scope.get("headers", ())),
            len(encoded),
        )
        await self._app(downstream_scope, _replay(encoded, receive), send)


def normalize_claude_code_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Return the strict Anthropic subset after bounded compatibility validation.

    The removed values are client execution hints only. They never influence workload,
    authorization, model group, registry eligibility, ranking, or provider identity.
    """
    normalized = dict(payload)
    _normalize_thinking(normalized)
    _normalize_output_config(normalized)
    _normalize_context_management(normalized)
    _normalize_tools(normalized)
    return normalized


def _normalize_thinking(payload: dict[str, object]) -> None:
    value = payload.get("thinking")
    if value is None:
        return
    mapping = _mapping(value, "thinking")
    thinking_type = mapping.get("type")
    if not isinstance(thinking_type, str) or thinking_type not in _ALLOWED_THINKING_TYPES:
        raise ClaudeCodeCompatibilityError("unsupported thinking type")
    allowed = {"type"}
    if thinking_type == "enabled":
        allowed.add("budget_tokens")
        budget = mapping.get("budget_tokens")
        if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
            raise ClaudeCodeCompatibilityError("enabled thinking requires positive budget_tokens")
    if set(mapping) - allowed:
        raise ClaudeCodeCompatibilityError("unknown thinking fields")
    payload.pop("thinking", None)


def _normalize_output_config(payload: dict[str, object]) -> None:
    value = payload.get("output_config")
    if value is None:
        return
    mapping = dict(_mapping(value, "output_config"))
    effort = mapping.pop("effort", None)
    if effort is not None and (not isinstance(effort, str) or effort not in _ALLOWED_EFFORT):
        raise ClaudeCodeCompatibilityError("unsupported output effort")
    # Preserve ``format`` for the strict Anthropic ingress, where it becomes canonical
    # structured-output policy. Any other output_config field remains fail-closed.
    if mapping:
        payload["output_config"] = mapping
    else:
        payload.pop("output_config", None)


def _normalize_context_management(payload: dict[str, object]) -> None:
    value = payload.get("context_management")
    if value is None:
        return
    mapping = _mapping(value, "context_management")
    encoded = json.dumps(
        mapping,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > _MAX_CONTEXT_MANAGEMENT_BYTES:
        raise ClaudeCodeCompatibilityError("context_management is too large")
    # The Gateway does not implement provider-owned context mutation. Treat this as
    # compatibility metadata and discard it before canonical request construction.
    payload.pop("context_management", None)


def _normalize_tools(payload: dict[str, object]) -> None:
    tools = payload.get("tools")
    if tools is None:
        return
    if not isinstance(tools, list):
        raise ClaudeCodeCompatibilityError("tools must be an array")
    normalized: list[object] = []
    for item in tools:
        if not isinstance(item, dict):
            normalized.append(item)
            continue
        tool = dict(item)
        # Claude Code built-in descriptions can be omitted, blank, or padded with
        # boundary whitespace. Normalize only the string representation needed by the
        # canonical contract; non-string values remain for strict ingress validation.
        description = tool.get("description")
        if isinstance(description, str):
            normalized_description = description.strip()
            tool["description"] = normalized_description or _DEFAULT_TOOL_DESCRIPTION
        elif "description" not in tool:
            tool["description"] = _DEFAULT_TOOL_DESCRIPTION
        normalized.append(tool)
    payload["tools"] = normalized


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ClaudeCodeCompatibilityError(f"{field} must be an object")
    for key in value:
        if not isinstance(key, str):
            raise ClaudeCodeCompatibilityError(f"{field} keys must be strings")
    return value


async def _read_body(receive: Receive) -> bytes | None:
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            continue
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > MAX_GENERATION_REQUEST_BODY_BYTES:
            return None
        chunks.append(chunk)
        if not message.get("more_body", False):
            return b"".join(chunks)


def _replay(body: bytes, upstream_receive: Receive) -> Receive:
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if sent:
            return await upstream_receive()
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


def _replace_content_length(
    headers: tuple[tuple[bytes, bytes], ...],
    body_length: int,
) -> list[tuple[bytes, bytes]]:
    filtered = [(name, value) for name, value in headers if name.lower() != b"content-length"]
    filtered.append((b"content-length", str(body_length).encode("ascii")))
    return filtered
