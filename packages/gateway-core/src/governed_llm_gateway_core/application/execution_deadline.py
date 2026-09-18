"""One process-local execution budget, independent of policy selection latency."""

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

MAX_EXECUTION_TIMEOUT_MS = 86_400_000


class ExecutionDeadlineExceeded(RuntimeError):
    """Terminal local expiry; never a replayable provider availability failure."""

    code = "execution_deadline_exceeded"

    def __init__(self) -> None:
        """Expose only a stable, payload-free diagnostic."""
        super().__init__("the local execution deadline was exceeded")


def validate_execution_timeout_ms(value: int | None) -> None:
    """Validate deployment-owned configuration before any credential or network access."""
    if value is None:
        return
    if type(value) is not int:
        raise TypeError("execution_timeout_ms must be an integer or None")
    if not 1 <= value <= MAX_EXECUTION_TIMEOUT_MS:
        raise ValueError("execution_timeout_ms must be between 1 and 86400000")


@dataclass(frozen=True, slots=True)
class ExecutionDeadline:
    """Opaque monotonic budget retained across preparation, attempts and stream yields."""

    _started_at: float | None = field(repr=False)
    _expires_at: float | None = field(repr=False)
    _clock: Callable[[], float] = field(repr=False)

    @classmethod
    def start(
        cls, timeout_ms: int | None, *, clock: Callable[[], float] = time.monotonic
    ) -> "ExecutionDeadline":
        """Capture once; a disabled budget reads no clock and creates no timer."""
        validate_execution_timeout_ms(timeout_ms)
        if timeout_ms is None:
            return cls(None, None, clock)
        started = clock()
        if not math.isfinite(started):
            raise ExecutionDeadlineExceeded()
        return cls(started, started + timeout_ms / 1000, clock)

    @property
    def enabled(self) -> bool:
        """Report whether this execution has an explicit server-owned limit."""
        return self._expires_at is not None

    def remaining_seconds(self) -> float | None:
        """Fail closed at the exact boundary, including invalid/regressed clock input."""
        if self._expires_at is None or self._started_at is None:
            return None
        now = self._clock()
        if not math.isfinite(now) or now < self._started_at or now >= self._expires_at:
            raise ExecutionDeadlineExceeded()
        return self._expires_at - now

    def check(self) -> None:
        """Reject late work even when an operation suppresses timeout cancellation."""
        self.remaining_seconds()

    async def run[T](self, operation: Callable[[], Awaitable[T]]) -> T:
        """Bound one owned await, not an async-generator scope spanning a public yield."""
        remaining = self.remaining_seconds()
        if remaining is None:
            return await operation()
        timeout = asyncio.timeout(remaining)
        try:
            async with timeout:
                result = await operation()
        except TimeoutError:
            if timeout.expired():
                raise ExecutionDeadlineExceeded() from None
            self.check()
            raise
        except Exception:
            if timeout.expired():
                raise ExecutionDeadlineExceeded() from None
            self.check()
            raise
        if timeout.expired():
            raise ExecutionDeadlineExceeded()
        self.check()
        return result
