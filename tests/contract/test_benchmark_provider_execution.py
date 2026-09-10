import asyncio
import unittest
from datetime import date
from decimal import Decimal

from governed_llm_gateway_contracts import Capability, DataClassification, Modality
from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)
from governed_llm_gateway_core.domain.model_registry import (
    ModelDeployment,
    ModelRegistry,
    PricingMetadata,
)

from benchmarks.contracts import BenchmarkCase, BenchmarkTarget, BenchmarkWorkload
from benchmarks.provider_execution import (
    BenchmarkExecutionBindingError,
    RegistryDeploymentExecutor,
    TargetDeploymentBinding,
    normalize_response_output,
    observed_cost_usd,
    registry_bindings,
)
from benchmarks.runner import BenchmarkProviderFailure

SOURCE_DATE = date(2026, 9, 9)


def _deployment(
    deployment_id: str,
    *,
    provider: str = "nvidia",
    model_id: str = "nvidia/nemotron",
    api_family: str = "openai-compatible",
    model_group: str = "balanced",
    enabled: bool = True,
    pricing: PricingMetadata | None = None,
) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=deployment_id,
        provider=provider,
        model_id=model_id,
        model_group=model_group,
        api_family=api_family,
        capabilities=frozenset({Capability.TEXT}),
        context_tokens=131072,
        modalities=frozenset({Modality.TEXT}),
        pricing=pricing,
        max_data_classification=DataClassification.PUBLIC,
        allowed_environments=frozenset({"development"}),
        enabled=enabled,
        source_date=SOURCE_DATE,
        catalog_version="test-v1",
    )


def _registry(*deployments: ModelDeployment) -> ModelRegistry:
    return ModelRegistry(
        schema_version="1.0",
        catalog_version="test-v1",
        source_date=SOURCE_DATE,
        deployments=deployments,
    )


def _target(
    target_id: str = "t-one",
    *,
    provider: str = "nvidia",
    model: str = "nvidia/nemotron",
    api_family: str | None = "openai-compatible",
) -> BenchmarkTarget:
    return BenchmarkTarget(
        target_id=target_id,
        provider=provider,
        model=model,
        api="openai-compatible/chat-completions",
        api_family=api_family,
        max_output_tokens=512,
        configuration="access=test;response_normalization=fenced_json_v1",
        source_date=SOURCE_DATE,
    )


def _case() -> BenchmarkCase:
    return BenchmarkCase(
        case_id="case-1",
        workload=BenchmarkWorkload.RAG_ANSWER,
        scorer="rag_answer_v1",
        prompt="Return only JSON.",
        expected={"answer": "yes", "citations": ["a"]},
    )


class _StubProvider:
    def __init__(self, response: ProviderResponse | ProviderError) -> None:
        self.response = response
        self.requests: list[ProviderRequest] = []

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.requests.append(request)
        if isinstance(self.response, ProviderError):
            raise self.response
        return self.response


class _StubResolver:
    def __init__(self, provider: _StubProvider) -> None:
        self.provider = provider

    def resolve(self, deployment: ModelDeployment) -> _StubProvider:
        return self.provider


def _executor(registry: ModelRegistry, provider: _StubProvider) -> RegistryDeploymentExecutor:
    ticks = iter([0.0, 1.5, 3.0, 4.5])
    return RegistryDeploymentExecutor(
        registry=registry,
        resolver=_StubResolver(provider),
        bindings=(TargetDeploymentBinding(target_id="t-one", deployment_id="d-one"),),
        clock=lambda: next(ticks),
    )


class BindingTests(unittest.TestCase):
    def test_unbound_target_fails_before_any_provider_call(self) -> None:
        provider = _StubProvider(ProviderResponse(text="{}"))
        executor = _executor(_registry(_deployment("d-one")), provider)

        with self.assertRaises(BenchmarkExecutionBindingError):
            asyncio.run(executor.execute(_case(), _target("unbound")))
        self.assertEqual(provider.requests, [])

    def test_target_contradicting_the_bound_deployment_fails_closed(self) -> None:
        provider = _StubProvider(ProviderResponse(text="{}"))
        executor = _executor(_registry(_deployment("d-one")), provider)

        with self.assertRaises(BenchmarkExecutionBindingError):
            asyncio.run(executor.execute(_case(), _target(model="some/other-model")))
        self.assertEqual(provider.requests, [])

    def test_disabled_deployment_is_never_benchmarked(self) -> None:
        provider = _StubProvider(ProviderResponse(text="{}"))
        executor = _executor(_registry(_deployment("d-one", enabled=False)), provider)

        with self.assertRaises(BenchmarkExecutionBindingError):
            asyncio.run(executor.execute(_case(), _target()))
        self.assertEqual(provider.requests, [])

    def test_registry_bindings_cover_only_enabled_group_members(self) -> None:
        registry = _registry(
            _deployment("d-one"),
            _deployment("d-two", enabled=False),
            _deployment("d-three", model_group="fast-small"),
        )

        bindings = registry_bindings(registry, model_group="balanced", target_id_prefix="pd-")

        self.assertEqual(bindings, (TargetDeploymentBinding("pd-d-one", "d-one"),))

    def test_group_without_enabled_deployments_fails_closed(self) -> None:
        registry = _registry(_deployment("d-one", enabled=False))

        with self.assertRaises(BenchmarkExecutionBindingError):
            registry_bindings(registry, model_group="balanced", target_id_prefix="pd-")


class ExecutionEvidenceTests(unittest.TestCase):
    def test_successful_call_carries_terminal_execution_identity(self) -> None:
        provider = _StubProvider(
            ProviderResponse(
                text='{"answer": "yes", "citations": ["a"]}',
                usage=ProviderUsage(input_tokens=100, output_tokens=50),
            )
        )
        pricing = PricingMetadata(
            input_usd_per_million_tokens=Decimal("1.00"),
            output_usd_per_million_tokens=Decimal("2.00"),
            source_date=SOURCE_DATE,
            snapshot_version="test",
        )
        registry = _registry(_deployment("d-one", pricing=pricing))

        call = asyncio.run(_executor(registry, provider).execute(_case(), _target()))

        self.assertEqual(call.output, {"answer": "yes", "citations": ["a"]})
        self.assertEqual(call.provider, "nvidia")
        self.assertEqual(call.model, "nvidia/nemotron")
        self.assertEqual(call.deployment, "d-one")
        self.assertEqual(call.api_family, "openai-compatible")
        self.assertEqual(call.max_output_tokens, 512)
        self.assertEqual(call.latency_ms, 1500)
        self.assertEqual(call.cost_usd, Decimal("0.000200"))
        self.assertEqual(provider.requests[0].max_output_tokens, 512)

    def test_provider_error_becomes_availability_evidence(self) -> None:
        error = ProviderError(
            provider="nvidia",
            code=ProviderErrorCode.RATE_LIMIT,
            message="slow down",
            retryable=True,
            status_code=429,
        )
        executor = _executor(_registry(_deployment("d-one")), _StubProvider(error))

        with self.assertRaises(BenchmarkProviderFailure) as raised:
            asyncio.run(executor.execute(_case(), _target()))

        self.assertEqual(raised.exception.code, "rate_limit")
        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.latency_ms, 1500)


class ResponseNormalizationTests(unittest.TestCase):
    def test_plain_json_is_parsed(self) -> None:
        response = ProviderResponse(text='{"answer": "a", "citations": []}')

        self.assertEqual(normalize_response_output(response), {"answer": "a", "citations": []})

    def test_fenced_json_is_unwrapped(self) -> None:
        response = ProviderResponse(text='```json\n{"answer": "a", "citations": []}\n```')

        self.assertEqual(normalize_response_output(response), {"answer": "a", "citations": []})

    def test_unparseable_text_is_handed_to_the_scorer_unchanged(self) -> None:
        response = ProviderResponse(text="I cannot answer that.")

        self.assertEqual(normalize_response_output(response), "I cannot answer that.")

    def test_native_structured_output_wins_over_text(self) -> None:
        response = ProviderResponse(text="ignored", structured_output={"answer": "s"})

        self.assertEqual(normalize_response_output(response), {"answer": "s"})


class CostEvidenceTests(unittest.TestCase):
    def test_provider_reported_cost_is_preferred(self) -> None:
        usage = ProviderUsage(input_tokens=10, output_tokens=10, total_cost_usd=Decimal("0.5"))

        self.assertEqual(observed_cost_usd(None, usage), Decimal("0.5"))

    def test_missing_pricing_yields_no_invented_cost(self) -> None:
        self.assertIsNone(observed_cost_usd(None, ProviderUsage(input_tokens=1, output_tokens=1)))

    def test_free_tier_pricing_is_zero_not_absent(self) -> None:
        pricing = PricingMetadata(
            input_usd_per_million_tokens=Decimal("0.00"),
            output_usd_per_million_tokens=Decimal("0.00"),
            source_date=SOURCE_DATE,
            snapshot_version="free",
        )
        usage = ProviderUsage(input_tokens=1000, output_tokens=1000)

        self.assertEqual(observed_cost_usd(pricing, usage), Decimal("0.000000"))


if __name__ == "__main__":
    unittest.main()
