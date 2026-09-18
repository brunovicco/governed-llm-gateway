"""Opt-in local TLS comparison; never contact a real PDP or a model provider.

The service below is a synthetic wire fixture, not a Policy Model Router or proof
of runtime-authorization enforcement. Its ephemeral TLS identity is trusted only
inside this local experiment. No caller URL, credential or output-file option exists.
"""

import argparse
import asyncio
import http.client
import ipaddress
import json
import math
import platform
import ssl
import statistics
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch
from uuid import uuid4

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from governed_llm_gateway_contracts import DataClassification, RiskLevel
from governed_llm_gateway_core.adapters.policy_router import (
    PolicyRouterHttpAdapter,
    PolicyTransport,
    StdlibPolicyTransport,
)
from governed_llm_gateway_core.adapters.policy_router_httpx import HttpxPolicyTransport
from governed_llm_gateway_core.application.policy import PolicyRequestMetadata

SYNTHETIC_KEYS = {"fixture-a": "synthetic-pdp-a", "fixture-b": "synthetic-pdp-b"}


def fixture_metadata(client_id: str = "fixture-a") -> PolicyRequestMetadata:
    """Produce fresh prompt-free correlation metadata, never an approved ranking artifact."""
    return PolicyRequestMetadata(
        request_id=uuid4(),
        client_id=client_id,
        environment="development",
        workload="rag.answer",
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.PUBLIC,
        context_tokens_estimated=10,
        max_output_tokens_estimated=10,
        structured_output_required=False,
        max_latency_ms=5000,
        max_cost_usd=Decimal("0.01"),
    )


class LocalTlsPdp:
    """HTTP/1.1 fixture bound only to literal loopback, with verified ephemeral TLS."""

    def __init__(self) -> None:
        self.connections = 0
        self.requests: list[tuple[dict[str, object], dict[str, str]]] = []
        self.received = asyncio.Event()
        self.release = asyncio.Event()
        self.stall = False
        self.abort_after_request = False
        self.close_after_response = False
        self.status = 200
        self.raw_body: bytes | None = None
        self.endpoint = ""
        self.client_context: ssl.SSLContext = ssl.create_default_context()
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self._server: asyncio.Server | None = None
        self._writers: set[asyncio.StreamWriter] = set()
        self._handlers: set[asyncio.Task[None]] = set()

    async def __aenter__(self) -> "LocalTlsPdp":
        self._temporary = tempfile.TemporaryDirectory(prefix="pdp-transport-tls-")
        root = Path(self._temporary.name)
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "local-transport-fixture")])
        now = datetime.now(UTC)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(hours=1))
            .add_extension(
                x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        certificate_path = root / "fixture.crt"
        key_path = root / "fixture.key"
        certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        # Generated local fixture material only, inside an owner-private temporary directory.
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        key_path.chmod(0o600)
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(certificate_path, key_path)
        server_context.set_alpn_protocols(["http/1.1"])
        self.client_context = ssl.create_default_context(cafile=str(certificate_path))
        self.client_context.set_alpn_protocols(["http/1.1"])
        try:
            self._server = await asyncio.start_server(
                self._handle, "127.0.0.1", 0, ssl=server_context, ssl_handshake_timeout=2.0
            )
        except BaseException:
            self._temporary.cleanup()
            raise
        port = self._server.sockets[0].getsockname()[1]
        self.endpoint = f"https://127.0.0.1:{port}/route"
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        for writer in tuple(self._writers):
            writer.close()
        for handler in tuple(self._handlers):
            handler.cancel()
        try:
            async with asyncio.timeout(2):
                await asyncio.gather(*tuple(self._handlers), return_exceptions=True)
        finally:
            if self._temporary is not None:
                self._temporary.cleanup()

    @contextmanager
    def trust_stdlib(self) -> Iterator[None]:
        """Use the same verified fixture CA for the unchanged real stdlib transport."""
        original = http.client.HTTPSConnection
        expected_port = int(self.endpoint.split(":")[2].split("/")[0])

        def connection(host: str, *, port: int, timeout: float) -> http.client.HTTPSConnection:
            if host != "127.0.0.1" or port != expected_port:
                raise ValueError("comparison permits only its own loopback TLS fixture")
            return original(host, port=port, timeout=timeout, context=self.client_context)

        # No sockets/responses are mocked; only the fixture CA injection is scoped here.
        # Do not replace http.client's global class: its __init__ uses that class
        # in super(). Intercept only the adapter's module-local infrastructure binding.
        infrastructure = SimpleNamespace(
            client=SimpleNamespace(
                HTTPSConnection=connection, HTTPException=http.client.HTTPException
            )
        )
        with patch("governed_llm_gateway_core.adapters.policy_router.http", infrastructure):
            yield

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = cast(asyncio.Task[None], asyncio.current_task())
        self._handlers.add(task)
        self._writers.add(writer)
        self.connections += 1
        try:
            while True:
                async with asyncio.timeout(5):
                    head = (await reader.readuntil(b"\r\n\r\n")).decode("ascii")
                    lines = head.split("\r\n")
                    if lines[0] != "POST /route HTTP/1.1":
                        return
                    headers = {
                        key.lower(): value.strip()
                        for key, value in (line.split(":", 1) for line in lines[1:] if line)
                    }
                    size = int(headers.get("content-length", "0"))
                    if not 0 < size <= 64 * 1024:
                        return
                    decoded = json.loads(await reader.readexactly(size))
                if not isinstance(decoded, dict):
                    return
                payload = cast(dict[str, object], decoded)
                self.requests.append((payload, headers))
                self.received.set()
                if self.abort_after_request:
                    writer.transport.abort()
                    return
                if self.stall:
                    await self.release.wait()
                request = payload.get("request", payload)
                if not isinstance(request, dict):
                    return
                status = self.status
                if headers.get("x-api-key") != SYNTHETIC_KEYS.get(str(request.get("agent_name"))):
                    status = 401
                response: dict[str, object] = {
                    "schema_version": "1.0",
                    "routing_decision_id": f"fixture-decision-{len(self.requests)}",
                    "decided_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "workflow_id": request.get("workflow_id"),
                    "task_id": request.get("task_id"),
                    "selected_model_group": "fixture-group",
                    "reason": "synthetic transport comparison only",
                    "rejected_candidates": [],
                    "policy_id": "transport-fixture",
                    "policy_version": "1.0.0",
                    "policy_digest": "sha256:" + "0" * 64,
                    "service_version": "fixture-1.0",
                    "environment": "development",
                }
                body = self.raw_body if self.raw_body is not None else json.dumps(response).encode()
                header = (
                    f"HTTP/1.1 {status} Fixture\r\nContent-Length: {len(body)}\r\n"
                    "Content-Type: application/json\r\nSet-Cookie: fixture=not-authority\r\n"
                    "Location: https://forbidden.example/route\r\n"
                    f"Connection: {'close' if self.close_after_response else 'keep-alive'}\r\n\r\n"
                )
                writer.write(header.encode("ascii") + body)
                await writer.drain()
                if self.close_after_response:
                    return
        except (
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            TimeoutError,
            ConnectionError,
            ssl.SSLError,
            ValueError,
        ):
            # A closed/malformed local fixture connection never logs payloads or headers.
            pass
        finally:
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
            self._writers.discard(writer)
            self._handlers.discard(task)


@contextmanager
def _stdlib_fixture_transport(server: LocalTlsPdp) -> Iterator[PolicyTransport]:
    with server.trust_stdlib():
        yield StdlibPolicyTransport()


async def _case(
    server: LocalTlsPdp, transport: PolicyTransport, *, requests: int, concurrency: int
) -> dict[str, object]:
    adapter = PolicyRouterHttpAdapter(
        endpoint=server.endpoint, api_keys_by_client=SYNTHETIC_KEYS, transport=transport
    )
    latencies: list[float] = []
    semaphore = asyncio.Semaphore(concurrency)
    start_connections = server.connections
    start_requests = len(server.requests)

    async def call(index: int) -> None:
        async with semaphore:
            metadata = fixture_metadata("fixture-a" if index % 2 == 0 else "fixture-b")
            started = time.perf_counter()
            decision = await adapter.authorize(metadata)
            latencies.append((time.perf_counter() - started) * 1000)
            if decision.authorization.authorized_model_groups != frozenset({"fixture-group"}):
                raise RuntimeError("local comparison decision did not pass adapter validation")

    for index in range(4):
        await call(index)
    cold_ms = latencies[0]
    warmup_connections = server.connections - start_connections
    latencies.clear()
    measured_connections = server.connections
    started = time.perf_counter()
    await asyncio.gather(*(call(index) for index in range(requests)))
    elapsed = time.perf_counter() - started
    fresh_calls = len(server.requests) - start_requests
    if fresh_calls != requests + 4:
        raise RuntimeError("local comparison did not perform exactly one fresh exchange per call")
    ordered = sorted(latencies)
    return {
        "requests": requests,
        "concurrency": concurrency,
        "cold_ms": round(cold_ms, 3),
        "warmup_requests": 4,
        "warmup_tls_connections": warmup_connections,
        "measured_tls_connections": server.connections - measured_connections,
        "total_tls_connections": server.connections - start_connections,
        "fresh_policy_exchanges": fresh_calls,
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[math.ceil(0.95 * len(ordered)) - 1], 3),
        "requests_per_second": round(requests / elapsed, 2),
    }


async def compare(
    *, requests: int = 48, concurrency: tuple[int, ...] = (1, 4), rounds: int = 3
) -> dict[str, object]:
    """Alternate case order, retain distributions, and report no production/score claims."""
    if type(requests) is not int or not 1 <= requests <= 200:
        raise ValueError("comparison requests must be in 1..200")
    if type(rounds) is not int or not 1 <= rounds <= 5:
        raise ValueError("comparison rounds must be in 1..5")
    if not concurrency or any(
        type(value) is not int or not 1 <= value <= 16 for value in concurrency
    ):
        raise ValueError("comparison concurrency must be in 1..16")
    results: list[dict[str, object]] = []
    async with asyncio.timeout(60), LocalTlsPdp() as server:
        for count in concurrency:
            for round_index in range(rounds):
                modes = ("stdlib", "httpx-pool")
                for mode in modes if round_index % 2 == 0 else tuple(reversed(modes)):
                    if mode == "stdlib":
                        with _stdlib_fixture_transport(server) as transport:
                            result = await _case(
                                server, transport, requests=requests, concurrency=count
                            )
                    else:
                        async with HttpxPolicyTransport(
                            endpoint=server.endpoint,
                            max_connections=count,
                            max_keepalive_connections=count,
                            ssl_context=server.client_context,
                        ) as pooled:
                            result = await _case(
                                server, pooled, requests=requests, concurrency=count
                            )
                    results.append({"round": round_index + 1, "transport": mode, **result})
    return {
        "scope": "local synthetic verified TLS HTTP/1.1, no real PDP/provider calls",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "httpx": httpx.__version__,
        "latency_scope": "adapter call including pool wait, excluding harness semaphore wait",
        "p95_method": "nearest rank per round; warmup excluded",
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=48)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 4])
    args = parser.parse_args()
    report = asyncio.run(
        compare(requests=args.requests, concurrency=tuple(args.concurrency), rounds=args.rounds)
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
