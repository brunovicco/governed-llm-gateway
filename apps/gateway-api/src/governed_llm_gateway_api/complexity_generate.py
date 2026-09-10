"""Complexity-aware preflight composition for governed streaming generation."""

from collections.abc import AsyncGenerator

from governed_llm_gateway_contracts import GatewayStreamEvent
from governed_llm_gateway_core.application import (
    ComplexityRouteExplainService,
    PolicyProjectionDefaults,
)
from governed_llm_gateway_core.application.health import DeploymentHealthPort
from governed_llm_gateway_core.application.streaming import StreamingExecutionService
from governed_llm_gateway_core.domain.evidence_ranking import EvidenceDrivenRankingPolicy
from governed_llm_gateway_core.domain.model_registry import ModelRegistry

from .route_explain import EffectiveContextResolver
from .stream_generate import (
    GenerateRequestModel,
    NoEligibleStreamingDeploymentError,
    PreparedStreamingExecution,
)


class ComplexityGenerateCoordinator:
    """Authenticate, authorize, complexity-narrow, rank, then stream the retained subset."""

    def __init__(
        self,
        *,
        context_resolver: EffectiveContextResolver,
        route_service: ComplexityRouteExplainService,
        streaming_service: StreamingExecutionService,
        health: DeploymentHealthPort,
        registry: ModelRegistry,
        ranking_policy: EvidenceDrivenRankingPolicy,
        defaults: PolicyProjectionDefaults,
    ) -> None:
        """Bind immutable complexity-routing inputs and the existing streaming executor."""
        self._context_resolver = context_resolver
        self._route_service = route_service
        self._streaming_service = streaming_service
        self._health = health
        self._registry = registry
        self._ranking_policy = ranking_policy
        self._defaults = defaults

    async def prepare(
        self,
        *,
        api_key: str,
        payload: GenerateRequestModel,
    ) -> PreparedStreamingExecution:
        """Finish auth, PDP, complexity narrowing, and ranking before SSE begins."""
        request = payload.to_gateway_request()
        effective_context = await self._context_resolver.resolve(
            api_key=api_key,
            request=request,
        )
        deployment_ids = tuple(
            sorted(deployment.deployment_id for deployment in self._registry.deployments)
        )
        runtime_health = await self._health.snapshots(deployment_ids)
        decision = await self._route_service.explain(
            request,
            effective_context,
            self._registry,
            self._ranking_policy,
            context_tokens_estimated=payload.context_tokens_estimated,
            max_output_tokens_estimated=payload.max_output_tokens,
            defaults=self._defaults,
            runtime_health=runtime_health,
        )
        ranking = decision.ranking
        if ranking.selected is None:
            raise NoEligibleStreamingDeploymentError(
                "no eligible complexity-authorized streaming deployment is available"
            )
        return PreparedStreamingExecution(
            request=request,
            decision=ranking,
            max_output_tokens=payload.max_output_tokens,
            provider_timeout_seconds=payload.provider_timeout_seconds,
        )

    def stream(
        self,
        prepared: PreparedStreamingExecution,
    ) -> AsyncGenerator[GatewayStreamEvent]:
        """Execute only the ranking result already narrowed by complexity routing."""
        return self._streaming_service.stream(
            prepared.request,
            prepared.decision,
            max_output_tokens=prepared.max_output_tokens,
            provider_timeout_seconds=prepared.provider_timeout_seconds,
        )
