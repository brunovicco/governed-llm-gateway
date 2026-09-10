"""A cache hit must be served honestly, and a broken cache must never lose an answer."""

import asyncio
import unittest
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from governed_llm_gateway_contracts import (
    Capability,
    DataClassification,
    GatewayRequest,
    GatewayStreamEvent,
    Message,
    MessageRole,
    Modality,
    PolicyProvenance,
    RiskLevel,
    RoutingProvenance,
    StreamEventType,
    WorkloadRequirements,
)
from governed_llm_gateway_core.application.provider import (
    ProviderContentDelta,
    ProviderFeatureSupport,
    ProviderRequest,
    ProviderResponse,
    ProviderResponseCompleted,
    ProviderResponseStarted,
    ProviderStreamEvent,
    ProviderUsage,
    ProviderUsageCompleted,
)
from governed_llm_gateway_core.application.ranking import (
    RankedCandidate,
    RankingDecision,
    ScoreBreakdown,
)
from governed_llm_gateway_core.application.resilience import (
    InMemoryHealthTracker,
    StaticProviderResolver,
)
from governed_llm_gateway_core.application.response_cache import CachedResponse
from governed_llm_gateway_core.application.streaming import StreamingExecutionService
from governed_llm_gateway_core.domain.model_registry import ModelDeployment, PricingMetadata
from governed_llm_gateway_core.domain.response_cache import (
    ResponseCacheIdentity,
    messages_digest,
)

REQUEST_ID = UUID("44444444-4444-4444-8444-444444444444")
ORIGIN_REQUEST_ID = UUID("33333333-3333-4333-8333-333333333333")
TODAY = date(2026, 9, 1)
MESSAGES = (Message(role=MessageRole.USER, content="explain deterministic routing"),)


class _Provider:
    feature_support = ProviderFeatureSupport(native_streaming=True, streaming_usage=True)

    def __init__(self) -> None:
        self.calls: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        del request
        raise AssertionError("streaming tests must not call generate")

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        self.calls.append(request)
        yield ProviderResponseStarted(response_id="r-1")
        yield ProviderContentDelta(delta="deterministic ")
        yield ProviderContentDelta(delta="routing")
        yield ProviderUsageCompleted(usage=ProviderUsage(input_tokens=11, output_tokens=3))
        yield ProviderResponseCompleted(response_id="r-1", finish_reason="stop")


class _MemoryCache:
    def __init__(self, seeded: CachedResponse | None = None) -> None:
        self.entries: dict[str, CachedResponse] = {}
        self.seeded = seeded
        self.put_calls = 0

    async def get(self, identity: ResponseCacheIdentity) -> CachedResponse | None:
        if self.seeded is not None:
            return self.seeded
        return self.entries.get(identity.digest)

    async def put(
        self,
        identity: ResponseCacheIdentity,
        response: CachedResponse,
        *,
        ttl_seconds: int,
    ) -> None:
        del ttl_seconds
        self.put_calls += 1
        self.entries[identity.digest] = response


class _BrokenCache(_MemoryCache):
    async def put(
        self,
        identity: ResponseCacheIdentity,
        response: CachedResponse,
        *,
        ttl_seconds: int,
    ) -> None:
        del identity, response, ttl_seconds
        raise RuntimeError("cache server unreachable")


def _deployment() -> ModelDeployment:
    return ModelDeployment(
        deployment_id="deployment-a",
        provider="provider-a",
        model_id="provider-a/model-a",
        model_group="balanced",
        api_family="openai-compatible",
        capabilities=frozenset({Capability.TEXT, Capability.STREAMING}),
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


def _routing() -> RoutingProvenance:
    return RoutingProvenance(
        routing_decision_id="sha256:" + "b" * 64,
        policy=PolicyProvenance(
            decision_id="policy-decision",
            policy_id="gateway-policy",
            policy_version="1.0.0",
            policy_digest="sha256:" + "a" * 64,
        ),
        authorized_model_group="balanced",
        model_registry_digest="c" * 64,
        ranking_policy_version="ranking-v1",
        ranking_policy_digest="d" * 64,
        score_snapshot_id="static-v1",
        provider="provider-a",
        model="provider-a/model-a",
        deployment="deployment-a",
    )


def _decision() -> RankingDecision:
    deployment = _deployment()
    value = Decimal("1")
    return RankingDecision(
        routing=_routing(),
        ranking_policy_digest="d" * 64,
        score_snapshot_id="static-v1",
        selected=RankedCandidate(
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
        ),
        alternatives=(),
        rejected_candidates=(),
    )


def _request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="rag.answer",
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(streaming=True),
        messages=MESSAGES,
    )


def _identity() -> ResponseCacheIdentity:
    return ResponseCacheIdentity(
        workload="rag.answer",
        risk_level=RiskLevel.LOW,
        data_classification=DataClassification.PUBLIC,
        authorized_model_group="balanced",
        model_registry_digest="c" * 64,
        ranking_policy_digest="d" * 64,
        max_output_tokens=64,
        messages_digest=messages_digest(MESSAGES),
    )


def _stored() -> CachedResponse:
    return CachedResponse(
        content="deterministic routing",
        input_tokens=11,
        output_tokens=3,
        provider="provider-a",
        model="provider-a/model-a",
        deployment="deployment-a",
        api_family="openai-compatible",
        finish_reason="stop",
        cached_at=datetime.now(UTC),
        source_request_id=ORIGIN_REQUEST_ID,
    )


def _service(provider: _Provider, cache: _MemoryCache | None) -> StreamingExecutionService:
    deployment = _deployment()
    return StreamingExecutionService(
        health=InMemoryHealthTracker(),
        resolver=StaticProviderResolver({(deployment.provider, deployment.api_family): provider}),
        cache=cache,
    )


async def _collect(
    service: StreamingExecutionService,
    *,
    identity: ResponseCacheIdentity | None,
) -> list[GatewayStreamEvent]:
    return [
        event
        async for event in service.stream(
            _request(),
            _decision(),
            max_output_tokens=64,
            cache_identity=identity,
        )
    ]


class CacheHitTests(unittest.TestCase):
    def test_a_hit_is_served_without_calling_a_provider(self) -> None:
        provider = _Provider()
        events = asyncio.run(
            _collect(_service(provider, _MemoryCache(seeded=_stored())), identity=_identity())
        )

        self.assertEqual(provider.calls, [])
        self.assertEqual(
            [event.event_type for event in events],
            [
                StreamEventType.RESPONSE_STARTED,
                StreamEventType.CONTENT_DELTA,
                StreamEventType.USAGE_COMPLETED,
                StreamEventType.RESPONSE_COMPLETED,
            ],
        )
        self.assertEqual(events[1].delta, "deterministic routing")

    def test_a_hit_never_presents_itself_as_a_fresh_provider_call(self) -> None:
        """The whole reason the contract gained a field: evidence must not lie."""
        events = asyncio.run(
            _collect(_service(_Provider(), _MemoryCache(seeded=_stored())), identity=_identity())
        )

        execution = events[-1].execution
        self.assertIsNotNone(execution)
        assert execution is not None
        self.assertTrue(execution.cached)
        self.assertEqual(execution.deployment, "deployment-a")
        self.assertEqual(execution.provider, "provider-a")

    def test_a_hit_reports_this_request_latency_not_the_original(self) -> None:
        events = asyncio.run(
            _collect(_service(_Provider(), _MemoryCache(seeded=_stored())), identity=_identity())
        )

        execution = events[-1].execution
        assert execution is not None
        self.assertEqual(execution.latency_ms, 0)

    def test_a_fresh_execution_is_not_marked_cached(self) -> None:
        events = asyncio.run(_collect(_service(_Provider(), _MemoryCache()), identity=_identity()))

        execution = events[-1].execution
        assert execution is not None
        self.assertFalse(execution.cached)


class CacheWriteTests(unittest.TestCase):
    def test_a_completed_answer_is_stored_under_its_authorized_identity(self) -> None:
        cache = _MemoryCache()

        asyncio.run(_collect(_service(_Provider(), cache), identity=_identity()))

        stored = cache.entries[_identity().digest]
        self.assertEqual(stored.content, "deterministic routing")
        self.assertEqual(stored.deployment, "deployment-a")
        self.assertEqual(stored.input_tokens, 11)
        self.assertEqual(stored.source_request_id, REQUEST_ID)

    def test_nothing_is_stored_without_an_identity(self) -> None:
        """No identity means the caller judged this request uncacheable."""
        cache = _MemoryCache()

        asyncio.run(_collect(_service(_Provider(), cache), identity=None))

        self.assertEqual(cache.put_calls, 0)

    def test_nothing_is_read_without_an_identity(self) -> None:
        provider = _Provider()

        asyncio.run(_collect(_service(provider, _MemoryCache(seeded=_stored())), identity=None))

        self.assertEqual(len(provider.calls), 1, "a seeded cache must not be consulted")

    def test_a_cache_write_failure_never_loses_a_served_answer(self) -> None:
        """The caller already has the full answer; a write failure must not undo that."""
        events = asyncio.run(_collect(_service(_Provider(), _BrokenCache()), identity=_identity()))

        self.assertEqual(events[-1].event_type, StreamEventType.RESPONSE_COMPLETED)
        self.assertEqual(events[1].delta, "deterministic ")

    def test_a_request_served_from_cache_is_not_written_back(self) -> None:
        cache = _MemoryCache(seeded=_stored())

        asyncio.run(_collect(_service(_Provider(), cache), identity=_identity()))

        self.assertEqual(cache.put_calls, 0)


class CacheDisabledTests(unittest.TestCase):
    def test_without_a_cache_the_path_is_unchanged(self) -> None:
        provider = _Provider()

        events = asyncio.run(_collect(_service(provider, None), identity=_identity()))

        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(events[-1].event_type, StreamEventType.RESPONSE_COMPLETED)
        execution = events[-1].execution
        assert execution is not None
        self.assertFalse(execution.cached)


class CacheStalenessTests(unittest.TestCase):
    def test_an_entry_from_another_deployment_is_not_replayed(self) -> None:
        """Serving it would name a deployment that did not produce this answer."""
        elsewhere = CachedResponse(
            content="answered by a deployment ranking no longer selects",
            input_tokens=1,
            output_tokens=1,
            provider="other-provider",
            model="other/model",
            deployment="deployment-b",
            api_family="openai-compatible",
            finish_reason="stop",
            cached_at=datetime.now(UTC),
            source_request_id=ORIGIN_REQUEST_ID,
        )
        provider = _Provider()

        events = asyncio.run(
            _collect(_service(provider, _MemoryCache(seeded=elsewhere)), identity=_identity())
        )

        self.assertEqual(len(provider.calls), 1, "the gateway must execute rather than replay")
        execution = events[-1].execution
        assert execution is not None
        self.assertFalse(execution.cached)
        self.assertEqual(execution.deployment, "deployment-a")


if __name__ == "__main__":
    unittest.main()
