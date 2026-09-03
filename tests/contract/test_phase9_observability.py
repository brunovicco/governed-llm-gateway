import asyncio
import http.client
from collections.abc import AsyncIterator, Mapping
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from a2a_otel_kit import Observability, ObservabilitySettings
from governed_llm_gateway_contracts import (
    Capability,
    DataClassification,
    GatewayRequest,
    Message,
    MessageRole,
    Modality,
    PolicyProvenance,
    RiskLevel,
    RoutingProvenance,
)
from governed_llm_gateway_core.adapters.http_json import StdlibJsonTransport
from governed_llm_gateway_core.adapters.http_sse import HttpxSseTransport
from governed_llm_gateway_core.application.policy import (
    PolicyAuthorizationDecision,
    PolicyEnforcementService,
    PolicyProjectionDefaults,
    PolicyRequestMetadata,
)
from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)
from governed_llm_gateway_core.application.ranking import (
    RankedCandidate,
    RankingDecision,
    ScoreBreakdown,
)
from governed_llm_gateway_core.application.resilience import (
    InMemoryHealthTracker,
    ResilientExecutionService,
    StaticProviderResolver,
)
from governed_llm_gateway_core.application.telemetry import set_gateway_span_attributes
from governed_llm_gateway_core.domain.authorization import PolicyAuthorization
from governed_llm_gateway_core.domain.model_registry import (
    ModelDeployment,
    ModelRegistry,
    PricingMetadata,
)
from governed_llm_gateway_core.domain.resilience import RetryPolicy
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

REQUEST_ID = UUID("99999999-9999-4999-8999-999999999999")
TODAY = date(2026, 9, 3)
PROMPT_SECRET = "prompt-value-must-never-enter-telemetry"
COMPLETION_SECRET = "completion-value-must-never-enter-telemetry"
CREDENTIAL_SECRET = "credential-value-must-never-enter-telemetry"


def _observability() -> tuple[Observability, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    settings = ObservabilitySettings(
        service_name="governed-gateway-test",
        service_version="0.1.0",
        environment="test",
        enabled=False,
    )
    observability = Observability(
        settings=settings,
        tracer=provider.get_tracer(settings.service_name, settings.service_version),
        lifecycle=None,
    )
    return observability, exporter


def _deployment(deployment_id: str, provider: str) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider=provider,
        model_id=f"model/{deployment_id}",
        model_group="agentic-strong",
        api_family="openai-compatible",
        capabilities=frozenset({Capability.TEXT}),
        context_tokens=128_000,
        modalities=frozenset({Modality.TEXT}),
        pricing=PricingMetadata(
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("2"),
            source_date=TODAY,
            snapshot_version="pricing-v1",
        ),
        max_data_classification=DataClassification.INTERNAL,
        allowed_environments=frozenset({"development"}),
        enabled=True,
        source_date=TODAY,
        catalog_version="catalog-v1",
    )


def _registry(*deployments: ModelDeployment) -> ModelRegistry:
    return ModelRegistry(
        schema_version="1.0",
        catalog_version="catalog-v1",
        source_date=TODAY,
        deployments=deployments,
    )


def _request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        messages=(Message(role=MessageRole.USER, content=PROMPT_SECRET),),
    )


def _context() -> EffectivePolicyContext:
    return EffectivePolicyContext(
        client_id="client-a",
        environment="development",
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
    )


class AllowPolicy:
    async def authorize(self, request: PolicyRequestMetadata) -> PolicyAuthorizationDecision:
        return PolicyAuthorizationDecision(
            authorization=PolicyAuthorization(
                decision_id="policy-decision",
                authorized_model_groups=frozenset({"agentic-strong"}),
            ),
            provenance=PolicyProvenance(
                decision_id="policy-decision",
                policy_id="gateway-policy",
                policy_version="1.0.0",
                policy_digest="sha256:" + "a" * 64,
            ),
            decided_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
            reason="allowed",
            service_version="1.0.0",
            environment=request.environment,
        )


class SequenceProvider:
    def __init__(self, *results: ProviderResponse | ProviderError) -> None:
        self.results = list(results)
        self.calls: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        result = self.results.pop(0)
        if isinstance(result, ProviderError):
            raise result
        return result


def _rate_limit(provider: str) -> ProviderError:
    return ProviderError(
        provider=provider,
        code=ProviderErrorCode.RATE_LIMIT,
        message="remote text that must not be exported",
        retryable=True,
        status_code=429,
    )


def _ranked(deployment: ModelDeployment, score: str) -> RankedCandidate:
    value = Decimal(score)
    return RankedCandidate(
        deployment=deployment,
        score=ScoreBreakdown(
            quality=value,
            reliability=Decimal("0"),
            latency=Decimal("0"),
            cost=Decimal("0"),
            availability=Decimal("0"),
            total=value,
        ),
        estimated_cost_usd=Decimal("0.01"),
    )


def _decision(primary: ModelDeployment, fallback: ModelDeployment) -> RankingDecision:
    routing = RoutingProvenance(
        routing_decision_id="sha256:" + "b" * 64,
        policy=PolicyProvenance(
            decision_id="policy-decision",
            policy_id="gateway-policy",
            policy_version="1.0.0",
            policy_digest="sha256:" + "a" * 64,
        ),
        authorized_model_group="agentic-strong",
        model_registry_digest="c" * 64,
        ranking_policy_version="ranking-v1",
        ranking_policy_digest="d" * 64,
        score_snapshot_id="static-v1",
        provider=primary.provider,
        model=primary.model_id,
        deployment=primary.deployment_id,
    )
    return RankingDecision(
        routing=routing,
        ranking_policy_digest="d" * 64,
        score_snapshot_id="static-v1",
        selected=_ranked(primary, "1"),
        alternatives=(_ranked(fallback, "0.9"),),
        rejected_candidates=(),
    )


def _telemetry_repr(exporter: InMemorySpanExporter) -> str:
    material: list[object] = []
    for span in exporter.get_finished_spans():
        material.append(
            (
                span.name,
                dict(span.attributes or {}),
                tuple((event.name, dict(event.attributes or {})) for event in span.events),
            )
        )
    return repr(material)


def test_gateway_attribute_boundary_is_deny_by_default() -> None:
    observability, exporter = _observability()

    with observability.start_span("privacy", record_exception=False) as span:
        set_gateway_span_attributes(
            span,
            {
                "llm.workload": "agent.orchestration",
                "routing.decision_id": "sha256:" + "b" * 64,
                "prompt": PROMPT_SECRET,
                "completion": COMPLETION_SECRET,
                "tool.arguments": "must-not-survive",
                "authorization": f"Bearer {CREDENTIAL_SECRET}",
                "api_key": CREDENTIAL_SECRET,
            },
        )

    finished = exporter.get_finished_spans()[0]
    attributes = dict(finished.attributes or {})
    assert attributes["llm.workload"] == "agent.orchestration"
    assert "routing.decision_id" in attributes
    serialized = _telemetry_repr(exporter)
    assert PROMPT_SECRET not in serialized
    assert COMPLETION_SECRET not in serialized
    assert CREDENTIAL_SECRET not in serialized
    assert "tool.arguments" not in serialized


def test_policy_route_span_is_metadata_only() -> None:
    observability, exporter = _observability()
    deployment = _deployment("deployment-a", "provider-a")
    service = PolicyEnforcementService(AllowPolicy(), observability=observability)

    authorized = asyncio.run(
        service.authorize_candidates(
            _request(),
            _context(),
            _registry(deployment),
            context_tokens_estimated=10,
            max_output_tokens_estimated=20,
            defaults=PolicyProjectionDefaults(
                max_latency_ms=5000,
                max_cost_usd=Decimal("1"),
            ),
        )
    )

    assert authorized.candidates == (deployment,)
    policy_spans = [span for span in exporter.get_finished_spans() if span.name == "policy.route"]
    assert len(policy_spans) == 1
    attributes = dict(policy_spans[0].attributes or {})
    assert attributes["routing.policy_id"] == "gateway-policy"
    assert attributes["routing.model_group"] == "agentic-strong"
    assert PROMPT_SECRET not in _telemetry_repr(exporter)


def test_provider_attempts_keep_one_trace_and_emit_retry_and_fallback_events() -> None:
    observability, exporter = _observability()
    primary = _deployment("deployment-a", "provider-a")
    fallback = _deployment("deployment-b", "provider-b")
    primary_provider = SequenceProvider(_rate_limit("provider-a"), _rate_limit("provider-a"))
    fallback_provider = SequenceProvider(
        ProviderResponse(
            text=COMPLETION_SECRET,
            usage=ProviderUsage(input_tokens=11, output_tokens=3),
            finish_reason="stop",
        )
    )
    service = ResilientExecutionService(
        InMemoryHealthTracker(),
        StaticProviderResolver(
            {
                (primary.provider, primary.api_family): primary_provider,
                (fallback.provider, fallback.api_family): fallback_provider,
            }
        ),
        retry_policy=RetryPolicy(max_attempts_per_deployment=2, max_fallbacks=1),
        sleeper=_no_sleep,
        observability=observability,
    )

    with observability.start_span("llm.gateway.request", record_exception=False) as gateway_span:
        gateway_trace_id = gateway_span.get_span_context().trace_id
        result = asyncio.run(
            service.execute(
                _request(),
                _decision(primary, fallback),
                max_output_tokens=64,
            )
        )

    assert result.deployment.deployment_id == "deployment-b"
    provider_spans = [
        span for span in exporter.get_finished_spans() if span.name == "provider.inference"
    ]
    assert len(provider_spans) == 3
    assert {span.context.trace_id for span in provider_spans} == {gateway_trace_id}
    event_names = {event.name for span in provider_spans for event in span.events}
    assert "llm.gateway.retry" in event_names
    assert "llm.gateway.fallback" in event_names
    assert COMPLETION_SECRET not in _telemetry_repr(exporter)
    assert "remote text that must not be exported" not in _telemetry_repr(exporter)


async def _no_sleep(delay: float) -> None:
    assert delay >= 0


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, *chunks: bytes) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        return None


def test_sse_transport_injects_current_w3c_trace_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observability, _ = _observability()
    captured_traceparent: str | None = None
    original_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_traceparent
        captured_traceparent = request.headers.get("traceparent")
        return httpx.Response(200, stream=ChunkStream(b"data: {}\n\n"))

    transport = httpx.MockTransport(handler)

    def client_factory(*, timeout: httpx.Timeout) -> httpx.AsyncClient:
        return original_client(transport=transport, timeout=timeout)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)

    async def scenario() -> None:
        stream = await HttpxSseTransport().open_sse(
            url="https://provider.example/stream",
            headers={"authorization": f"Bearer {CREDENTIAL_SECRET}"},
            payload={"stream": True},
            timeout_seconds=1.0,
        )
        try:
            await anext(stream.__aiter__())
        finally:
            await stream.aclose()

    with observability.start_span("caller", record_exception=False) as span:
        expected_trace_id = f"{span.get_span_context().trace_id:032x}"
        asyncio.run(scenario())

    assert captured_traceparent is not None
    assert captured_traceparent.split("-")[1] == expected_trace_id
    assert CREDENTIAL_SECRET not in captured_traceparent


def test_json_transport_injects_context_across_to_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observability, _ = _observability()
    captured_headers: dict[str, str] = {}

    class FakeResponse:
        status = 200

        def read(self, amount: int) -> bytes:
            assert amount > 0
            return b'{"ok":true}'

        def getheaders(self) -> list[tuple[str, str]]:
            return []

    class FakeConnection:
        def __init__(self, host: str, *, port: int, timeout: float) -> None:
            assert host == "provider.example"
            assert port == 443
            assert timeout == 1.0

        def request(
            self,
            method: str,
            path: str,
            *,
            body: bytes,
            headers: Mapping[str, str],
        ) -> None:
            assert method == "POST"
            assert path == "/generate"
            assert body
            captured_headers.update(headers)

        def getresponse(self) -> FakeResponse:
            return FakeResponse()

        def close(self) -> None:
            return None

    monkeypatch.setattr(http.client, "HTTPSConnection", FakeConnection)

    with observability.start_span("caller", record_exception=False) as span:
        expected_trace_id = f"{span.get_span_context().trace_id:032x}"
        response = asyncio.run(
            StdlibJsonTransport().post_json(
                url="https://provider.example/generate",
                headers={"authorization": f"Bearer {CREDENTIAL_SECRET}"},
                payload={"input": "not-telemetry"},
                timeout_seconds=1.0,
            )
        )

    assert response.status_code == 200
    assert captured_headers["traceparent"].split("-")[1] == expected_trace_id
    assert captured_headers["authorization"] == f"Bearer {CREDENTIAL_SECRET}"
