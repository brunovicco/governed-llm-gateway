"""Default-compatible opt-in ownership, no-secret gates and verified local TLS regressions."""

import asyncio
import json
from collections.abc import Iterator, Mapping
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import httpx
import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient
from governed_llm_gateway_api import policy_router_lifecycle as lifecycle_module
from governed_llm_gateway_api import server as server_module
from governed_llm_gateway_api.application_bootstrap import bootstrap_governed_application_services
from governed_llm_gateway_api.deployment_activation import activate_governed_deployment
from governed_llm_gateway_api.policy_router_lifecycle import (
    PolicyRouterHttpPoolSettings,
    PolicyRouterPoolLifecycle,
    PolicyRouterPoolLifecycleError,
    prepare_policy_router_pool,
)
from governed_llm_gateway_api.process_health import attach_process_health_routes
from governed_llm_gateway_api.server import (
    GovernedServerSettings,
    UvicornServerRunner,
    parse_server_args,
    run_governed_server,
)
from governed_llm_gateway_core.adapters.policy_router import (
    PolicyHttpResponse,
    PolicyRouterHttpAdapter,
    PolicyTransportFailure,
)
from governed_llm_gateway_core.adapters.policy_router_httpx import HttpxPolicyTransport
from governed_llm_gateway_core.adapters.policy_router_runtime import (
    PolicyRouterRuntimeConfig,
    build_policy_router_adapter,
)
from governed_llm_gateway_core.application import PolicyProjectionDefaults
from governed_llm_gateway_core.application.policy import PolicyAuthorizationDecision
from test_gateway_server import _deployment, _static_argv
from test_governed_application_bootstrap import _paths, _secrets

from scripts.pdp_transport_comparison import SYNTHETIC_KEYS, LocalTlsPdp, fixture_metadata

ENDPOINT = "https://policy.example/route"


class Backend:
    def __init__(self) -> None:
        self.entered = 0
        self.closed = 0
        self.calls: list[dict[str, object]] = []
        self.enter_error = False
        self.close_error = False
        self.enter_stall = False
        self.enter_started = asyncio.Event()

    async def __aenter__(self) -> "Backend":
        self.entered += 1
        self.enter_started.set()
        if self.enter_error:
            raise RuntimeError("raw startup secret")
        if self.enter_stall:
            await asyncio.Event().wait()
        return self

    async def aclose(self) -> None:
        self.closed += 1
        if self.close_error:
            raise OSError("raw shutdown secret")

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> PolicyHttpResponse:
        self.calls.append(dict(payload))
        return PolicyHttpResponse(status_code=403, retry_after=None, payload=None)


def backend_fixture(monkeypatch: pytest.MonkeyPatch, backend: Backend) -> list[dict[str, object]]:
    constructions: list[dict[str, object]] = []

    def factory(**kwargs: object) -> Backend:
        constructions.append(kwargs)
        return backend

    monkeypatch.setattr(lifecycle_module, "HttpxPolicyTransport", factory)
    return constructions


async def post(owner: PolicyRouterPoolLifecycle) -> PolicyHttpResponse:
    return await owner.post_json(url=ENDPOINT, headers={}, payload={}, timeout_seconds=5)


@pytest.mark.parametrize(
    "maximum,idle,expiry",
    [
        (0, 0, 30),
        (65, 1, 30),
        (True, 1, 30),
        (8, -1, 30),
        (8, 9, 30),
        (8, True, 30),
        (8, 8, 0),
        (8, 8, float("nan")),
        (8, 8, float("inf")),
        (8, 8, 301),
        (8, 8, 10**1000),
    ],
)
def test_settings_limits_fail_before_resource_creation(
    maximum: int, idle: int, expiry: float
) -> None:
    with pytest.raises(ValueError):
        PolicyRouterHttpPoolSettings(
            max_connections=maximum, max_keepalive_connections=idle, keepalive_expiry_seconds=expiry
        )


@pytest.mark.parametrize("endpoint", [None, "http://127.0.0.1/route"])
def test_disabled_or_plaintext_selection_fails_before_all_secrets(
    tmp_path: Path,
    endpoint: str | None,
) -> None:
    paths = _paths(tmp_path)
    policy_path = paths.process.policy_router_path
    payload = json.loads(policy_path.read_text())
    payload["endpoint"] = endpoint
    if endpoint is None:
        payload["enabled"] = False
        payload["bindings"] = []
        clients = json.loads(paths.process.client_auth_path.read_text())
        clients["bindings"] = []
        paths.process.client_auth_path.write_text(json.dumps(clients))
    policy_path.write_text(json.dumps(payload))
    client, policy, provider, events = _secrets()
    with pytest.raises(ValueError):
        bootstrap_governed_application_services(
            paths,
            client_secrets=client,
            policy_router_secrets=policy,
            provider_secrets=provider,
            defaults=PolicyProjectionDefaults(max_latency_ms=5000, max_cost_usd=Decimal("1")),
            policy_router_pool=PolicyRouterHttpPoolSettings(),
        )
    assert events == []


def test_invalid_selection_and_contradictory_injection_read_no_secrets(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    client, policy, provider, events = _secrets()
    for selected, borrowed in [
        (cast(PolicyRouterHttpPoolSettings, True), None),
        (PolicyRouterHttpPoolSettings(), Backend()),
    ]:
        with pytest.raises((TypeError, ValueError)):
            bootstrap_governed_application_services(
                paths,
                client_secrets=client,
                policy_router_secrets=policy,
                provider_secrets=provider,
                defaults=PolicyProjectionDefaults(max_latency_ms=5000, max_cost_usd=Decimal("1")),
                policy_router_pool=selected,
                policy_router_transport=borrowed,
            )
        assert events == []


def test_owner_and_readiness_require_one_started_lifetime(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = Backend()
    constructions = backend_fixture(monkeypatch, backend)
    owner = PolicyRouterPoolLifecycle(endpoint=ENDPOINT, settings=PolicyRouterHttpPoolSettings())
    app = FastAPI(lifespan=owner.lifespan)
    attach_process_health_routes(app, readiness=owner.ready)
    assert constructions == [] and not owner.ready()

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://test"
        ) as client:
            assert (await client.get("/livez")).status_code == 200
            assert (await client.get("/readyz")).status_code == 503
            with pytest.raises(PolicyTransportFailure):
                await post(owner)
            async with app.router.lifespan_context(app):
                assert owner.ready() and len(constructions) == 1
                assert backend.calls == []
                assert (await client.get("/readyz")).status_code == 200
                assert (await post(owner)).status_code == 403
            assert not owner.ready() and backend.closed == 1
            assert (await client.get("/readyz")).status_code == 503
            with pytest.raises(PolicyTransportFailure):
                await post(owner)
            with pytest.raises(PolicyRouterPoolLifecycleError, match="new application"):
                async with owner.lifespan(app):
                    pass

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "mode", ["constructor", "enter", "cancel", "body", "close", "body-and-close"]
)
def test_partial_startup_and_shutdown_preserve_primary_and_close_owned_backend(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    backend = Backend()
    backend.enter_error = mode == "enter"
    backend.enter_stall = mode == "cancel"
    backend.close_error = mode in {"close", "body-and-close"}
    backend_fixture(monkeypatch, backend)
    if mode == "constructor":

        def broken(**kwargs: object) -> Backend:
            raise OSError("raw constructor secret")

        monkeypatch.setattr(lifecycle_module, "HttpxPolicyTransport", broken)
    owner = PolicyRouterPoolLifecycle(endpoint=ENDPOINT, settings=PolicyRouterHttpPoolSettings())

    async def scenario() -> None:
        async def life() -> None:
            async with owner.lifespan(FastAPI()):
                if mode in {"body", "body-and-close"}:
                    raise LookupError("primary application failure")

        if mode == "cancel":
            task = asyncio.create_task(life())
            await backend.enter_started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif mode in {"body", "body-and-close"}:
            with pytest.raises(LookupError, match="primary application"):
                await life()
        else:
            with pytest.raises(PolicyRouterPoolLifecycleError) as caught:
                await life()
            assert "secret" not in str(caught.value) and caught.value.__suppress_context__
        assert not owner.ready()
        assert backend.closed == (0 if mode == "constructor" else 1)

    asyncio.run(asyncio.wait_for(scenario(), 2))


def test_other_loop_cannot_use_or_report_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    backend_fixture(monkeypatch, Backend())
    owner = PolicyRouterPoolLifecycle(endpoint=ENDPOINT, settings=PolicyRouterHttpPoolSettings())

    async def foreign() -> None:
        assert not owner.ready()
        with pytest.raises(PolicyTransportFailure):
            await post(owner)

    async def scenario() -> None:
        async with owner.lifespan(FastAPI()):
            await asyncio.to_thread(lambda: asyncio.run(foreign()))

    asyncio.run(scenario())


def test_complete_app_owns_pool_but_default_and_borrowed_paths_do_not(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Backend()
    constructions = backend_fixture(monkeypatch, backend)
    paths = _paths(tmp_path)
    client, policy, provider, events = _secrets()
    defaults = PolicyProjectionDefaults(max_latency_ms=5000, max_cost_usd=Decimal("1"))
    services = bootstrap_governed_application_services(
        paths,
        client_secrets=client,
        policy_router_secrets=policy,
        provider_secrets=provider,
        defaults=defaults,
        policy_router_pool=PolicyRouterHttpPoolSettings(),
    )
    assert services.policy_router_lifecycle is not None and constructions == []
    payload = {
        "request_id": str(uuid4()),
        "workload": "rag.answer",
        "risk_level": "low",
        "data_classification": "public",
        "context_tokens_estimated": 10,
        "max_output_tokens_estimated": 10,
    }
    headers = {"X-Gateway-API-Key": "pc10-client-opaque"}
    inactive = TestClient(services.app).post("/v1/route/explain", json=payload, headers=headers)
    assert inactive.status_code == 503 and constructions == []
    with TestClient(services.app) as http:
        assert http.post("/v1/route/explain", json=payload, headers=headers).status_code == 403
        assert backend.calls[0]["data_classification"] == "confidential"
        assert "messages" not in backend.calls[0]
    assert backend.closed == 1
    assert (
        TestClient(services.app)
        .post("/v1/route/explain", json=payload, headers=headers)
        .status_code
        == 503
    )
    for borrowed in [None, Backend()]:
        other = bootstrap_governed_application_services(
            paths,
            client_secrets=client,
            policy_router_secrets=policy,
            provider_secrets=provider,
            defaults=defaults,
            policy_router_transport=borrowed,
        )
        assert other.policy_router_lifecycle is None
        with TestClient(other.app):
            pass
        if borrowed is not None:
            assert borrowed.closed == 0
    assert events[:3] == [
        "client:GATEWAY_CLIENT_A_KEY",
        "policy:POLICY_SERVICE_A_KEY",
        "provider:OPENAI_API_KEY",
    ]


@pytest.mark.integration
@pytest.mark.parametrize("shutdown_active", [False, True])
def test_owned_lifecycle_real_verified_tls_reuse_and_active_shutdown(
    monkeypatch: pytest.MonkeyPatch,
    shutdown_active: bool,
) -> None:
    async def scenario() -> None:
        async with LocalTlsPdp() as server:

            def factory(
                *,
                endpoint: str,
                max_connections: int,
                max_keepalive_connections: int,
                keepalive_expiry_seconds: float,
            ) -> HttpxPolicyTransport:
                return HttpxPolicyTransport(
                    endpoint=endpoint,
                    max_connections=max_connections,
                    max_keepalive_connections=max_keepalive_connections,
                    keepalive_expiry_seconds=keepalive_expiry_seconds,
                    ssl_context=server.client_context,
                )

            monkeypatch.setattr(lifecycle_module, "HttpxPolicyTransport", factory)
            owner = PolicyRouterPoolLifecycle(
                endpoint=server.endpoint,
                settings=PolicyRouterHttpPoolSettings(
                    max_connections=1, max_keepalive_connections=1
                ),
            )
            adapter = PolicyRouterHttpAdapter(
                endpoint=server.endpoint, api_keys_by_client=SYNTHETIC_KEYS, transport=owner
            )
            active: list[asyncio.Task[PolicyAuthorizationDecision]] = []
            async with owner.lifespan(FastAPI()):
                assert server.requests == [] and server.connections == 0
                decisions = [
                    await adapter.authorize(fixture_metadata(client))
                    for client in ["fixture-a", "fixture-b"]
                ]
                assert server.connections == 1 and len(server.requests) == 2
                assert decisions[0].provenance.decision_id != decisions[1].provenance.decision_id
                assert all("cookie" not in headers for _, headers in server.requests)
                if shutdown_active:
                    server.received.clear()
                    server.stall = True
                    active.append(asyncio.create_task(adapter.authorize(fixture_metadata())))
                    await server.received.wait()
                    active.append(asyncio.create_task(adapter.authorize(fixture_metadata())))
                    await asyncio.sleep(0)
            assert not owner.ready()
            for task in active:
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert len(server.requests) == (3 if shutdown_active else 2)

    asyncio.run(asyncio.wait_for(scenario(), 3))


def test_cli_pool_is_explicit_and_uvicorn_requires_lifespan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv = _static_argv(tmp_path.resolve())
    assert parse_server_args(argv).deployment.policy_router_pool is None
    assert (
        parse_server_args([*argv, "--pdp-http-pool"]).deployment.policy_router_pool
        == PolicyRouterHttpPoolSettings()
    )
    settings = parse_server_args(
        [
            *argv,
            "--pdp-http-pool",
            "--pdp-http-max-connections",
            "2",
            "--pdp-http-max-keepalive-connections",
            "1",
            "--pdp-http-keepalive-expiry-seconds",
            "10",
        ]
    )
    assert settings.deployment.policy_router_pool == PolicyRouterHttpPoolSettings(
        max_connections=2, max_keepalive_connections=1, keepalive_expiry_seconds=10
    )
    seen: list[dict[str, object]] = []

    def run(app: FastAPI, **kwargs: object) -> None:
        seen.append(kwargs)

    monkeypatch.setattr(uvicorn, "run", run)
    UvicornServerRunner(require_lifespan=True).run(FastAPI(), host="127.0.0.1", port=8000)
    assert seen[0]["lifespan"] == "on" and seen[0]["workers"] == 1


@pytest.mark.parametrize(
    "extra",
    [
        ["--pdp-http-max-connections", "2"],
        ["--pdp-http-pool", "--pdp-http-max-connections", "0"],
        ["--pdp-http-pool", "--pdp-http-keepalive-expiry-seconds", "nan"],
    ],
)
def test_invalid_cli_pool_rejected_before_activation(tmp_path: Path, extra: list[str]) -> None:
    with pytest.raises(ValueError):
        parse_server_args([*_static_argv(tmp_path.resolve()), *extra])


def test_deployment_validates_pool_type_before_artifacts(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        replace(
            _deployment(tmp_path.resolve()),
            policy_router_pool=cast(PolicyRouterHttpPoolSettings, True),
        )


def test_core_borrowed_transport_never_resolves_disabled_pdp() -> None:
    config = PolicyRouterRuntimeConfig(enabled=False, endpoint=None, timeout_seconds=5, bindings=())

    class Secrets:
        def resolve(self, reference: str) -> str:
            raise AssertionError("no secret access allowed")

    with pytest.raises(ValueError):
        build_policy_router_adapter(config, Secrets(), transport=Backend())
    assert prepare_policy_router_pool(config, None) is None


@pytest.mark.parametrize("injected_runner", [False, True])
def test_server_selects_lifespan_owner_and_local_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    injected_runner: bool,
) -> None:
    backend = Backend()
    backend_fixture(monkeypatch, backend)
    owner = PolicyRouterPoolLifecycle(endpoint=ENDPOINT, settings=PolicyRouterHttpPoolSettings())
    app = FastAPI(lifespan=owner.lifespan)
    seen: list[bool] = []

    def activate(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(app=app, policy_router_lifecycle=owner)

    class Runner:
        def __init__(self, *, require_lifespan: bool = False) -> None:
            seen.append(require_lifespan)

        def run(self, app: FastAPI, *, host: str, port: int) -> None:
            assert TestClient(app).get("/readyz").status_code == 503
            with TestClient(app) as client:
                assert client.get("/readyz").status_code == 200
                assert client.get("/livez").status_code == 200
            assert TestClient(app).get("/readyz").status_code == 503

    monkeypatch.setattr(server_module, "activate_governed_deployment", activate)
    monkeypatch.setattr(server_module, "UvicornServerRunner", Runner)
    settings = GovernedServerSettings(
        deployment=replace(
            _deployment(tmp_path.resolve()), policy_router_pool=PolicyRouterHttpPoolSettings()
        )
    )
    runner = Runner() if injected_runner else None
    run_governed_server(settings, environ={}, runner=runner)
    assert seen == [not injected_runner]
    assert backend.entered == backend.closed == 1 and backend.calls == []


def test_activation_rejects_plaintext_pool_before_environment_reads(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    payload = json.loads(paths.process.policy_router_path.read_text())
    payload["endpoint"] = "http://127.0.0.1/route"
    paths.process.policy_router_path.write_text(json.dumps(payload))
    settings = replace(
        _deployment(tmp_path.resolve()),
        model_registry_path=paths.process.model_registry_path,
        provider_runtime_path=paths.process.provider_runtime_path,
        client_auth_path=paths.process.client_auth_path,
        policy_router_path=paths.process.policy_router_path,
        ranking_policy_path=paths.ranking_policy_path,
        policy_router_pool=PolicyRouterHttpPoolSettings(),
    )

    class Environment(Mapping[str, str]):
        def __init__(self) -> None:
            self.reads: list[str] = []

        def __getitem__(self, key: str) -> str:
            self.reads.append(key)
            raise AssertionError("no environment secret reads permitted")

        def __iter__(self) -> Iterator[str]:
            return iter(())

        def __len__(self) -> int:
            return 0

    environ = Environment()
    with pytest.raises(ValueError, match="HTTPS"):
        activate_governed_deployment(settings, environ=environ)
    assert environ.reads == []


def test_factories_prepare_distinct_per_application_owners(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructions = backend_fixture(monkeypatch, Backend())
    paths = _paths(tmp_path)
    client, policy, provider, _ = _secrets()
    owners = [
        bootstrap_governed_application_services(
            paths,
            client_secrets=client,
            policy_router_secrets=policy,
            provider_secrets=provider,
            defaults=PolicyProjectionDefaults(max_latency_ms=5000, max_cost_usd=Decimal("1")),
            policy_router_pool=PolicyRouterHttpPoolSettings(),
        ).policy_router_lifecycle
        for _ in range(2)
    ]
    assert owners[0] is not owners[1] and all(owner is not None for owner in owners)
    assert constructions == []
