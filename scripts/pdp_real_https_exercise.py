"""Exercise the optional PDP pool and deadline against the pinned local Policy Router.

The Router and HTTPS bridge use synthetic authorization material and deterministic providers. The
exercise never contacts model providers, public endpoints, AWS, or production policy services.
"""

import argparse
import asyncio
import json
import os
import shutil
import ssl
import subprocess  # nosec B404
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import cast
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from governed_llm_gateway_api.policy_router_lifecycle import (
    PolicyRouterHttpPoolSettings,
    PolicyRouterPoolLifecycle,
)
from governed_llm_gateway_core.adapters.policy_router import (
    PolicyTransport,
)
from governed_llm_gateway_core.adapters.policy_router_httpx import HttpxPolicyTransport
from governed_llm_gateway_core.application.policy import (
    PolicyDecisionError,
    PolicyDecisionErrorCode,
    PolicyDecisionPort,
    PolicyRequestMetadata,
    project_policy_request,
)
from governed_llm_gateway_core.domain.governance import ForwardableGovernanceAuthorization

from scripts import composition_fixture, composition_proof, portfolio_execution_demo
from scripts.composition_pin import verify_router_revision
from scripts.demo_pdp_https import LocalVerifiedHttpsProxy

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_REQUESTS = 4
_DEFAULT_ROUNDS = 2
_MAX_REQUESTS = 16
_MAX_ROUNDS = 3
_PROXY_DELAY_SECONDS = 0.025


def _metadata(
    authorization: ForwardableGovernanceAuthorization | None = None,
) -> PolicyRequestMetadata:
    request = composition_proof._gateway_request()
    context = composition_proof._effective_context()
    return project_policy_request(
        request,
        context,
        context_tokens_estimated=composition_fixture.CONTEXT_TOKENS_ESTIMATED,
        max_output_tokens_estimated=composition_fixture.MAX_OUTPUT_TOKENS_ESTIMATED,
        defaults=composition_proof._defaults(),
        runtime_authorization=authorization,
    )


def _fresh_authorization() -> ForwardableGovernanceAuthorization:
    envelope = composition_fixture.mint_envelope(
        now=datetime.now(UTC), authorization_id=str(uuid4())
    )
    return composition_proof._forwardable(envelope)


def _decision_adapter(
    endpoint: str, transport: PolicyTransport | None = None
) -> PolicyDecisionPort:
    return composition_proof._adapter(endpoint, transport=transport)


async def _fresh_call(adapter: PolicyDecisionPort) -> tuple[str, str]:
    decision = await adapter.authorize(_metadata(_fresh_authorization()))
    groups = decision.authorization.authorized_model_groups
    if groups != frozenset({composition_fixture.MODEL_GROUP}):
        raise RuntimeError("the real Policy Router returned an unexpected model group")
    return decision.provenance.decision_id, next(iter(groups))


async def _fresh_sequence(
    endpoint: str,
    transport: PolicyTransport | None,
    *,
    requests: int,
    concurrency: int,
) -> dict[str, object]:
    adapter = _decision_adapter(endpoint, transport)
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    decision_ids: list[str] = []

    async def call() -> None:
        async with semaphore:
            started = time.perf_counter()
            decision_id, _ = await _fresh_call(adapter)
            latencies.append((time.perf_counter() - started) * 1000)
            decision_ids.append(decision_id)

    await asyncio.gather(*(call() for _ in range(requests)))
    ordered = sorted(latencies)
    return {
        "fresh_authorizations": requests,
        "unique_decisions": len(set(decision_ids)),
        "authorized_group": composition_fixture.MODEL_GROUP,
        "p50_ms": round(median(ordered), 3),
        "p95_ms": round(ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)], 3),
    }


async def _denial(endpoint: str, transport: PolicyTransport | None) -> dict[str, object]:
    adapter = _decision_adapter(endpoint, transport)
    try:
        await adapter.authorize(_metadata())
    except PolicyDecisionError as error:
        passed = (
            error.code is PolicyDecisionErrorCode.AUTHORIZATION
            and error.status_code == 403
            and not error.retryable
        )
        return {
            "passed": passed,
            "outcome": error.code.value,
            "status": error.status_code,
            "retryable": error.retryable,
        }
    return {"passed": False, "outcome": "unexpected authorization"}


async def _invalid_certificate(endpoint: str) -> dict[str, object]:
    # Deliberately empty trust store: hostname and certificate verification remain enabled.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    async with HttpxPolicyTransport(endpoint=endpoint, ssl_context=context) as transport:
        adapter = _decision_adapter(endpoint, transport)
        try:
            await adapter.authorize(_metadata(_fresh_authorization()))
        except PolicyDecisionError as error:
            return {
                "passed": error.code is PolicyDecisionErrorCode.TRANSPORT,
                "outcome": error.code.value,
            }
    return {"passed": False, "outcome": "untrusted certificate was accepted"}


async def _pool_lifecycle(endpoint: str, proxy: LocalVerifiedHttpsProxy) -> dict[str, object]:
    owner = PolicyRouterPoolLifecycle(
        endpoint=endpoint,
        settings=PolicyRouterHttpPoolSettings(
            max_connections=1, max_keepalive_connections=1, keepalive_expiry_seconds=10
        ),
    )
    adapter = _decision_adapter(endpoint, cast(PolicyTransport, owner))
    request_count_before_start = proxy.metrics[1]
    before_start_rejected = False
    try:
        await adapter.authorize(_metadata(_fresh_authorization()))
    except PolicyDecisionError as error:
        before_start_rejected = error.code is PolicyDecisionErrorCode.TRANSPORT

    async with owner.lifespan(FastAPI()):
        active = owner.ready()
        # Startup must be local-only: no readiness probe or authorization warmup.
        no_startup_exchange = proxy.metrics[1] == request_count_before_start
        decision_id, _ = await _fresh_call(adapter)
        completed = bool(decision_id)
    after_shutdown = not owner.ready()
    requests_after_close = proxy.metrics[1]
    rejected_after_shutdown = False
    try:
        await adapter.authorize(_metadata(_fresh_authorization()))
    except PolicyDecisionError as error:
        rejected_after_shutdown = error.code is PolicyDecisionErrorCode.TRANSPORT
    return {
        "passed": (
            before_start_rejected
            and active
            and no_startup_exchange
            and completed
            and after_shutdown
            and rejected_after_shutdown
            and proxy.metrics[1] == requests_after_close
        ),
        "before_start_rejected": before_start_rejected,
        "ready_during_lifespan": active,
        "no_startup_authorization": no_startup_exchange,
        "after_shutdown_inactive": after_shutdown,
        "after_shutdown_rejected": rejected_after_shutdown,
    }


def _before_commit_deadline(
    endpoint: str, directory: Path, proxy: LocalVerifiedHttpsProxy
) -> dict[str, object]:
    proxy.response_delay_seconds = 0.2
    provider = portfolio_execution_demo._SimulatedProvider()
    services = portfolio_execution_demo._build_services(
        directory, endpoint, provider, execution_timeout_ms=50
    )
    before = proxy.metrics[1]
    response = TestClient(services.app).post(
        "/v1/generate",
        headers={"X-Gateway-API-Key": portfolio_execution_demo._GATEWAY_KEY},
        json=portfolio_execution_demo._payload(),
    )
    # Let the deliberately delayed real-PDP response arrive after the Gateway has timed out.
    time.sleep(0.25)
    calls = portfolio_execution_demo._provider_calls(provider)
    code = response.json().get("detail", {}).get("code")
    fresh_pdp_exchanges = proxy.metrics[1] - before
    provider_calls = sum(calls.values())
    passed = (
        response.status_code == 504
        and code == "execution_deadline_exceeded"
        and fresh_pdp_exchanges == 1
        and provider_calls == 0
    )
    proxy.response_delay_seconds = 0.0
    return {
        "passed": passed,
        "status": response.status_code,
        "outcome": code,
        "fresh_pdp_exchanges": fresh_pdp_exchanges,
        "provider_calls": provider_calls,
        "late_provider_success": provider_calls > 0,
    }


def _after_output_deadline(endpoint: str, directory: Path) -> dict[str, object]:
    provider = portfolio_execution_demo._SimulatedProvider()
    provider.scenario = "deadline"
    services = portfolio_execution_demo._build_services(
        directory, endpoint, provider, execution_timeout_ms=100
    )
    response = TestClient(services.app).post(
        "/v1/generate",
        headers={"X-Gateway-API-Key": portfolio_execution_demo._GATEWAY_KEY},
        json=portfolio_execution_demo._payload(),
    )
    events = portfolio_execution_demo._event_types(response.text)
    calls = portfolio_execution_demo._provider_calls(provider)
    passed = (
        response.status_code == 200
        and "content.delta" in events
        and events.count("response.failed") == 1
        and "response.completed" not in events
        and calls[portfolio_execution_demo._PRIMARY] == 1
        and not calls[portfolio_execution_demo._SECONDARY]
        and not calls[portfolio_execution_demo._UNAUTHORIZED]
        and provider.closed[portfolio_execution_demo._MODEL_IDS[portfolio_execution_demo._PRIMARY]]
        == 1
    )
    return {
        "passed": passed,
        "http_status": response.status_code,
        "events": events,
        "provider_calls": sum(calls.values()),
        "provider_stream_closed": provider.closed[
            portfolio_execution_demo._MODEL_IDS[portfolio_execution_demo._PRIMARY]
        ]
        == 1,
        "late_completion": "response.completed" in events,
    }


def validate_bounds(requests: int, rounds: int) -> None:
    """Reject an unbounded local exercise before Docker or listener creation."""
    if type(requests) is not int or not 2 <= requests <= _MAX_REQUESTS:
        raise ValueError(f"requests must be between 2 and {_MAX_REQUESTS}")
    if type(rounds) is not int or not 1 <= rounds <= _MAX_ROUNDS:
        raise ValueError(f"rounds must be between 1 and {_MAX_ROUNDS}")


def run_exercise(*, requests: int = _DEFAULT_REQUESTS, rounds: int = _DEFAULT_ROUNDS) -> int:
    validate_bounds(requests, rounds)
    revision = verify_router_revision(portfolio_execution_demo._ROUTER_PATH)
    docker = shutil.which("docker")
    if docker is None:
        print("exercise unavailable: Docker is required", file=sys.stderr)
        return 2

    project_name = f"gateway-pdp-https-{uuid4().hex[:10]}"
    port = portfolio_execution_demo._free_loopback_port()
    report: dict[str, object] = {
        "scope": "pinned local Policy Model Router via verified loopback HTTPS; no provider calls",
        "router_revision": revision,
        "rounds": rounds,
        "requests_per_transport_per_round": requests,
        "results": [],
    }
    original_key = os.environ.get(composition_fixture.API_KEY_ENV_REFERENCE)
    os.environ[composition_fixture.API_KEY_ENV_REFERENCE] = portfolio_execution_demo._PDP_API_KEY

    with tempfile.TemporaryDirectory(prefix="gateway-pdp-https-exercise-") as temporary_dir:
        temporary = Path(temporary_dir)
        key_path = temporary / "runtime-authorization-keys.json"
        key_path.write_text(
            json.dumps(composition_fixture.trusted_key_set(now=datetime.now(UTC))),
            encoding="utf-8",
        )
        compose_file = portfolio_execution_demo._compose_document(
            port, key_path, portfolio_execution_demo._PDP_API_KEY
        )
        base = [
            docker,
            "compose",
            "--project-directory",
            str(_ROOT),
            "-p",
            project_name,
            "-f",
            str(compose_file),
        ]
        try:
            started = subprocess.run(
                [*base, "up", "-d", "--build"],
                cwd=_ROOT,
                capture_output=True,
                check=False,
                timeout=300,
            )  # nosec B603
            if started.returncode != 0:
                print("exercise failed: pinned Policy Router startup failed", file=sys.stderr)
                return 1
            portfolio_execution_demo._wait_router(port)
            with LocalVerifiedHttpsProxy(upstream_port=port) as proxy:
                case_results: list[dict[str, object]] = []
                proxy.response_delay_seconds = _PROXY_DELAY_SECONDS
                for round_number in range(1, rounds + 1):
                    modes = (
                        ("stdlib-default", "httpx-pool-concurrency-sized")
                        if round_number % 2
                        else ("httpx-pool-concurrency-sized", "stdlib-default")
                    )
                    for mode in modes:
                        before_connections, before_requests = proxy.metrics
                        if mode == "stdlib-default":
                            measured = asyncio.run(
                                _fresh_sequence(
                                    proxy.endpoint,
                                    None,
                                    requests=requests,
                                    concurrency=requests,
                                )
                            )
                        else:
                            measured = asyncio.run(
                                _run_pooled_sequence(
                                    proxy.endpoint,
                                    requests=requests,
                                    concurrency=requests,
                                    max_connections=requests,
                                )
                            )
                        after_connections, after_requests = proxy.metrics
                        tls_connections = after_connections - before_connections
                        forwarded_requests = after_requests - before_requests
                        expected_connections = requests
                        measured.update(
                            {
                                "round": round_number,
                                "transport": mode,
                                "tls_connections": tls_connections,
                                "forwarded_requests": forwarded_requests,
                                "provider_calls": 0,
                                "passed": (
                                    measured["fresh_authorizations"] == forwarded_requests
                                    and measured["unique_decisions"] == requests
                                    and tls_connections == expected_connections
                                ),
                            }
                        )
                        case_results.append(measured)

                saturation_before_connections, saturation_before_requests = proxy.metrics
                saturation = asyncio.run(
                    _run_pooled_sequence(
                        proxy.endpoint,
                        requests=requests,
                        concurrency=requests,
                        max_connections=1,
                    )
                )
                saturation_after_connections, saturation_after_requests = proxy.metrics
                saturation.update(
                    {
                        "tls_connections": saturation_after_connections
                        - saturation_before_connections,
                        "forwarded_requests": saturation_after_requests
                        - saturation_before_requests,
                        "pool_limit": 1,
                        "passed": (
                            saturation["unique_decisions"] == requests
                            and saturation_after_requests - saturation_before_requests == requests
                            and saturation_after_connections - saturation_before_connections == 1
                        ),
                    }
                )

                denial_before = proxy.metrics[1]
                denial = asyncio.run(_denial(proxy.endpoint, None))
                denial["fresh_pdp_exchanges"] = proxy.metrics[1] - denial_before
                denial["passed"] = bool(denial["passed"] and denial["fresh_pdp_exchanges"] == 1)

                invalid_before = proxy.metrics[1]
                invalid_certificate = asyncio.run(_invalid_certificate(proxy.endpoint))
                invalid_certificate["pdp_exchanges"] = proxy.metrics[1] - invalid_before
                invalid_certificate["passed"] = bool(
                    invalid_certificate["passed"] and invalid_certificate["pdp_exchanges"] == 0
                )

                lifecycle_before = proxy.metrics[1]
                lifecycle = asyncio.run(_pool_lifecycle(proxy.endpoint, proxy))
                lifecycle["fresh_pdp_exchanges"] = proxy.metrics[1] - lifecycle_before
                lifecycle["passed"] = bool(
                    lifecycle["passed"] and lifecycle["fresh_pdp_exchanges"] == 1
                )

                before_deadline = _before_commit_deadline(
                    proxy.endpoint, temporary / "deadline-before-commit", proxy
                )
                after_deadline = _after_output_deadline(
                    proxy.endpoint, temporary / "deadline-after-output"
                )
                report["results"] = case_results
                report["pool_saturation"] = saturation
                report["policy_denial"] = denial
                report["invalid_certificate"] = invalid_certificate
                report["pool_lifecycle"] = lifecycle
                report["deadline_before_commit"] = before_deadline
                report["deadline_after_output"] = after_deadline
        finally:
            stopped = portfolio_execution_demo._teardown_compose(base)
            compose_file.unlink(missing_ok=True)
            if original_key is None:
                os.environ.pop(composition_fixture.API_KEY_ENV_REFERENCE, None)
            else:
                os.environ[composition_fixture.API_KEY_ENV_REFERENCE] = original_key
            report["compose_cleanup_passed"] = stopped

    result_rows = cast(list[dict[str, object]], report.get("results", []))
    passed = (
        len(result_rows) == rounds * 2
        and all(bool(row.get("passed")) for row in result_rows)
        and bool(cast(dict[str, object], report.get("pool_saturation", {})).get("passed"))
        and bool(cast(dict[str, object], report.get("policy_denial", {})).get("passed"))
        and bool(cast(dict[str, object], report.get("invalid_certificate", {})).get("passed"))
        and bool(cast(dict[str, object], report.get("pool_lifecycle", {})).get("passed"))
        and bool(cast(dict[str, object], report.get("deadline_before_commit", {})).get("passed"))
        and bool(cast(dict[str, object], report.get("deadline_after_output", {})).get("passed"))
        and bool(report.get("compose_cleanup_passed"))
    )
    report["passed"] = passed
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed else 1


async def _run_pooled_sequence(
    endpoint: str, *, requests: int, concurrency: int, max_connections: int | None = None
) -> dict[str, object]:
    connection_limit = max_connections if max_connections is not None else concurrency
    async with HttpxPolicyTransport(
        endpoint=endpoint,
        max_connections=connection_limit,
        max_keepalive_connections=connection_limit,
        keepalive_expiry_seconds=10,
    ) as transport:
        return await _fresh_sequence(
            endpoint, transport, requests=requests, concurrency=concurrency
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=_DEFAULT_REQUESTS)
    parser.add_argument("--rounds", type=int, default=_DEFAULT_ROUNDS)
    arguments = parser.parse_args()
    try:
        return run_exercise(requests=arguments.requests, rounds=arguments.rounds)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"exercise failed: {type(error).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
