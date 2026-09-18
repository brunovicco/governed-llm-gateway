"""ASGI-owned delivery lifetime; no timeout leaks across an external generator yield."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import suppress
from functools import partial

from fastapi.responses import StreamingResponse
from governed_llm_gateway_core.application.execution_deadline import (
    ExecutionDeadline,
    ExecutionDeadlineExceeded,
)
from starlette.types import Send

TERMINAL_DELIVERY_GRACE_SECONDS = 1.0


class TerminalFailureFrame(str):
    """Trusted API-generated terminal failure framing, never new semantic output."""


class DeadlineStreamingResponse(StreamingResponse):
    """Own an explicitly closeable body and bound cooperative stalled delivery."""

    def __init__(
        self,
        content: AsyncGenerator[str],
        *,
        deadline: ExecutionDeadline | None,
        media_type: str,
        headers: dict[str, str],
    ) -> None:
        """Retain the preparation deadline and original body ownership."""
        super().__init__(content, media_type=media_type, headers=headers)
        self._body = content
        self._deadline = deadline

    async def stream_response(self, send: Send) -> None:
        """Bound ASGI consumption/delivery, including suspension after a yielded body chunk."""
        if self._deadline is None or not self._deadline.enabled:
            try:
                await super().stream_response(send)
            finally:
                await self._body.aclose()
            return
        timeout: asyncio.Timeout | None = None
        try:
            try:
                remaining = self._deadline.remaining_seconds()
            except ExecutionDeadlineExceeded:
                remaining = 0.0
            # This task owns the body iterator through all yields. The separate finite
            # grace can deliver only terminal failure/closure, never extend inference.
            timeout = asyncio.timeout((remaining or 0.0) + TERMINAL_DELIVERY_GRACE_SECONDS)
            async with timeout:
                await send(
                    {
                        "type": "http.response.start",
                        "status": self.status_code,
                        "headers": self.raw_headers,
                    }
                )
                async for chunk in self._body:
                    message = {
                        "type": "http.response.body",
                        "body": chunk.encode(self.charset),
                        "more_body": True,
                    }
                    if isinstance(chunk, TerminalFailureFrame):
                        await send(message)
                    else:
                        await self._deadline.run(partial(send, message))
                await send({"type": "http.response.body", "body": b"", "more_body": False})
        except ExecutionDeadlineExceeded:
            # A blocked/disconnected client may not receive any terminal frame.
            pass
        except TimeoutError:
            # Cooperative terminal delivery exhausted the independent finite grace.
            if timeout is None or not timeout.expired():
                raise
        finally:
            with suppress(Exception):
                async with asyncio.timeout(TERMINAL_DELIVERY_GRACE_SECONDS):
                    await self._body.aclose()
