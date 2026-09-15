"""Regression tests for Claude Code ASGI request replay."""

import asyncio
import json
import unittest

from governed_llm_gateway_api.claude_code_compat import (
    ClaudeCodeCompatibilityMiddleware,
)
from starlette.types import Message, Receive, Scope, Send


class ClaudeCodeCompatibilityMiddlewareTests(unittest.TestCase):
    def test_replayed_body_then_delegates_to_original_receive(self) -> None:
        downstream_messages: list[Message] = []
        sent_messages: list[Message] = []

        async def downstream(
            scope: Scope,
            receive: Receive,
            send: Send,
        ) -> None:
            del scope
            downstream_messages.append(await receive())
            downstream_messages.append(await receive())

            await send(
                {
                    "type": "http.response.start",
                    "status": 204,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"",
                    "more_body": False,
                }
            )

        request_body = json.dumps(
            {
                "model": "governed-agent",
                "max_tokens": 64,
                "stream": True,
                "messages": [{"role": "user", "content": "hello"}],
            }
        ).encode("utf-8")

        upstream_messages: list[Message] = [
            {
                "type": "http.request",
                "body": request_body,
                "more_body": False,
            },
            {"type": "http.disconnect"},
        ]
        upstream_iter = iter(upstream_messages)

        async def upstream_receive() -> Message:
            return next(upstream_iter)

        async def capture_send(message: Message) -> None:
            sent_messages.append(message)

        scope: Scope = {
            "type": "http",
            "method": "POST",
            "path": "/v1/messages",
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(request_body)).encode("ascii")),
            ],
        }

        middleware = ClaudeCodeCompatibilityMiddleware(downstream)

        asyncio.run(
            middleware(
                scope,
                upstream_receive,
                capture_send,
            )
        )

        self.assertEqual(len(downstream_messages), 2)

        replayed = downstream_messages[0]
        self.assertEqual(replayed["type"], "http.request")
        self.assertFalse(replayed["more_body"])
        self.assertEqual(json.loads(replayed["body"]), json.loads(request_body))

        self.assertEqual(
            downstream_messages[1],
            {"type": "http.disconnect"},
        )
        self.assertEqual(sent_messages[0]["type"], "http.response.start")


if __name__ == "__main__":
    unittest.main()
