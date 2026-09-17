"""Real cache coordinator with synthetic auth/PDP/providers and a controlled RESP store."""

import asyncio
from collections.abc import AsyncGenerator, Mapping
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import fakeredis.aioredis
import pytest
from governed_llm_gateway_api.client_auth import (
    EnvironmentGatewayClientSecretResolver,
    GatewayClientAuthBinding,
    StaticGatewayClientContextResolver,
    build_static_gateway_client_context_resolver,
)
from governed_llm_gateway_api.route_explain import ClientAuthenticationError
from governed_llm_gateway_api.stream_generate import (
    GenerateCoordinator,
    GenerateRequestModel,
    NoEligibleStreamingDeploymentError,
)
from governed_llm_gateway_contracts import (
    Capability,
    DataClassification,
    GatewayRequest,
    GatewayStreamEvent,
    Modality,
    RiskLevel,
)
from governed_llm_gateway_core.adapters.policy_router import (
    PolicyHttpResponse,
    PolicyRouterHttpAdapter,
)
from governed_llm_gateway_core.adapters.response_cache_redis import RedisResponseCache
from governed_llm_gateway_core.application.policy import (
    PolicyDecisionError,
    PolicyDecisionErrorCode,
    PolicyEnforcementService,
    PolicyProjectionDefaults,
)
from governed_llm_gateway_core.application.provider import (
    PreparedProviderStream,
    ProviderContentDelta,
    ProviderError,
    ProviderErrorCode,
    ProviderFeatureSupport,
    ProviderRequest,
    ProviderResponse,
    ProviderResponseCompleted,
    ProviderResponseStarted,
    ProviderStreamEvent,
    ProviderUsage,
    ProviderUsageCompleted,
)
from governed_llm_gateway_core.application.ranking import RouteExplainService
from governed_llm_gateway_core.application.resilience import (
    InMemoryHealthTracker,
    StaticProviderResolver,
)
from governed_llm_gateway_core.application.response_cache import CachedResponse
from governed_llm_gateway_core.application.streaming import StreamingExecutionService
from governed_llm_gateway_core.domain.model_registry import (
    ModelDeployment,
    ModelRegistry,
    PricingMetadata,
)
from governed_llm_gateway_core.domain.ranking import (
    RankingPolicy,
    RankingWeights,
    StaticDeploymentScore,
    WorkloadRankingPolicy,
)
from governed_llm_gateway_core.domain.resilience import CircuitBreakerPolicy
from governed_llm_gateway_core.domain.response_cache import (
    ResponseCacheIdentity,
    ResponseCachePolicy,
)
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext

_NOW = datetime(2026, 9, 17, tzinfo=UTC)
_KEY_A = "synthetic-client-a-credential"
_KEY_B = "synthetic-client-b-credential"
_KEY_PRIVATE = "synthetic-private-client-credential"
_PDP_KEY = "synthetic-pdp-credential"
_PROMPT = "synthetic exact-match public question"


class _ContextResolver:
    def __init__(self, resolver: StaticGatewayClientContextResolver, events: list[str]) -> None:
        self.resolver = resolver
        self.events = events

    async def resolve(self, *, api_key: str, request: GatewayRequest) -> EffectivePolicyContext:
        self.events.append("authenticate")
        return await self.resolver.resolve(api_key=api_key, request=request)


class _PolicyTransport:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.policy_digest = "sha256:" + "a" * 64
        self.status = 200
        self.requests: list[Mapping[str, object]] = []

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> PolicyHttpResponse:
        del url, headers, timeout_seconds
        self.events.append("pdp")
        self.requests.append(payload)
        if self.status != 200:
            return PolicyHttpResponse(status_code=self.status, retry_after=None, payload=None)
        return PolicyHttpResponse(
            status_code=200,
            retry_after=None,
            payload={
                "schema_version": "1.0",
                "routing_decision_id": f"decision-{len(self.requests)}",
                "decided_at": _NOW.isoformat().replace("+00:00", "Z"),
                "workflow_id": payload["workflow_id"],
                "task_id": payload["task_id"],
                "selected_model_group": "balanced",
                "reason": "synthetic workload authorization",
                "rejected_candidates": [],
                "policy_id": "synthetic-pdp-policy",
                "policy_version": "1.0.0",
                "policy_digest": self.policy_digest,
                "service_version": "test-v1",
                "environment": "development",
            },
        )


class _ObservedCache:
    def __init__(self, cache: RedisResponseCache, events: list[str]) -> None:
        self.cache = cache
        self.events = events
        self.reads: list[ResponseCacheIdentity] = []
        self.writes: list[ResponseCacheIdentity] = []

    async def get(self, identity: ResponseCacheIdentity) -> CachedResponse | None:
        self.events.append("cache.read")
        self.reads.append(identity)
        return await self.cache.get(identity)

    async def put(
        self, identity: ResponseCacheIdentity, response: CachedResponse, *, ttl_seconds: int
    ) -> None:
        self.events.append("cache.write")
        self.writes.append(identity)
        await self.cache.put(identity, response, ttl_seconds=ttl_seconds)


class _Provider:
    feature_support = ProviderFeatureSupport(native_streaming=True, streaming_usage=True)

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        del request
        raise AssertionError("streaming fixture only")

    def prepare_stream(self, request: ProviderRequest) -> PreparedProviderStream:
        self.events.append("preflight")
        return PreparedProviderStream(request=request, _factory=lambda: self.stream(request))

    async def stream(self, request: ProviderRequest) -> AsyncGenerator[ProviderStreamEvent]:
        self.events.append("provider")
        self.calls.append(request)
        response_id = f"synthetic-{len(self.calls)}"
        yield ProviderResponseStarted(response_id=response_id)
        yield ProviderContentDelta(delta=f"answer:{request.model}:{len(self.calls)}")
        yield ProviderUsageCompleted(usage=ProviderUsage(input_tokens=10, output_tokens=3))
        yield ProviderResponseCompleted(response_id=response_id, finish_reason="stop")


def _registry() -> ModelRegistry:
    first = ModelDeployment(
        deployment_id="deployment-a",
        provider="provider-a",
        model_id="provider-a/model-a",
        model_group="balanced",
        api_family="openai-compatible",
        capabilities=frozenset({Capability.TEXT, Capability.STREAMING}),
        context_tokens=8192,
        modalities=frozenset({Modality.TEXT}),
        pricing=PricingMetadata(
            input_usd_per_million_tokens=Decimal("1"),
            output_usd_per_million_tokens=Decimal("2"),
            source_date=_NOW.date(),
            snapshot_version="synthetic-pricing-v1",
        ),
        max_data_classification=DataClassification.CONFIDENTIAL,
        allowed_environments=frozenset({"development"}),
        enabled=True,
        source_date=_NOW.date(),
        catalog_version="synthetic-catalog-v1",
    )
    return ModelRegistry(
        schema_version="1.0",
        catalog_version="synthetic-catalog-v1",
        source_date=_NOW.date(),
        deployments=(
            first,
            replace(
                first,
                deployment_id="deployment-b",
                provider="provider-b",
                model_id="provider-b/model-b",
            ),
        ),
    )


def _ranking(registry: ModelRegistry) -> RankingPolicy:
    zero, one = Decimal("0"), Decimal("1")
    return RankingPolicy(
        schema_version="1.0",
        policy_version="synthetic-ranking-v1",
        score_snapshot_id="synthetic-static-v1",
        source_date=date(2026, 9, 17),
        workloads=(
            WorkloadRankingPolicy(
                workload="rag.answer",
                weights=RankingWeights(
                    quality=one, reliability=zero, latency=zero, cost=zero, availability=zero
                ),
                deployments=tuple(
                    StaticDeploymentScore(
                        deployment_id=deployment.deployment_id,
                        quality=one,
                        reliability=zero,
                        latency=zero,
                        cost=zero,
                        availability=zero,
                        expected_latency_ms=100,
                    )
                    for deployment in registry.deployments
                ),
            ),
        ),
    )


def _payload(
    index: int,
    *,
    agent_identity: str | None = None,
    classification: DataClassification = DataClassification.PUBLIC,
) -> GenerateRequestModel:
    return GenerateRequestModel.model_validate(
        {
            "request_id": str(UUID(int=index)),
            "workload": "rag.answer",
            "risk_level": "low",
            "data_classification": classification.value,
            "messages": [{"role": "user", "content": _PROMPT}],
            "context_tokens_estimated": 10,
            "max_output_tokens": 64,
            "agent_identity": agent_identity,
        }
    )


class _Harness:
    def __init__(self, *, cache_policy: ResponseCachePolicy | None = None) -> None:
        self.events: list[str] = []
        self.client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        self.cache = _ObservedCache(
            RedisResponseCache(self.client, prefix="synthetic"), self.events
        )
        self.provider = _Provider(self.events)
        self.transport = _PolicyTransport(self.events)
        self.health = InMemoryHealthTracker(
            CircuitBreakerPolicy(failure_threshold=1), clock=lambda: 0.0
        )
        registry = _registry()
        bindings = tuple(
            GatewayClientAuthBinding(
                client_id=client_id,
                environment="development",
                credential_reference=reference,
                allowed_workloads=("rag.answer",),
                minimum_risk_level=RiskLevel.LOW,
                minimum_data_classification=classification,
            )
            for client_id, reference, classification in (
                ("client-a", "CLIENT_A", DataClassification.PUBLIC),
                ("client-b", "CLIENT_B", DataClassification.PUBLIC),
                ("client-private", "CLIENT_PRIVATE", DataClassification.CONFIDENTIAL),
            )
        )
        context = _ContextResolver(
            build_static_gateway_client_context_resolver(
                bindings,
                EnvironmentGatewayClientSecretResolver(
                    {
                        "CLIENT_A": _KEY_A,
                        "CLIENT_B": _KEY_B,
                        "CLIENT_PRIVATE": _KEY_PRIVATE,
                    }
                ),
            ),
            self.events,
        )
        pdp = PolicyRouterHttpAdapter(
            endpoint="https://synthetic-pdp.example/route",
            transport=self.transport,
            now=lambda: _NOW,
            api_keys_by_client={binding.client_id: _PDP_KEY for binding in bindings},
        )
        route = RouteExplainService(PolicyEnforcementService(pdp))
        ranking = _ranking(registry)
        resolver = StaticProviderResolver(
            {
                (deployment.provider, deployment.api_family): self.provider
                for deployment in registry.deployments
            }
        )
        policy = (
            cache_policy
            if cache_policy is not None
            else ResponseCachePolicy(enabled=True, allowed_workloads=frozenset({"rag.answer"}))
        )
        self.coordinators = tuple(
            GenerateCoordinator(
                context_resolver=context,
                route_service=route,
                streaming_service=StreamingExecutionService(
                    health=self.health, resolver=resolver, cache=self.cache
                ),
                health=self.health,
                registry=registry,
                ranking_policy=ranking,
                defaults=PolicyProjectionDefaults(max_latency_ms=1000, max_cost_usd=Decimal("1")),
                cache_policy=policy,
            )
            for _ in range(2)
        )

    async def collect(
        self,
        api_key: str,
        index: int,
        *,
        worker: int = 0,
        agent_identity: str | None = None,
        classification: DataClassification = DataClassification.PUBLIC,
    ) -> list[GatewayStreamEvent]:
        coordinator = self.coordinators[worker]
        prepared = await coordinator.prepare(
            api_key=api_key,
            payload=_payload(index, agent_identity=agent_identity, classification=classification),
        )
        return [event async for event in coordinator.stream(prepared)]


def _cached(events: list[GatewayStreamEvent]) -> bool:
    execution = events[-1].execution
    assert execution is not None
    return execution.cached


def test_two_workers_isolate_clients_but_reuse_each_clients_answer_after_fresh_pdp() -> None:
    async def scenario() -> None:
        harness = _Harness()
        try:
            first = await harness.collect(_KEY_A, 1, agent_identity="client-b")
            second = await harness.collect(_KEY_B, 2, worker=1, agent_identity="client-a")
            again_a = await harness.collect(_KEY_A, 3, worker=1, agent_identity="spoofed-other")
            again_b = await harness.collect(_KEY_B, 4)
            assert not _cached(first) and not _cached(second)
            assert _cached(again_a) and _cached(again_b)
            assert first[1].delta != second[1].delta
            assert again_a[1].delta == first[1].delta
            assert again_b[1].delta == second[1].delta
            assert len(harness.provider.calls) == 2
            assert [request["agent_name"] for request in harness.transport.requests] == [
                "client-a",
                "client-b",
                "client-a",
                "client-b",
            ]
            assert [identity.client_id for identity in harness.cache.reads] == [
                "client-a",
                "client-b",
                "client-a",
                "client-b",
            ]
            assert all(_PROMPT not in str(request) for request in harness.transport.requests)
            assert first[-1].routing != again_a[-1].routing, "hits carry the fresh decision"
        finally:
            await harness.client.aclose()

    asyncio.run(scenario())


def test_pdp_policy_changes_invalidate_answers_even_with_unchanged_group_and_ranking() -> None:
    async def scenario() -> None:
        harness = _Harness()
        try:
            first = await harness.collect(_KEY_A, 1)
            harness.transport.policy_digest = "sha256:" + "b" * 64
            changed = await harness.collect(_KEY_A, 2, worker=1)
            repeated = await harness.collect(_KEY_A, 3)
            assert not _cached(first) and not _cached(changed) and _cached(repeated)
            assert len(harness.provider.calls) == 2
            old, new = harness.cache.reads[:2]
            assert old.ranking_policy_digest == new.ranking_policy_digest
            assert old.authorized_model_group == new.authorized_model_group
            assert old.digest != new.digest
        finally:
            await harness.client.aclose()

    asyncio.run(scenario())


def test_raised_classification_neither_reads_nor_writes_a_seeded_public_cache() -> None:
    async def scenario() -> None:
        harness = _Harness()
        try:
            await harness.collect(_KEY_A, 1)
            counts = len(harness.cache.reads), len(harness.cache.writes)
            raised = await harness.collect(_KEY_PRIVATE, 2)
            assert not _cached(raised)
            assert (len(harness.cache.reads), len(harness.cache.writes)) == counts
            assert harness.transport.requests[-1]["data_classification"] == "confidential"
            assert len(harness.provider.calls) == 2
        finally:
            await harness.client.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("status", "code"),
    [(403, PolicyDecisionErrorCode.AUTHORIZATION), (503, PolicyDecisionErrorCode.UNAVAILABLE)],
)
def test_fresh_pdp_denial_or_outage_prevents_cache_access(
    status: int, code: PolicyDecisionErrorCode
) -> None:
    async def scenario() -> None:
        harness = _Harness()
        try:
            await harness.collect(_KEY_A, 1)
            counts = len(harness.cache.reads), len(harness.cache.writes)
            harness.transport.status = status
            with pytest.raises(PolicyDecisionError) as caught:
                await harness.collect(_KEY_A, 2, worker=1)
            assert caught.value.code is code
            assert (len(harness.cache.reads), len(harness.cache.writes)) == counts
            assert len(harness.provider.calls) == 1
            assert len(harness.transport.requests) == 2
        finally:
            await harness.client.aclose()

    asyncio.run(scenario())


def test_invalid_authentication_prevents_pdp_and_cache_access() -> None:
    async def scenario() -> None:
        harness = _Harness()
        try:
            await harness.collect(_KEY_A, 1)
            before = (
                len(harness.transport.requests),
                len(harness.cache.reads),
                len(harness.provider.calls),
            )
            with pytest.raises(ClientAuthenticationError):
                await harness.collect("unrecognized-synthetic-key", 2)
            assert (
                len(harness.transport.requests),
                len(harness.cache.reads),
                len(harness.provider.calls),
            ) == before
        finally:
            await harness.client.aclose()

    asyncio.run(scenario())


def test_cache_lookup_follows_complete_preflight_and_never_validates_provider_health() -> None:
    async def scenario() -> None:
        harness = _Harness()
        try:
            coordinator = harness.coordinators[0]
            prepared = await coordinator.prepare(api_key=_KEY_A, payload=_payload(1))
            assert harness.cache.reads == [] and harness.provider.calls == []
            assert harness.events[:2] == ["authenticate", "pdp"]
            assert harness.events[2:] and set(harness.events[2:]) == {"preflight"}
            events = [event async for event in coordinator.stream(prepared)]
            assert not _cached(events)
            health = await harness.health.snapshot("deployment-a")
            assert _cached(await harness.collect(_KEY_A, 2, worker=1))
            assert await harness.health.snapshot("deployment-a") == health
            assert harness.events.index("cache.read") > harness.events.index("preflight")
        finally:
            await harness.client.aclose()

    asyncio.run(scenario())


def test_health_selection_change_rejects_a_stored_answer_from_the_previous_deployment() -> None:
    async def scenario() -> None:
        harness = _Harness()
        try:
            first = await harness.collect(_KEY_A, 1)
            await harness.health.record_failure(
                "deployment-a",
                ProviderError(
                    code=ProviderErrorCode.UNAVAILABLE,
                    message="synthetic availability failure",
                    provider="provider-a",
                    retryable=True,
                ),
                latency_ms=0,
            )
            changed = await harness.collect(_KEY_A, 2, worker=1)
            assert not _cached(first) and not _cached(changed)
            assert harness.cache.reads[0].digest == harness.cache.reads[1].digest
            assert changed[-1].execution is not None
            assert changed[-1].execution.deployment == "deployment-b"
            assert len(harness.provider.calls) == 2
            assert harness.provider.calls[-1].model == "provider-b/model-b"
        finally:
            await harness.client.aclose()

    asyncio.run(scenario())


def test_disabled_cache_preserves_fresh_execution_after_every_authorization() -> None:
    async def scenario() -> None:
        harness = _Harness(cache_policy=ResponseCachePolicy())
        try:
            assert not _cached(await harness.collect(_KEY_A, 1))
            assert not _cached(await harness.collect(_KEY_A, 2, worker=1))
            assert len(harness.transport.requests) == len(harness.provider.calls) == 2
            assert harness.cache.reads == harness.cache.writes == []
        finally:
            await harness.client.aclose()

    asyncio.run(scenario())


def test_same_client_elevated_classification_cannot_read_its_earlier_public_answer() -> None:
    async def scenario() -> None:
        harness = _Harness()
        try:
            await harness.collect(_KEY_A, 1)
            counts = len(harness.cache.reads), len(harness.cache.writes)
            events = await harness.collect(
                _KEY_A, 2, classification=DataClassification.CONFIDENTIAL
            )
            assert not _cached(events)
            assert (len(harness.cache.reads), len(harness.cache.writes)) == counts
            assert harness.transport.requests[-1]["agent_name"] == "client-a"
            assert harness.transport.requests[-1]["data_classification"] == "confidential"
            assert len(harness.provider.calls) == 2
        finally:
            await harness.client.aclose()

    asyncio.run(scenario())


def test_invalid_fresh_pdp_provenance_cannot_be_replaced_by_a_cached_answer() -> None:
    async def scenario() -> None:
        harness = _Harness()
        try:
            await harness.collect(_KEY_A, 1)
            harness.transport.policy_digest = "malformed-synthetic-digest"
            with pytest.raises(PolicyDecisionError) as caught:
                await harness.collect(_KEY_A, 2)
            assert caught.value.code is PolicyDecisionErrorCode.INVALID_RESPONSE
            assert len(harness.cache.reads) == len(harness.cache.writes) == 1
            assert len(harness.provider.calls) == 1
        finally:
            await harness.client.aclose()

    asyncio.run(scenario())


def test_no_eligible_deployment_prevents_cache_lookup_even_when_an_answer_exists() -> None:
    async def scenario() -> None:
        harness = _Harness()
        try:
            await harness.collect(_KEY_A, 1)
            error = ProviderError(
                code=ProviderErrorCode.UNAVAILABLE,
                message="synthetic transient failure",
                provider="synthetic",
                retryable=True,
            )
            for deployment in ("deployment-a", "deployment-b"):
                await harness.health.record_failure(deployment, error, latency_ms=0)
            with pytest.raises(NoEligibleStreamingDeploymentError):
                await harness.collect(_KEY_A, 2)
            assert len(harness.cache.reads) == len(harness.cache.writes) == 1
            assert len(harness.provider.calls) == 1
            assert len(harness.transport.requests) == 2
        finally:
            await harness.client.aclose()

    asyncio.run(scenario())


def test_concurrent_hits_remain_client_scoped_and_do_not_export_identities_or_credentials(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    async def scenario() -> None:
        harness = _Harness()
        try:
            originals = [await harness.collect(_KEY_A, 1), await harness.collect(_KEY_B, 2)]
            keys = (_KEY_A, _KEY_B)
            events = await asyncio.gather(
                *(
                    harness.collect(keys[index % 2], index + 3, worker=index % 2)
                    for index in range(12)
                )
            )
            assert all(_cached(result) for result in events)
            for index, result in enumerate(events):
                assert result[1].delta == originals[index % 2][1].delta
            assert len(harness.provider.calls) == 2
            assert len(harness.transport.requests) == len(harness.cache.reads) == 14
            for raw_key in await harness.client.keys():
                for marker in ("client-a", "client-b", _KEY_A, _KEY_B, _PDP_KEY, _PROMPT):
                    assert marker not in raw_key
            public_events = str(events)
            for marker in ("client-a", "client-b", _KEY_A, _KEY_B, _PDP_KEY, _PROMPT):
                assert marker not in public_events
        finally:
            await harness.client.aclose()

    asyncio.run(scenario())
    assert caplog.records == []
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
