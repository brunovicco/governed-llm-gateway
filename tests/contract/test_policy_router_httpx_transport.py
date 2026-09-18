"""PDP-only pool conformance and local verified-TLS ownership regressions."""

import asyncio
import json
import ssl
from collections.abc import AsyncIterator
from typing import cast

import governed_llm_gateway_core.adapters.policy_router_httpx as pool_module
import httpx
import pytest
from governed_llm_gateway_core.adapters.policy_router import (
    PolicyHttpResponse,
    PolicyRouterHttpAdapter,
    PolicyTransportFailure,
    PolicyTransportFailureKind,
    StdlibPolicyTransport,
)
from governed_llm_gateway_core.adapters.policy_router_httpx import HttpxPolicyTransport
from governed_llm_gateway_core.application.execution_deadline import (
    ExecutionDeadline,
    ExecutionDeadlineExceeded,
)
from governed_llm_gateway_core.application.policy import (
    PolicyDecisionError,
    PolicyDecisionErrorCode,
)

from scripts.pdp_transport_comparison import SYNTHETIC_KEYS, LocalTlsPdp, compare, fixture_metadata

ENDPOINT = "https://policy.example/route"


class Body(httpx.AsyncByteStream):
    def __init__(self, raw: bytes = b'{"ok":true}', *, stall: bool = False) -> None:
        self.raw = raw
        self.stall = stall
        self.started = asyncio.Event()
        self.closed = 0
        self.close_error = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.started.set()
        if self.stall:
            await asyncio.Event().wait()
        for index in range(0, len(self.raw), 65536):
            yield self.raw[index : index + 65536]

    async def aclose(self) -> None:
        self.closed += 1
        if self.close_error:
            raise OSError("raw cleanup credential detail")


class Wire(httpx.AsyncBaseTransport):
    def __init__(self, body: Body) -> None:
        self.body = body
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.error: httpx.RequestError | None = None
        self.closed = 0
        self.close_started = asyncio.Event()
        self.close_release = asyncio.Event()
        self.stall_close = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return httpx.Response(
            self.status,
            headers={"retry-after": "2", "set-cookie": "private-cookie", "location": ENDPOINT},
            stream=self.body,
        )

    async def aclose(self) -> None:
        self.closed += 1
        self.close_started.set()
        if self.stall_close:
            await self.close_release.wait()


def wire_fixture(monkeypatch: pytest.MonkeyPatch, body: Body | None = None) -> Wire:
    wire = Wire(body or Body())

    def factory(**kwargs: object) -> Wire:
        context = kwargs["verify"]
        assert isinstance(context, ssl.SSLContext)
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        assert kwargs["trust_env"] is False
        assert kwargs["retries"] == 0 and kwargs["http2"] is False
        limits = kwargs["limits"]
        assert isinstance(limits, httpx.Limits) and limits.max_connections == 8
        return wire

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", factory)
    return wire


async def post(
    pool: HttpxPolicyTransport, *, timeout: float = 5, key: str = "synthetic-key"
) -> PolicyHttpResponse:
    return await pool.post_json(
        url=ENDPOINT,
        headers={"x-api-key": key},
        payload={"workload": "rag.answer"},
        timeout_seconds=timeout,
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1/route",
        "https://u:p@policy.example/route",
        "https://policy.example/#f",
        "https://policy.example/?q=1",
        "https://policy.example:invalid/route",
        "https:///route",
        " https://policy.example/route",
        "https://policy.example/\nroute",
    ],
)
def test_endpoint_fails_before_connection_creation(endpoint: str) -> None:
    with pytest.raises(ValueError):
        HttpxPolicyTransport(endpoint=endpoint)


@pytest.mark.parametrize("value", [True, 0, -1, 65, 1.5])
def test_connection_limit_rejects_invalid_input(value: object) -> None:
    with pytest.raises(ValueError):
        HttpxPolicyTransport(endpoint=ENDPOINT, max_connections=cast(int, value))


@pytest.mark.parametrize("value", [True, -1, 9, 1.0])
def test_keepalive_limit_is_bounded(value: object) -> None:
    with pytest.raises(ValueError):
        HttpxPolicyTransport(endpoint=ENDPOINT, max_keepalive_connections=cast(int, value))


@pytest.mark.parametrize("value", [True, 0, -1, float("nan"), float("inf"), 301, 10**1000])
def test_idle_expiry_and_request_wait_are_finite(value: float) -> None:
    with pytest.raises(ValueError):
        HttpxPolicyTransport(endpoint=ENDPOINT, keepalive_expiry_seconds=value)

    async def scenario() -> None:
        async with HttpxPolicyTransport(endpoint=ENDPOINT) as pool:
            with pytest.raises(ValueError):
                await post(pool, timeout=value)

    asyncio.run(scenario())


def test_unverified_tls_context_is_never_accepted() -> None:
    context = ssl.create_default_context()
    context.check_hostname = False
    with pytest.raises(ValueError):
        HttpxPolicyTransport(endpoint=ENDPOINT, ssl_context=context)
    with pytest.raises(ValueError):
        HttpxPolicyTransport(endpoint=ENDPOINT, ssl_context=cast(ssl.SSLContext, False))


def test_default_adapter_is_unchanged_and_unused_pool_is_lazy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = wire_fixture(monkeypatch)
    adapter = PolicyRouterHttpAdapter(endpoint=ENDPOINT, api_keys_by_client={"fixture-a": "key"})
    assert isinstance(adapter._transport, StdlibPolicyTransport)

    async def scenario() -> None:
        async with HttpxPolicyTransport(endpoint=ENDPOINT) as pool:
            with pytest.raises(ValueError, match="bound endpoint"):
                await pool.post_json(
                    url="https://other.example/route", headers={}, payload={}, timeout_seconds=5
                )
        await pool.aclose()
        with pytest.raises(RuntimeError, match="closed"):
            await post(pool)
        assert wire.requests == [] and wire.closed == 0

    asyncio.run(scenario())


def test_fresh_requests_preserve_headers_body_and_have_no_cookie_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = wire_fixture(monkeypatch)

    async def scenario() -> None:
        async with HttpxPolicyTransport(endpoint=ENDPOINT) as pool:
            await asyncio.gather(*(post(pool, key=f"synthetic-{index}") for index in range(16)))
            for index, request in enumerate(wire.requests):
                assert request.headers["x-api-key"] == f"synthetic-{index}"
                assert "cookie" not in request.headers and "authorization" not in request.headers
                assert "accept-encoding" not in request.headers
                assert json.loads(request.content) == {"workload": "rag.answer"}
                assert request.extensions["timeout"] == {
                    "connect": 5,
                    "read": 5,
                    "write": 5,
                    "pool": 5,
                }
            result = await post(pool)
            assert result.payload == {"ok": True} and result.retry_after == "2"
            assert not hasattr(result, "headers")
        assert wire.closed == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [200, 422])
@pytest.mark.parametrize("raw", [b"not json", b"[]", b"\xff"])
def test_invalid_json_is_permanent_and_closes_body(
    monkeypatch: pytest.MonkeyPatch, status: int, raw: bytes
) -> None:
    body = Body(raw)
    wire = wire_fixture(monkeypatch, body)
    wire.status = status

    async def scenario() -> None:
        async with HttpxPolicyTransport(endpoint=ENDPOINT) as pool:
            with pytest.raises(PolicyTransportFailure) as caught:
                await post(pool)
            assert caught.value.kind is PolicyTransportFailureKind.INVALID_RESPONSE
            assert body.closed == 1 and len(wire.requests) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [307, 401, 403, 429, 500, 503])
def test_other_statuses_do_not_parse_bodies_or_follow_redirects(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    wire = wire_fixture(monkeypatch, Body(b"raw private error"))
    wire.status = status

    async def scenario() -> None:
        async with HttpxPolicyTransport(endpoint=ENDPOINT) as pool:
            result = await post(pool)
            assert result.status_code == status and result.payload is None
            assert len(wire.requests) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("extra", [0, 1])
def test_response_ceiling_applies_to_raw_incremental_bytes(
    monkeypatch: pytest.MonkeyPatch, extra: int
) -> None:
    raw = b'{"ok":true}'
    body = Body(raw + b" " * (512 * 1024 - len(raw) + extra))
    wire_fixture(monkeypatch, body)

    async def scenario() -> None:
        async with HttpxPolicyTransport(endpoint=ENDPOINT) as pool:
            if extra:
                with pytest.raises(PolicyTransportFailure) as caught:
                    await post(pool)
                assert caught.value.kind is PolicyTransportFailureKind.INVALID_RESPONSE
            else:
                await post(pool)
            assert body.closed == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "error_type,kind",
    [
        (httpx.PoolTimeout, PolicyTransportFailureKind.TIMEOUT),
        (httpx.ConnectTimeout, PolicyTransportFailureKind.TIMEOUT),
        (httpx.ReadTimeout, PolicyTransportFailureKind.TIMEOUT),
        (httpx.WriteTimeout, PolicyTransportFailureKind.TIMEOUT),
        (httpx.ConnectError, PolicyTransportFailureKind.NETWORK),
        (httpx.RemoteProtocolError, PolicyTransportFailureKind.NETWORK),
    ],
)
def test_transport_failure_is_sanitized_and_never_replayed(
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[httpx.RequestError],
    kind: PolicyTransportFailureKind,
) -> None:
    wire = wire_fixture(monkeypatch)
    wire.error = error_type("raw secret detail and synthetic-key")

    async def scenario() -> None:
        async with HttpxPolicyTransport(endpoint=ENDPOINT) as pool:
            with pytest.raises(PolicyTransportFailure) as caught:
                await post(pool)
            assert caught.value.kind is kind and len(wire.requests) == 1
            assert "secret" not in str(caught.value) and caught.value.__suppress_context__

    asyncio.run(scenario())


@pytest.mark.parametrize("deadline", [False, True])
def test_cancel_or_total_deadline_closes_body_and_releases_owned_work(
    monkeypatch: pytest.MonkeyPatch, deadline: bool
) -> None:
    body = Body(stall=True)
    wire_fixture(monkeypatch, body)

    async def scenario() -> None:
        async with HttpxPolicyTransport(endpoint=ENDPOINT) as pool:
            if deadline:
                with pytest.raises(ExecutionDeadlineExceeded):
                    await ExecutionDeadline.start(10).run(lambda: post(pool))
            else:
                task = asyncio.create_task(post(pool))
                await body.started.wait()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert body.closed == 1 and pool._active == set()

    asyncio.run(scenario())


def test_shutdown_cancels_owned_requests_and_survives_cancelled_close_waiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = Body(stall=True)
    wire = wire_fixture(monkeypatch, body)
    wire.stall_close = True

    async def scenario() -> None:
        pool = HttpxPolicyTransport(endpoint=ENDPOINT)
        task = asyncio.create_task(post(pool))
        await body.started.wait()
        closing = asyncio.create_task(pool.aclose())
        await wire.close_started.wait()
        closing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await closing
        wire.close_release.set()
        await pool.aclose()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert body.closed == wire.closed == 1
        with pytest.raises(RuntimeError, match="closed"):
            await post(pool)

    asyncio.run(scenario())


@pytest.mark.parametrize("invalid_body", [False, True])
def test_cleanup_failure_does_not_allow_success_or_replace_primary_failure(
    monkeypatch: pytest.MonkeyPatch, invalid_body: bool
) -> None:
    body = Body(b"invalid" if invalid_body else b'{"ok":true}')
    body.close_error = True
    wire_fixture(monkeypatch, body)

    async def scenario() -> None:
        async with HttpxPolicyTransport(endpoint=ENDPOINT) as pool:
            with pytest.raises(PolicyTransportFailure) as caught:
                await post(pool)
            assert caught.value.kind is (
                PolicyTransportFailureKind.INVALID_RESPONSE
                if invalid_body
                else PolicyTransportFailureKind.NETWORK
            )
            assert "credential" not in str(caught.value)

    asyncio.run(scenario())


def test_pool_cannot_cross_event_loops(monkeypatch: pytest.MonkeyPatch) -> None:
    wire_fixture(monkeypatch)
    pool = HttpxPolicyTransport(endpoint=ENDPOINT)

    async def first() -> None:
        await post(pool)
        await pool.aclose()

    asyncio.run(first())
    with pytest.raises(RuntimeError, match="event loop"):
        asyncio.run(post(pool))


@pytest.mark.integration
def test_verified_tls_reuse_preserves_fresh_decisions_and_client_isolation() -> None:
    async def scenario() -> None:
        async with (
            LocalTlsPdp() as server,
            HttpxPolicyTransport(
                endpoint=server.endpoint, ssl_context=server.client_context
            ) as pool,
        ):
            adapter = PolicyRouterHttpAdapter(
                endpoint=server.endpoint, api_keys_by_client=SYNTHETIC_KEYS, transport=pool
            )
            decisions = [
                await adapter.authorize(fixture_metadata(client))
                for client in ["fixture-a", "fixture-b", "fixture-a"]
            ]
            assert server.connections == 1 and len(server.requests) == 3
            assert len({d.provenance.decision_id for d in decisions}) == 3
            assert [h["x-api-key"] for _, h in server.requests] == [
                SYNTHETIC_KEYS[client] for client in ["fixture-a", "fixture-b", "fixture-a"]
            ]
            assert all("cookie" not in h for _, h in server.requests)
            server.status = 403
            with pytest.raises(PolicyDecisionError) as denied:
                await adapter.authorize(fixture_metadata())
            assert denied.value.code is PolicyDecisionErrorCode.AUTHORIZATION
            assert not denied.value.retryable and len(server.requests) == 4

    asyncio.run(scenario())


@pytest.mark.integration
@pytest.mark.parametrize(
    "mode", ["pool-wait", "cancel", "abort", "abort-reused", "server-close", "untrusted-tls"]
)
def test_real_tls_failure_cancellation_and_connection_recovery(mode: str) -> None:
    async def scenario() -> None:
        async with (
            LocalTlsPdp() as server,
            HttpxPolicyTransport(
                endpoint=server.endpoint,
                max_connections=1,
                max_keepalive_connections=1,
                ssl_context=None if mode == "untrusted-tls" else server.client_context,
            ) as pool,
        ):
            adapter = PolicyRouterHttpAdapter(
                endpoint=server.endpoint,
                api_keys_by_client=SYNTHETIC_KEYS,
                transport=pool,
                timeout_seconds=2.0,
            )
            if mode == "untrusted-tls":
                with pytest.raises(PolicyDecisionError):
                    await adapter.authorize(fixture_metadata())
                assert server.requests == []
            elif mode in {"abort", "abort-reused"}:
                if mode == "abort-reused":
                    await adapter.authorize(fixture_metadata())
                server.abort_after_request = True
                with pytest.raises(PolicyDecisionError) as failed:
                    await adapter.authorize(fixture_metadata())
                assert failed.value.code is PolicyDecisionErrorCode.TRANSPORT
                assert len(server.requests) == (2 if mode == "abort-reused" else 1)
                assert server.connections == 1
            elif mode == "server-close":
                server.close_after_response = True
                await adapter.authorize(fixture_metadata())
                await adapter.authorize(fixture_metadata())
                assert server.connections == len(server.requests) == 2
            else:
                server.stall = True
                first = asyncio.create_task(adapter.authorize(fixture_metadata()))
                await server.received.wait()
                if mode == "pool-wait":
                    with pytest.raises(PolicyTransportFailure) as expired:
                        await pool.post_json(
                            url=server.endpoint, headers={}, payload={}, timeout_seconds=0.01
                        )
                    assert expired.value.kind is PolicyTransportFailureKind.TIMEOUT
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first
                server.stall = False
                server.release.set()
                await adapter.authorize(fixture_metadata())
                assert len(server.requests) == 2

    asyncio.run(asyncio.wait_for(scenario(), 3))


@pytest.mark.integration
def test_local_comparison_reports_real_tls_counts_not_ranking_evidence() -> None:
    report = asyncio.run(compare(requests=4, concurrency=(1,), rounds=1))
    results = cast(list[dict[str, object]], report["results"])
    assert results[0]["total_tls_connections"] == 8
    assert results[1]["total_tls_connections"] == 1
    assert all(result["fresh_policy_exchanges"] == 8 for result in results)
    assert "synthetic" in str(report["scope"])
    assert "synthetic-pdp" not in json.dumps(report)


@pytest.mark.parametrize("invalid_body", [False, True])
def test_response_cleanup_outage_is_finite_and_preserves_primary_outcome(
    monkeypatch: pytest.MonkeyPatch, invalid_body: bool
) -> None:
    class StalledClose(Body):
        async def aclose(self) -> None:
            await asyncio.Event().wait()

    monkeypatch.setattr(pool_module, "_CLEANUP_SECONDS", 0.01)
    wire_fixture(monkeypatch, StalledClose(b"invalid" if invalid_body else b'{"ok":true}'))

    async def scenario() -> None:
        async with HttpxPolicyTransport(endpoint=ENDPOINT) as pool:
            with pytest.raises(PolicyTransportFailure) as error:
                await post(pool)
            assert error.value.kind is (
                PolicyTransportFailureKind.INVALID_RESPONSE
                if invalid_body
                else PolicyTransportFailureKind.NETWORK
            )

    asyncio.run(asyncio.wait_for(scenario(), 2))


def test_read_failure_after_headers_closes_response_without_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenRead(Body):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"{"
            raise httpx.ReadError("raw credential detail")

    body = BrokenRead()
    wire = wire_fixture(monkeypatch, body)

    async def scenario() -> None:
        async with HttpxPolicyTransport(endpoint=ENDPOINT) as pool:
            with pytest.raises(PolicyTransportFailure) as error:
                await post(pool)
            assert error.value.kind is PolicyTransportFailureKind.NETWORK
            assert len(wire.requests) == body.closed == 1
            assert "credential" not in str(error.value)

    asyncio.run(scenario())


@pytest.mark.integration
def test_concurrent_local_tls_connections_never_exceed_pool_limit() -> None:
    async def scenario() -> None:
        async with (
            LocalTlsPdp() as server,
            HttpxPolicyTransport(
                endpoint=server.endpoint,
                max_connections=2,
                max_keepalive_connections=2,
                ssl_context=server.client_context,
            ) as pool,
        ):
            server.stall = True
            adapter = PolicyRouterHttpAdapter(
                endpoint=server.endpoint, api_keys_by_client=SYNTHETIC_KEYS, transport=pool
            )
            tasks = [asyncio.create_task(adapter.authorize(fixture_metadata())) for _ in range(4)]
            await server.received.wait()
            while len(server.requests) < 2:
                await asyncio.sleep(0)
            assert server.connections == len(server.requests) == 2
            server.stall = False
            server.release.set()
            await asyncio.gather(*tasks)
            assert server.connections == 2 and len(server.requests) == 4

    asyncio.run(asyncio.wait_for(scenario(), 3))


@pytest.mark.integration
def test_success_with_mismatched_correlation_still_fails_closed() -> None:
    async def scenario() -> None:
        async with (
            LocalTlsPdp() as server,
            HttpxPolicyTransport(
                endpoint=server.endpoint, ssl_context=server.client_context
            ) as pool,
        ):
            metadata = fixture_metadata()
            adapter = PolicyRouterHttpAdapter(
                endpoint=server.endpoint, api_keys_by_client=SYNTHETIC_KEYS, transport=pool
            )
            await adapter.authorize(metadata)
            response: dict[str, object] = {
                "schema_version": "1.0",
                "routing_decision_id": "fixture-mismatch",
                "decided_at": "2026-09-18T00:00:00Z",
                "workflow_id": "wrong",
                "task_id": str(metadata.request_id),
                "selected_model_group": "fixture-group",
                "reason": "fixture only",
                "rejected_candidates": [],
                "policy_id": "transport-fixture",
                "policy_version": "1.0.0",
                "policy_digest": "sha256:" + "0" * 64,
                "service_version": "fixture-1.0",
                "environment": "development",
            }
            server.raw_body = json.dumps(response).encode()
            with pytest.raises(PolicyDecisionError) as error:
                await adapter.authorize(metadata)
            assert error.value.code is PolicyDecisionErrorCode.INVALID_RESPONSE
            assert server.connections == 1 and len(server.requests) == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("requests,rounds,concurrency", [(0, 1, (1,)), (4, 6, (1,)), (4, 1, ())])
def test_comparison_rejects_unbounded_or_invalid_run_before_listening(
    requests: int,
    rounds: int,
    concurrency: tuple[int, ...],
) -> None:
    with pytest.raises(ValueError):
        asyncio.run(compare(requests=requests, rounds=rounds, concurrency=concurrency))
