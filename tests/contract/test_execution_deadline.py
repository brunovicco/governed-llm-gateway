"""Credential-free local deadline and ASGI ownership regressions."""

import asyncio
from collections.abc import AsyncGenerator
from typing import cast

import pytest
from governed_llm_gateway_api.deadline_response import (
    DeadlineStreamingResponse,
    TerminalFailureFrame,
)
from governed_llm_gateway_core.application.execution_deadline import (
    ExecutionDeadline,
    ExecutionDeadlineExceeded,
    validate_execution_timeout_ms,
)
from governed_llm_gateway_core.application.health import health_admission_scope
from governed_llm_gateway_core.application.resilience import InMemoryHealthTracker
from governed_llm_gateway_core.domain.resilience import HealthAdmission
from starlette.types import Message


@pytest.mark.parametrize("value", [True, False, 1.0, "10", float("nan"), float("inf")])
def test_deadline_configuration_rejects_coercion(value: object) -> None:
    with pytest.raises(TypeError):
        validate_execution_timeout_ms(cast(int, value))


@pytest.mark.parametrize("value", [0, -1, 86_400_001, 10**100])
def test_deadline_configuration_rejects_invalid_range(value: int) -> None:
    with pytest.raises(ValueError):
        validate_execution_timeout_ms(value)


def test_disabled_deadline_reads_no_clock_and_installs_no_timeout() -> None:
    def forbidden_clock() -> float:
        raise AssertionError("disabled feature must not consult the clock")

    async def scenario() -> None:
        budget = ExecutionDeadline.start(None, clock=forbidden_clock)
        assert not budget.enabled
        assert budget.remaining_seconds() is None
        budget.check()
        assert await budget.run(lambda: asyncio.sleep(0, result=42)) == 42

    asyncio.run(scenario())


@pytest.mark.parametrize("advance", [0.999, 1.0, 1.001])
def test_exact_deadline_boundary_does_not_renew(advance: float) -> None:
    now = [100.0]
    budget = ExecutionDeadline.start(1000, clock=lambda: now[0])
    assert budget.remaining_seconds() == 1.0
    now[0] += advance
    if advance < 1.0:
        assert budget.remaining_seconds() == pytest.approx(1.0 - advance)
    else:
        with pytest.raises(ExecutionDeadlineExceeded):
            budget.check()


@pytest.mark.parametrize("now", [99.0, float("nan"), float("inf")])
def test_invalid_monotonic_clock_fails_closed(now: float) -> None:
    value = [100.0]
    budget = ExecutionDeadline.start(1000, clock=lambda: value[0])
    value[0] = now
    with pytest.raises(ExecutionDeadlineExceeded):
        budget.check()


def test_invalid_initial_clock_fails_closed() -> None:
    with pytest.raises(ExecutionDeadlineExceeded):
        ExecutionDeadline.start(1000, clock=lambda: float("nan"))


def test_expired_budget_does_not_construct_an_operation() -> None:
    now = [0.0]
    budget = ExecutionDeadline.start(1, clock=lambda: now[0])
    now[0] = 1.0

    def forbidden() -> asyncio.Future[None]:
        raise AssertionError("expired execution must not start more work")

    with pytest.raises(ExecutionDeadlineExceeded):
        asyncio.run(budget.run(forbidden))


@pytest.mark.parametrize("suppress_cancel", [False, True])
def test_stalled_await_expires_even_if_cancellation_is_suppressed(suppress_cancel: bool) -> None:
    async def scenario() -> None:
        async def operation() -> int:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if suppress_cancel:
                    return 42
                raise
            return 0

        with pytest.raises(ExecutionDeadlineExceeded):
            await ExecutionDeadline.start(10).run(operation)

    asyncio.run(scenario())


def test_unrelated_timeout_and_external_cancellation_remain_distinct() -> None:
    async def scenario() -> None:
        budget = ExecutionDeadline.start(10_000)

        async def unrelated() -> None:
            raise TimeoutError("unrelated")

        with pytest.raises(TimeoutError, match="unrelated"):
            await budget.run(unrelated)
        started = asyncio.Event()

        async def stalled() -> None:
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(budget.run(stalled))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def test_late_operation_exception_cannot_hide_local_expiry() -> None:
    now = [100.0]
    budget = ExecutionDeadline.start(1000, clock=lambda: now[0])

    async def late_failure() -> None:
        now[0] += 1
        raise RuntimeError("must not escape as a provider or raw local diagnostic")

    with pytest.raises(ExecutionDeadlineExceeded):
        asyncio.run(budget.run(late_failure))


def test_asgi_stalled_delivery_closes_suspended_body() -> None:
    async def scenario() -> None:
        closed = False
        messages: list[Message] = []

        async def body() -> AsyncGenerator[str]:
            nonlocal closed
            try:
                yield "semantic"
                raise AssertionError("blocked delivery must not consume more output")
            finally:
                closed = True

        async def send(message: Message) -> None:
            messages.append(message)
            if message["type"] == "http.response.body":
                await asyncio.Event().wait()

        response = DeadlineStreamingResponse(
            body(), deadline=ExecutionDeadline.start(10), media_type="text/event-stream", headers={}
        )
        await asyncio.wait_for(response.stream_response(send), 2)
        assert closed
        assert len(messages) == 2

    asyncio.run(scenario())


def test_asgi_expired_budget_accepts_only_terminal_failure_framing() -> None:
    async def scenario() -> None:
        now = [0.0]
        deadline = ExecutionDeadline.start(1000, clock=lambda: now[0])
        messages: list[Message] = []

        async def body() -> AsyncGenerator[str]:
            now[0] = 1.0
            yield TerminalFailureFrame("failed")
            yield "forbidden late output"

        async def send(message: Message) -> None:
            messages.append(message)

        response = DeadlineStreamingResponse(
            body(), deadline=deadline, media_type="text/event-stream", headers={}
        )
        await response.stream_response(send)
        assert [m.get("body") for m in messages] == [None, b"failed"]

    asyncio.run(scenario())


def test_asgi_transport_timeout_is_not_silently_classified_as_local_expiry() -> None:
    async def scenario() -> None:
        async def body() -> AsyncGenerator[str]:
            yield "body"

        async def send(message: Message) -> None:
            del message
            raise TimeoutError("unrelated delivery failure")

        response = DeadlineStreamingResponse(
            body(),
            deadline=ExecutionDeadline.start(10_000),
            media_type="text/event-stream",
            headers={},
        )
        with pytest.raises(TimeoutError, match="unrelated"):
            await response.stream_response(send)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "failure", [ExecutionDeadlineExceeded(), asyncio.CancelledError(), GeneratorExit()]
)
def test_finite_health_cleanup_outage_does_not_replace_terminal_outcome(
    failure: BaseException,
) -> None:
    async def scenario() -> None:
        class StalledRelease(InMemoryHealthTracker):
            async def release_request(self, admission: HealthAdmission) -> None:
                del admission
                await asyncio.Event().wait()

        health = StalledRelease()
        admission = await health.allow_request("synthetic-deployment")
        assert admission is not None
        with pytest.raises(type(failure)):
            async with health_admission_scope(health, admission, cleanup_timeout_seconds=0.01):
                raise failure
        assert (await health.snapshot("synthetic-deployment")).request_count == 0

    asyncio.run(asyncio.wait_for(scenario(), 2))


def test_terminal_delivery_grace_is_finite_and_closes_body() -> None:
    async def scenario() -> None:
        closed = False

        async def body() -> AsyncGenerator[str]:
            nonlocal closed
            try:
                yield TerminalFailureFrame("failure")
            finally:
                closed = True

        async def send(message: Message) -> None:
            if message["type"] == "http.response.body":
                await asyncio.Event().wait()

        now = [100.0]
        budget = ExecutionDeadline.start(1000, clock=lambda: now[0])
        now[0] += 1
        response = DeadlineStreamingResponse(
            body(), deadline=budget, media_type="text/event-stream", headers={}
        )
        await asyncio.wait_for(response.stream_response(send), 2)
        assert closed

    asyncio.run(scenario())
