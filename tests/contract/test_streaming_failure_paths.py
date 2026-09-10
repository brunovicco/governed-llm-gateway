"""Streaming failure and cancellation paths.

/v1/generate is SSE-only, so this is the gateway's primary execution path, and it was
also its least-covered one. These cases target the properties that make partial delivery
safe rather than the happy path already covered by test_phase8_streaming_execution.py.
"""

import asyncio
import contextlib
import unittest
from collections.abc import AsyncIterator
from datetime import date
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
from governed_llm_gateway_core.application.ranking import (
    RankedCandidate,
    RankingDecision,
    ScoreBreakdown,
)
from governed_llm_gateway_core.application.resilience import (
    InMemoryHealthTracker,
    StaticProviderResolver,
)
from governed_llm_gateway_core.application.streaming import StreamingExecutionService
from governed_llm_gateway_core.domain.model_registry import ModelDeployment, PricingMetadata
from governed_llm_gateway_core.domain.resilience import CircuitBreakerPolicy, RetryPolicy

REQUEST_ID = UUID("77777777-7777-4777-8777-777777777777")
TODAY = date(2026, 9, 1)


class ScriptedStreamingProvider:
    """Replay one scripted provider stream per attempt, raising scripted errors in place."""

    feature_support = ProviderFeatureSupport(native_streaming=True, streaming_usage=True)

    def __init__(self, *attempts: tuple[ProviderStreamEvent | ProviderError, ...]) -> None:
        self.attempts = list(attempts)
        self.calls: list[ProviderRequest] = []
        self.closed_count = 0

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        del request
        raise AssertionError("streaming tests must not call generate")

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
        self.calls.append(request)
        attempt = self.attempts.pop(0)
        try:
            for event in attempt:
                if isinstance(event, ProviderError):
                    raise event
                yield event
        finally:
            self.closed_count += 1


class NonStreamingProvider:
    """A provider adapter that never implements the streaming port."""

    feature_support = ProviderFeatureSupport(native_streaming=False, streaming_usage=False)

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        del request
        return ProviderResponse(text="unary only")


class DeclaredCapabilityProvider(ScriptedStreamingProvider):
    """Streaming adapter whose declared feature support is set per test."""

    def __init__(self, *, native_streaming: bool, streaming_usage: bool) -> None:
        super().__init__(())
        self.feature_support = ProviderFeatureSupport(
            native_streaming=native_streaming,
            streaming_usage=streaming_usage,
        )


def _request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=REQUEST_ID,
        workload="agent.orchestration",
        risk_level=RiskLevel.MEDIUM,
        data_classification=DataClassification.PUBLIC,
        requirements=WorkloadRequirements(streaming=True),
        messages=(Message(role=MessageRole.USER, content="hello"),),
    )


def _deployment(deployment_id: str, provider: str) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider=provider,
        model_id=f"model/{deployment_id}",
        model_group="agentic-strong",
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


def _decision(selected: ModelDeployment, *alternatives: ModelDeployment) -> RankingDecision:
    return RankingDecision(
        routing=RoutingProvenance(
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
            provider=selected.provider,
            model=selected.model_id,
            deployment=selected.deployment_id,
        ),
        ranking_policy_digest="d" * 64,
        score_snapshot_id="static-v1",
        selected=_ranked(selected, "1"),
        alternatives=tuple(
            _ranked(deployment, str(Decimal("0.9") - Decimal(index) / Decimal("10")))
            for index, deployment in enumerate(alternatives)
        ),
        rejected_candidates=(),
    )


def _service(
    *pairs: tuple[ModelDeployment, ProviderPort],
    health: InMemoryHealthTracker | None = None,
    retry_policy: RetryPolicy | None = None,
) -> StreamingExecutionService:
    return StreamingExecutionService(
        health=health or InMemoryHealthTracker(),
        resolver=StaticProviderResolver(
            {
                (deployment.provider, deployment.api_family): provider
                for deployment, provider in pairs
            }
        ),
        retry_policy=retry_policy or RetryPolicy(max_attempts_per_deployment=1, max_fallbacks=1),
    )


async def _collect(
    service: StreamingExecutionService, decision: RankingDecision
) -> list[GatewayStreamEvent]:
    return [event async for event in service.stream(_request(), decision, max_output_tokens=64)]


def _rate_limit(provider: str = "provider-a") -> ProviderError:
    return ProviderError(
        provider=provider,
        code=ProviderErrorCode.RATE_LIMIT,
        message="stream was rate limited",
        retryable=True,
        status_code=429,
    )


class PartialDeliverySafetyTests(unittest.TestCase):
    def test_failure_after_partial_output_never_retries_or_falls_back(self) -> None:
        """Replaying after delivered content would duplicate it for the caller."""
        primary = _deployment("deployment-a", "provider-a")
        fallback = _deployment("deployment-b", "provider-b")
        primary_provider = ScriptedStreamingProvider(
            (
                ProviderResponseStarted(response_id="partial"),
                ProviderContentDelta(delta="half an ans"),
                _rate_limit(),
            ),
        )
        fallback_provider = ScriptedStreamingProvider(
            (
                ProviderResponseStarted(response_id="never"),
                ProviderContentDelta(delta="should not run"),
                ProviderUsageCompleted(usage=ProviderUsage(input_tokens=1, output_tokens=1)),
                ProviderResponseCompleted(response_id="never", finish_reason="stop"),
            ),
        )
        service = _service(
            (primary, primary_provider),
            (fallback, fallback_provider),
            retry_policy=RetryPolicy(max_attempts_per_deployment=3, max_fallbacks=1),
        )

        events = asyncio.run(_collect(service, _decision(primary, fallback)))

        self.assertEqual(events[-1].event_type, StreamEventType.RESPONSE_FAILED)
        self.assertTrue(events[-1].partial)
        self.assertEqual(events[-1].error.code if events[-1].error else None, "rate_limit")
        self.assertEqual(len(primary_provider.calls), 1, "a retried attempt would replay content")
        self.assertEqual(fallback_provider.calls, [], "fallback would duplicate delivered content")

    def test_failure_before_any_output_is_not_marked_partial(self) -> None:
        deployment = _deployment("deployment-a", "provider-a")
        provider = ScriptedStreamingProvider(
            (ProviderResponseStarted(response_id="none"), _rate_limit()),
        )
        service = _service((deployment, provider))

        events = asyncio.run(_collect(service, _decision(deployment)))

        self.assertEqual(events[-1].event_type, StreamEventType.RESPONSE_FAILED)
        self.assertFalse(events[-1].partial)


class StreamTerminationTests(unittest.TestCase):
    def test_stream_ending_without_completion_fails_closed(self) -> None:
        """A truncated provider stream must not look like a completed response."""
        deployment = _deployment("deployment-a", "provider-a")
        provider = ScriptedStreamingProvider(
            (
                ProviderResponseStarted(response_id="truncated"),
                ProviderContentDelta(delta="cut off"),
            ),
        )
        service = _service((deployment, provider))

        events = asyncio.run(_collect(service, _decision(deployment)))

        self.assertEqual(events[-1].event_type, StreamEventType.RESPONSE_FAILED)
        self.assertNotIn(StreamEventType.RESPONSE_COMPLETED, [event.event_type for event in events])

    def test_usage_is_required_before_a_completed_response(self) -> None:
        deployment = _deployment("deployment-a", "provider-a")
        provider = ScriptedStreamingProvider(
            (
                ProviderResponseStarted(response_id="no-usage"),
                ProviderContentDelta(delta="text"),
                ProviderResponseCompleted(response_id="no-usage", finish_reason="stop"),
            ),
        )
        service = _service((deployment, provider))

        events = asyncio.run(_collect(service, _decision(deployment)))

        self.assertEqual(events[-1].event_type, StreamEventType.RESPONSE_FAILED)


class CancellationTests(unittest.TestCase):
    def test_caller_cancellation_closes_the_provider_stream(self) -> None:
        """A disconnecting caller must not leave the provider generator open."""
        deployment = _deployment("deployment-a", "provider-a")
        provider = ScriptedStreamingProvider(
            (
                ProviderResponseStarted(response_id="cancelled"),
                ProviderContentDelta(delta="first"),
                ProviderContentDelta(delta="second"),
                ProviderUsageCompleted(usage=ProviderUsage(input_tokens=1, output_tokens=1)),
                ProviderResponseCompleted(response_id="cancelled", finish_reason="stop"),
            ),
        )
        service = _service((deployment, provider))

        async def _abandon_after_first_delta() -> list[StreamEventType]:
            seen: list[StreamEventType] = []
            stream = service.stream(_request(), _decision(deployment), max_output_tokens=64)
            async with contextlib.aclosing(stream) as events:
                async for event in events:
                    seen.append(event.event_type)
                    if event.event_type is StreamEventType.CONTENT_DELTA:
                        break
            return seen

        seen = asyncio.run(_abandon_after_first_delta())

        self.assertEqual(seen, [StreamEventType.RESPONSE_STARTED, StreamEventType.CONTENT_DELTA])
        self.assertEqual(provider.closed_count, 1, "provider stream must be closed on abandon")

    def test_cancellation_propagates_rather_than_being_swallowed(self) -> None:
        deployment = _deployment("deployment-a", "provider-a")

        class CancellingProvider(ScriptedStreamingProvider):
            async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderStreamEvent]:
                self.calls.append(request)
                yield ProviderResponseStarted(response_id="cancelling")
                raise asyncio.CancelledError

        provider = CancellingProvider(())
        service = _service((deployment, provider))

        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(_collect(service, _decision(deployment)))


class CapabilityGuardTests(unittest.TestCase):
    def test_non_streaming_adapter_is_refused_rather_than_downgraded(self) -> None:
        deployment = _deployment("deployment-a", "provider-a")
        service = _service((deployment, NonStreamingProvider()))

        events = asyncio.run(_collect(service, _decision(deployment)))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, StreamEventType.RESPONSE_FAILED)
        self.assertEqual(
            events[0].error.code if events[0].error else None, "streaming_not_supported"
        )

    def test_adapter_without_verified_native_streaming_is_refused(self) -> None:
        deployment = _deployment("deployment-a", "provider-a")
        provider = DeclaredCapabilityProvider(native_streaming=False, streaming_usage=True)
        service = _service((deployment, provider))

        events = asyncio.run(_collect(service, _decision(deployment)))

        self.assertEqual(
            events[0].error.code if events[0].error else None, "streaming_not_supported"
        )
        self.assertEqual(provider.calls, [])

    def test_adapter_that_cannot_finalize_usage_is_refused(self) -> None:
        """Usage evidence is not optional: without it, cost evidence would be silently absent."""
        deployment = _deployment("deployment-a", "provider-a")
        provider = DeclaredCapabilityProvider(native_streaming=True, streaming_usage=False)
        service = _service((deployment, provider))

        events = asyncio.run(_collect(service, _decision(deployment)))

        self.assertEqual(
            events[0].error.code if events[0].error else None, "streaming_usage_unavailable"
        )
        self.assertEqual(provider.calls, [])


class CircuitStateTests(unittest.TestCase):
    def test_open_circuit_skips_a_candidate_without_consuming_it(self) -> None:
        primary = _deployment("deployment-a", "provider-a")
        fallback = _deployment("deployment-b", "provider-b")
        primary_provider = ScriptedStreamingProvider(())
        fallback_provider = ScriptedStreamingProvider(
            (
                ProviderResponseStarted(response_id="ok"),
                ProviderContentDelta(delta="from fallback"),
                ProviderUsageCompleted(usage=ProviderUsage(input_tokens=1, output_tokens=1)),
                ProviderResponseCompleted(response_id="ok", finish_reason="stop"),
            ),
        )
        health = InMemoryHealthTracker(CircuitBreakerPolicy(failure_threshold=1))
        for _ in range(2):
            health.record_failure(primary.deployment_id, _rate_limit(), latency_ms=1)
        self.assertFalse(health.allow_request(primary.deployment_id))

        service = _service(
            (primary, primary_provider),
            (fallback, fallback_provider),
            health=health,
        )

        events = asyncio.run(_collect(service, _decision(primary, fallback)))

        self.assertEqual(events[-1].event_type, StreamEventType.RESPONSE_COMPLETED)
        self.assertEqual(primary_provider.calls, [], "an open circuit must not be called")
        self.assertEqual(len(fallback_provider.calls), 1)

    def test_all_candidates_unavailable_exhausts_closed(self) -> None:
        deployment = _deployment("deployment-a", "provider-a")
        provider = ScriptedStreamingProvider(())
        health = InMemoryHealthTracker(CircuitBreakerPolicy(failure_threshold=1))
        for _ in range(2):
            health.record_failure(deployment.deployment_id, _rate_limit(), latency_ms=1)

        service = _service((deployment, provider), health=health)

        events = asyncio.run(_collect(service, _decision(deployment)))

        self.assertEqual(events[-1].event_type, StreamEventType.RESPONSE_FAILED)
        self.assertEqual(
            events[-1].error.code if events[-1].error else None,
            "streaming_candidates_exhausted",
        )
        self.assertEqual(provider.calls, [])


if __name__ == "__main__":
    unittest.main()
