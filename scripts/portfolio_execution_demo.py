"""Run five credential-free execution scenarios through the real Gateway and Policy Router.

The fixture issuer and providers in this module are local demonstration components only. The
Policy Model Router container is built from the exact reviewed commit in
``config/composition-proof/router.commit``; no serving defaults or user profile artifacts change.
"""

import argparse
import asyncio
import json
import os
import secrets
import shutil
import socket

# Docker Compose arguments are constructed from repository paths and generated project IDs below.
import subprocess  # nosec B404
import sys
import tempfile
import threading
import time
from collections import Counter
from collections.abc import AsyncGenerator
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import uuid4

import httpx
import uvicorn
import yaml  # type: ignore[import-untyped]
from fastapi.testclient import TestClient
from governed_llm_gateway_api import (
    GovernedProcessBootstrapPaths,
    bootstrap_governed_process_runtime,
    compose_governed_gateway_services,
)
from governed_llm_gateway_api.service_composition import GovernedGatewayServices
from governed_llm_gateway_contracts import DataClassification
from governed_llm_gateway_core.adapters import PolicyRouterHttpAdapter
from governed_llm_gateway_core.application import PolicyProjectionDefaults
from governed_llm_gateway_core.application.policy import PolicyDecisionPort
from governed_llm_gateway_core.application.provider import (
    PreparedProviderStream,
    ProviderContentDelta,
    ProviderError,
    ProviderErrorCode,
    ProviderFeatureSupport,
    ProviderPort,
    ProviderRequest,
    ProviderResponse,
    ProviderResponseCompleted,
    ProviderResponseStarted,
    ProviderStreamEvent,
    ProviderUsage,
    ProviderUsageCompleted,
)
from governed_llm_gateway_core.application.resilience import StaticProviderResolver
from governed_llm_gateway_core.domain.ranking import (
    RankingPolicy,
    RankingWeights,
    StaticDeploymentScore,
    WorkloadRankingPolicy,
)
from governed_llm_gateway_core.domain.resilience import RetryPolicy

from scripts import composition_fixture
from scripts.composition_pin import verify_router_revision
from scripts.demo_authorization import DemoAuthorizationAdapter
from scripts.demo_pdp_https import LocalVerifiedHttpsProxy

_ROOT = Path(__file__).resolve().parents[1]
_COMPOSE_FILE = _ROOT / "compose.pdp-composition.yml"
_ROUTER_PATH = Path(
    os.environ.get("POLICY_MODEL_ROUTER_PATH", str(_ROOT.parent / "policy-model-router"))
)
_PRIMARY = "demo-reasoning-primary"
_SECONDARY = "demo-reasoning-secondary"
_UNAUTHORIZED = "demo-fast-unauthorized"
_MODEL_IDS = {
    _PRIMARY: "nvidia/demo-reasoning-primary",
    _SECONDARY: "nvidia/demo-reasoning-secondary",
    _UNAUTHORIZED: "nvidia/demo-fast-unauthorized",
}
_GATEWAY_KEY = secrets.token_urlsafe(32)
_PDP_API_KEY = secrets.token_urlsafe(32)
_PROVIDER_API_KEY = secrets.token_urlsafe(32)


class _DemoSecrets:
    def resolve(self, reference: str) -> str:
        if reference == "DEMO_GATEWAY_KEY":
            return _GATEWAY_KEY
        if reference == composition_fixture.API_KEY_ENV_REFERENCE:
            return _PDP_API_KEY
        return _PROVIDER_API_KEY


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    name: str
    passed: bool
    observed: str
    event_counts: dict[str, int]
    provider_calls: dict[str, int]
    digests: dict[str, str]


class _SimulatedProvider:
    """Conspicuous in-memory stream fixture with scenario-specific deterministic behavior."""

    feature_support = ProviderFeatureSupport(native_streaming=True, streaming_usage=True)

    def __init__(self) -> None:
        self.scenario = "success"
        self.calls: Counter[str] = Counter()
        self.closed: Counter[str] = Counter()

    def prepare_stream(self, request: ProviderRequest) -> PreparedProviderStream:
        model = request.model
        return PreparedProviderStream(request, lambda: self._stream(model))

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        del request
        raise RuntimeError("portfolio provider fixture only supports normalized streaming")

    def stream(self, request: ProviderRequest) -> AsyncGenerator[ProviderStreamEvent]:
        return self.prepare_stream(request).stream()

    async def _stream(self, model: str) -> AsyncGenerator[ProviderStreamEvent]:
        self.calls[model] += 1
        try:
            yield ProviderResponseStarted(response_id="simulated-response")
            if self.scenario == "retry" and model == _MODEL_IDS[_PRIMARY]:
                raise ProviderError(
                    provider="nvidia",
                    code=ProviderErrorCode.UNAVAILABLE,
                    message="simulated retryable failure",
                    retryable=True,
                )
            yield ProviderContentDelta(delta="simulated output")
            if self.scenario == "partial-failure":
                raise ProviderError(
                    provider="nvidia",
                    code=ProviderErrorCode.UNAVAILABLE,
                    message="simulated failure after output",
                    retryable=True,
                )
            if self.scenario == "cancel":
                await asyncio.Event().wait()
            yield ProviderUsageCompleted(ProviderUsage(input_tokens=12, output_tokens=3))
            yield ProviderResponseCompleted(response_id="simulated-response", finish_reason="stop")
        finally:
            self.closed[model] += 1


def _fixture_documents(directory: Path, endpoint: str) -> GovernedProcessBootstrapPaths:
    """Create isolated runtime artifacts validated by the production bootstrap loaders."""
    common = {
        "provider": "nvidia",
        "api_family": "openai-compatible",
        "capabilities": {
            "text": True,
            "vision": False,
            "tool_calling": False,
            "structured_output": False,
            "streaming": True,
        },
        "context_tokens": 64_000,
        "modalities": ["text"],
        "pricing": {
            "input_usd_per_million_tokens": "1.00",
            "output_usd_per_million_tokens": "2.00",
            "source_date": date.today().isoformat(),
            "snapshot_version": "portfolio-demo-v1",
        },
        "max_data_classification": "confidential",
        "allowed_environments": ["development"],
        "enabled": True,
        "source_date": date.today().isoformat(),
        "catalog_version": "portfolio-demo-v1",
    }
    registry = {
        "schema_version": "1.0",
        "catalog_version": "portfolio-demo-v1",
        "source_date": date.today().isoformat(),
        "deployments": {
            _PRIMARY: {
                **common,
                "model_id": _MODEL_IDS[_PRIMARY],
                "model_group": "reasoning-medium",
            },
            _SECONDARY: {
                **common,
                "model_id": _MODEL_IDS[_SECONDARY],
                "model_group": "reasoning-medium",
            },
            _UNAUTHORIZED: {
                **common,
                "model_id": _MODEL_IDS[_UNAUTHORIZED],
                "model_group": "fast-small",
            },
        },
    }
    (directory / "registry.yaml").write_text(
        yaml.safe_dump(registry, sort_keys=False), encoding="utf-8"
    )
    (directory / "provider-runtime.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "config_version": "portfolio-demo-v1",
                "bindings": [
                    {
                        "provider": "nvidia",
                        "api_family": "openai-compatible",
                        "credential_reference": "DEMO_PROVIDER_KEY",
                        "endpoint": "https://simulator.invalid/v1/chat/completions",
                        "openai_compatible": {
                            "max_tokens_field": "max_tokens",
                            "supports_native_structured_output": False,
                            "supports_native_tool_calling": False,
                            "supports_streaming": True,
                            "supports_stream_usage": True,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (directory / "client-auth.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "config_version": "portfolio-demo-v1",
                "bindings": [
                    {
                        "client_id": composition_fixture.CLIENT_ID,
                        "environment": composition_fixture.ENVIRONMENT,
                        "credential_reference": "DEMO_GATEWAY_KEY",
                        "allowed_workloads": [composition_fixture.WORKLOAD],
                        "minimum_risk_level": composition_fixture.RISK_TIER,
                        "minimum_data_classification": composition_fixture.DATA_CLASSIFICATION,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (directory / "policy-router.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "config_version": "portfolio-demo-v1",
                "enabled": True,
                "endpoint": endpoint,
                "timeout_seconds": 5.0,
                "bindings": [
                    {
                        "client_id": composition_fixture.CLIENT_ID,
                        "credential_reference": composition_fixture.API_KEY_ENV_REFERENCE,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return GovernedProcessBootstrapPaths(
        model_registry_path=directory / "registry.yaml",
        provider_runtime_path=directory / "provider-runtime.json",
        client_auth_path=directory / "client-auth.json",
        policy_router_path=directory / "policy-router.json",
    )


def _ranking() -> RankingPolicy:
    weights = RankingWeights(
        quality=Decimal("0.40"),
        reliability=Decimal("0.20"),
        latency=Decimal("0.15"),
        cost=Decimal("0.10"),
        availability=Decimal("0.15"),
    )
    scores = (
        StaticDeploymentScore(
            _PRIMARY,
            Decimal("0.90"),
            Decimal("0.90"),
            Decimal("0.8"),
            Decimal("0.7"),
            Decimal("0.95"),
            900,
        ),
        StaticDeploymentScore(
            _SECONDARY,
            Decimal("0.82"),
            Decimal("0.88"),
            Decimal("0.7"),
            Decimal("0.8"),
            Decimal("0.94"),
            1100,
        ),
        # Deliberately attractive but outside the Policy Router's authorized model group.
        StaticDeploymentScore(
            _UNAUTHORIZED,
            Decimal("1.0"),
            Decimal("1.0"),
            Decimal("1.0"),
            Decimal("1.0"),
            Decimal("1.0"),
            100,
        ),
    )
    return RankingPolicy(
        schema_version="1.0",
        policy_version="portfolio-demo-v1",
        score_snapshot_id="portfolio-demo-v1",
        source_date=date.today(),
        workloads=(WorkloadRankingPolicy(composition_fixture.WORKLOAD, weights, scores),),
    )


def _payload(*, data_classification: str = "confidential") -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "request_id": str(uuid4()),
        "workload": composition_fixture.WORKLOAD,
        "risk_level": composition_fixture.RISK_TIER,
        "data_classification": data_classification,
        "stream": True,
        "requirements": {"tool_calling": False, "structured_output": False},
        "limits": {
            "max_latency_ms": composition_fixture.MAX_LATENCY_MS,
            "max_cost_usd": str(
                Decimal(composition_fixture.MAX_COST_USD_MICROS) / Decimal(1_000_000)
            ),
        },
        "messages": [{"role": "user", "content": "portfolio execution fixture"}],
        "context_tokens_estimated": composition_fixture.CONTEXT_TOKENS_ESTIMATED,
        "max_output_tokens": composition_fixture.MAX_OUTPUT_TOKENS_ESTIMATED,
    }


def _event_types(body: str) -> list[str]:
    return [
        line.removeprefix("event: ") for line in body.splitlines() if line.startswith("event: ")
    ]


def _build_services(
    directory: Path, endpoint: str, provider: _SimulatedProvider
) -> GovernedGatewayServices:
    directory.mkdir(parents=True, exist_ok=True)
    paths = _fixture_documents(directory, endpoint)
    runtime = bootstrap_governed_process_runtime(
        paths,
        client_secrets=_DemoSecrets(),
        policy_router_secrets=_DemoSecrets(),
        provider_secrets=_DemoSecrets(),
    )
    if runtime.policy_router_adapter is None:
        raise RuntimeError("demo requires a real Policy Model Router adapter")
    runtime = replace(
        runtime,
        policy_router_adapter=cast(
            PolicyRouterHttpAdapter | None,
            DemoAuthorizationAdapter(cast(PolicyDecisionPort, runtime.policy_router_adapter)),
        ),
        provider_resolver=StaticProviderResolver(
            {("nvidia", "openai-compatible"): cast(ProviderPort, provider)}
        ),
    )
    return compose_governed_gateway_services(
        runtime,
        ranking_policy=_ranking(),
        defaults=PolicyProjectionDefaults(
            max_latency_ms=composition_fixture.MAX_LATENCY_MS,
            max_cost_usd=Decimal(composition_fixture.MAX_COST_USD_MICROS) / Decimal(1_000_000),
        ),
        retry_policy=RetryPolicy(
            max_attempts_per_deployment=2,
            max_fallbacks=1,
            base_delay_seconds=0,
            max_delay_seconds=0,
            jitter_ratio=0,
        ),
    )


def _provider_calls(provider: _SimulatedProvider) -> dict[str, int]:
    return {
        deployment_id: provider.calls[_MODEL_IDS[deployment_id]]
        for deployment_id in (_PRIMARY, _SECONDARY, _UNAUTHORIZED)
    }


def _events(body: str) -> dict[str, int]:
    return dict(Counter(_event_types(body)))


def _digests(services: GovernedGatewayServices) -> dict[str, str]:
    return {
        "model_registry": services.operations_read_model._registry.digest,
        "ranking_policy": services.operations_read_model._ranking_policy.digest,
    }


def _scenario(
    name: str,
    behavior: str,
    directory: Path,
    endpoint: str,
) -> ScenarioResult:
    provider = _SimulatedProvider()
    provider.scenario = behavior
    services = _build_services(directory, endpoint, provider)
    headers = {"X-Gateway-API-Key": _GATEWAY_KEY}

    if name == "authorized-success":
        response = TestClient(services.app).post("/v1/generate", headers=headers, json=_payload())
        event_types = _event_types(response.text)
        event_counts = _events(response.text)
        calls = _provider_calls(provider)
        passed = (
            response.status_code == 200
            and event_types.count("usage.completed") == 1
            and event_types.index("usage.completed") < event_types.index("response.completed")
            and calls[_PRIMARY] == 1
            and calls[_SECONDARY] == 0
            and calls[_UNAUTHORIZED] == 0
            and f'"deployment":"{_PRIMARY}"' in response.text
            and '"authorized_model_group":"reasoning-medium"' in response.text
        )
        return ScenarioResult(
            name,
            passed,
            f"HTTP {response.status_code}; selected {_PRIMARY}",
            event_counts,
            calls,
            _digests(services),
        )

    if name == "policy-denial":
        response = TestClient(services.app).post(
            "/v1/generate",
            headers=headers,
            json=_payload(data_classification=DataClassification.RESTRICTED.value),
        )
        calls = _provider_calls(provider)
        passed = response.status_code in {403, 422} and not any(calls.values())
        return ScenarioResult(
            name,
            passed,
            f"HTTP {response.status_code}; zero provider calls",
            {},
            calls,
            _digests(services),
        )

    if name == "pre-output-retry-fallback":
        response = TestClient(services.app).post("/v1/generate", headers=headers, json=_payload())
        event_types = _event_types(response.text)
        calls = _provider_calls(provider)
        passed = (
            response.status_code == 200
            and event_types[-1:] == ["response.completed"]
            and calls == {_PRIMARY: 2, _SECONDARY: 1, _UNAUTHORIZED: 0}
            and f'"deployment":"{_SECONDARY}"' in response.text
            and '"authorized_model_group":"reasoning-medium"' in response.text
        )
        return ScenarioResult(
            name,
            passed,
            "two primary attempts then authorized fallback",
            _events(response.text),
            calls,
            _digests(services),
        )

    if name == "post-output-terminal-failure":
        response = TestClient(services.app).post("/v1/generate", headers=headers, json=_payload())
        event_types = _event_types(response.text)
        calls = _provider_calls(provider)
        passed = (
            response.status_code == 200
            and event_types.count("response.failed") == 1
            and "response.completed" not in event_types
            and calls == {_PRIMARY: 1, _SECONDARY: 0, _UNAUTHORIZED: 0}
        )
        return ScenarioResult(
            name,
            passed,
            "partial output ended without replay or completion",
            _events(response.text),
            calls,
            _digests(services),
        )

    if name == "client-cancellation":
        return _cancel_over_loopback(services, provider)
    raise ValueError("unknown portfolio execution scenario")


def _cancel_over_loopback(
    services: GovernedGatewayServices, provider: _SimulatedProvider
) -> ScenarioResult:
    """Disconnect a real HTTP client after content and verify upstream closure without failure."""
    server = uvicorn.Server(
        uvicorn.Config(services.app, log_level="critical", access_log=False, lifespan="off")
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    port = listener.getsockname()[1]
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    observed_events: list[str] = []
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        if not server.started:
            return ScenarioResult(
                "client-cancellation",
                False,
                "Gateway listener did not start",
                {},
                _provider_calls(provider),
                _digests(services),
            )
        with (
            httpx.Client(timeout=10) as client,
            client.stream(
                "POST",
                f"http://127.0.0.1:{port}/v1/generate",
                headers={"X-Gateway-API-Key": _GATEWAY_KEY},
                json=_payload(),
            ) as response,
        ):
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line.startswith("event: "):
                        event = line.removeprefix("event: ")
                        observed_events.append(event)
                        if event == "content.delta":
                            break
        close_deadline = time.monotonic() + 3
        while provider.closed[_MODEL_IDS[_PRIMARY]] == 0 and time.monotonic() < close_deadline:
            time.sleep(0.02)
        health = asyncio.run(services.health.snapshot(_PRIMARY))
        calls = _provider_calls(provider)
        passed = (
            calls == {_PRIMARY: 1, _SECONDARY: 0, _UNAUTHORIZED: 0}
            and provider.closed[_MODEL_IDS[_PRIMARY]] == 1
            and health.transient_failure_count == 0
            and "content.delta" in observed_events
        )
        return ScenarioResult(
            "client-cancellation",
            passed,
            "client disconnected after content; upstream closed without provider failure",
            dict(Counter(observed_events)),
            calls,
            _digests(services),
        )
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_router(port: int, timeout_seconds: float = 90.0) -> None:
    import http.client

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        try:
            connection.request("GET", "/health")
            if connection.getresponse().status == 200:
                return
        except OSError:
            pass
        finally:
            connection.close()
        time.sleep(1)
    raise RuntimeError("Policy Model Router readiness timed out")


def _teardown_compose(base: list[str]) -> bool:
    """Stop the isolated PDP stack and verify Compose reports no remaining containers."""
    docker_executable = shutil.which("docker")
    if docker_executable is None:
        return False
    command_base = [docker_executable, *base[1:]]
    try:
        stopped = subprocess.run(
            [*command_base, "down", "--volumes", "--remove-orphans"],
            cwd=_ROOT,
            capture_output=True,
            check=False,
            timeout=90,
        )  # nosec B603
    except (OSError, subprocess.SubprocessError):
        return False
    if stopped.returncode != 0:
        return False
    try:
        remaining_containers = subprocess.run(
            [*command_base, "ps", "--all", "--quiet"],
            cwd=_ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )  # nosec B603
        project_index = base.index("-p")
        project_name = base[project_index + 1]
        label = f"label=com.docker.compose.project={project_name}"
        remaining_networks = subprocess.run(
            [docker_executable, "network", "ls", "--quiet", "--filter", label],
            cwd=_ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )  # nosec B603
        remaining_volumes = subprocess.run(
            [docker_executable, "volume", "ls", "--quiet", "--filter", label],
            cwd=_ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=15,
        )  # nosec B603
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return False
    return (
        remaining_containers.returncode == 0
        and remaining_networks.returncode == 0
        and remaining_volumes.returncode == 0
        and not remaining_containers.stdout.strip()
        and not remaining_networks.stdout.strip()
        and not remaining_volumes.stdout.strip()
    )


def _compose_document(port: int, key_path: Path, router_api_key: str) -> Path:
    document = yaml.safe_load(_COMPOSE_FILE.read_text(encoding="utf-8"))
    router = document["services"]["policy-model-router"]
    router["ports"] = [f"127.0.0.1:{port}:8000"]
    router["environment"]["API_KEYS"] = json.dumps(
        {composition_fixture.CLIENT_ID: router_api_key}, separators=(",", ":")
    )
    key_target = "/etc/policy-model-router/runtime-authorization-keys.json"
    volumes = router["volumes"]
    for index, volume in enumerate(volumes):
        if len(volume.split(":")) > 1 and volume.split(":")[1] == key_target:
            volumes[index] = f"{key_path}:{key_target}:ro"
            break
    else:
        raise RuntimeError("Policy Router Compose file is missing its runtime key-set mount")
    descriptor, temporary_name = tempfile.mkstemp(prefix="gateway-demo-compose-", suffix=".yaml")
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return temporary


def run_demo() -> int:
    """Start an isolated pinned PDP stack, run five assertions and always tear it down."""
    revision = verify_router_revision(_ROUTER_PATH)
    project_name = f"gateway-portfolio-demo-{uuid4().hex[:10]}"
    port = _free_loopback_port()
    outcomes: list[ScenarioResult] = []
    with tempfile.TemporaryDirectory(prefix="gateway-portfolio-demo-") as temporary_dir:
        temporary = Path(temporary_dir)
        keys = temporary / "runtime-authorization-keys.json"
        keys.write_text(
            json.dumps(composition_fixture.trusted_key_set(now=datetime.now(UTC))),
            encoding="utf-8",
        )
        compose_file = _compose_document(port, keys, _PDP_API_KEY)
        old_router_path = os.environ.get("POLICY_MODEL_ROUTER_PATH")
        os.environ["POLICY_MODEL_ROUTER_PATH"] = str(_ROUTER_PATH)
        base = [
            "docker",
            "compose",
            "--project-directory",
            str(_ROOT),
            "-p",
            project_name,
            "-f",
            str(compose_file),
        ]
        try:
            # Security-reviewed fixed arguments, isolated project and fixture-only key material.
            started = subprocess.run(
                [*base, "up", "-d", "--build"],
                cwd=_ROOT,
                capture_output=True,
                check=False,
                timeout=300,
            )  # nosec B603
            if started.returncode != 0:
                print("FAIL  Policy Router Compose startup failed", file=sys.stderr)
                return 2
            _wait_router(port)
            with LocalVerifiedHttpsProxy(upstream_port=port) as proxy:
                names = (
                    ("authorized-success", "success"),
                    ("policy-denial", "success"),
                    ("pre-output-retry-fallback", "retry"),
                    ("post-output-terminal-failure", "partial-failure"),
                    ("client-cancellation", "cancel"),
                )
                for name, behavior in names:
                    outcomes.append(_scenario(name, behavior, temporary / name, proxy.endpoint))
        finally:
            stopped = _teardown_compose(base)
            if old_router_path is None:
                os.environ.pop("POLICY_MODEL_ROUTER_PATH", None)
            else:
                os.environ["POLICY_MODEL_ROUTER_PATH"] = old_router_path
            compose_file.unlink(missing_ok=True)
            if not stopped:
                print("FAIL  Policy Router Compose cleanup failed", file=sys.stderr)
                outcomes.append(
                    ScenarioResult("teardown", False, "Compose containers remain", {}, {}, {})
                )

    print(f"Policy Model Router pinned revision: {revision}")
    print("Provider adapters: deterministic in-memory simulation")
    for result in outcomes:
        status = "PASS" if result.passed else "FAIL"
        print(
            f"{status}  {result.name}: {result.observed}; "
            f"events={json.dumps(result.event_counts, sort_keys=True)}; "
            f"provider_calls={json.dumps(result.provider_calls, sort_keys=True)}; "
            f"digests={json.dumps(result.digests, sort_keys=True)}"
        )
    return 0 if len(outcomes) == 5 and all(item.passed for item in outcomes) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    return run_demo()


if __name__ == "__main__":
    raise SystemExit(main())
