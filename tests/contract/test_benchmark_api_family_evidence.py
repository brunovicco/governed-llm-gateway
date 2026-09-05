"""Contract tests for benchmark-side terminal API-family evidence."""

import asyncio
from datetime import date
from uuid import UUID

import pytest
from governed_llm_gateway_contracts import (
    ExecutionStatus,
    GatewayResponse,
    PolicyProvenance,
    ProviderExecution,
    RoutingProvenance,
)

from benchmarks import (
    BenchmarkCase,
    BenchmarkRunner,
    BenchmarkTarget,
    BenchmarkWorkload,
    ProviderCall,
    build_default_scorers,
    build_snapshot,
    canonical_snapshot_json,
)
from benchmarks.multimodal_response import normalize_multimodal_gateway_response

_RUN_DATE = date(2026, 9, 5)


class _StaticExecutor:
    def __init__(self, call: ProviderCall) -> None:
        self._call = call

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        del case, target
        return self._call


def _routing() -> RoutingProvenance:
    return RoutingProvenance(
        routing_decision_id="sha256:" + "1" * 64,
        policy=PolicyProvenance(
            decision_id="policy-decision",
            policy_id="gateway-policy",
            policy_version="1.0.0",
            policy_digest="sha256:" + "2" * 64,
        ),
        authorized_model_group="vision",
        model_registry_digest="sha256:" + "3" * 64,
        ranking_policy_version="ranking-v1",
        provider="openai",
        model="gpt-control",
        deployment="openai-primary",
        fallback_sequence=("openai-primary",),
    )


def _case() -> BenchmarkCase:
    return BenchmarkCase(
        case_id="api-family-evidence",
        workload=BenchmarkWorkload.MULTIMODAL_ANALYSIS,
        scorer="exact_json",
        prompt="Return the synthetic visual label.",
        expected={"label": "circle"},
        metadata={"synthetic": True},
    )


def _target() -> BenchmarkTarget:
    return BenchmarkTarget(
        target_id="openai-control",
        provider="openai",
        model="gpt-control",
        api="historical-target-api-vocabulary",
        configuration="benchmark-config-v1",
        source_date=_RUN_DATE,
    )


def _run(call: ProviderCall):
    return asyncio.run(
        BenchmarkRunner(_StaticExecutor(call), build_default_scorers()).run(
            (_case(),),
            (_target(),),
        )
    )


def test_gateway_normalization_preserves_terminal_api_family() -> None:
    call = normalize_multimodal_gateway_response(
        GatewayResponse(
            request_id=UUID("38383838-3838-4838-8838-383838383838"),
            status=ExecutionStatus.SUCCEEDED,
            content='{"label":"circle"}',
            routing=_routing(),
            execution=ProviderExecution(
                provider="openai",
                model="gpt-control",
                deployment="openai-primary",
                status=ExecutionStatus.SUCCEEDED,
                latency_ms=21,
                api_family="openai-responses",
            ),
        )
    )

    assert call.api_family == "openai-responses"


def test_runner_and_snapshot_preserve_api_family_without_attesting_target_api() -> None:
    observations, scorecards = _run(
        ProviderCall(
            output={"label": "circle"},
            latency_ms=21,
            provider="openai",
            model="gpt-control",
            deployment="openai-primary",
            api_family="openai-responses",
        )
    )

    observation = observations[0]
    assert observation.api_family == "openai-responses"
    snapshot = build_snapshot(
        benchmark_version="api-family-evidence-v1",
        runner_version="benchmark-runner-v1",
        run_date=_RUN_DATE,
        cases=(_case(),),
        targets=(_target(),),
        observations=observations,
        scorecards=scorecards,
    )
    serialized = canonical_snapshot_json(snapshot)
    assert '"api_family":"openai-responses"' in serialized
    assert '"api":"historical-target-api-vocabulary"' in serialized


def test_snapshot_id_covers_observed_api_family() -> None:
    first_observations, first_scorecards = _run(
        ProviderCall(
            output={"label": "circle"},
            latency_ms=21,
            provider="openai",
            model="gpt-control",
            deployment="openai-primary",
            api_family="openai-responses",
        )
    )
    second_observations, second_scorecards = _run(
        ProviderCall(
            output={"label": "circle"},
            latency_ms=21,
            provider="openai",
            model="gpt-control",
            deployment="openai-primary",
            api_family="openai-compatible",
        )
    )

    first = build_snapshot(
        benchmark_version="api-family-evidence-v1",
        runner_version="benchmark-runner-v1",
        run_date=_RUN_DATE,
        cases=(_case(),),
        targets=(_target(),),
        observations=first_observations,
        scorecards=first_scorecards,
    )
    second = build_snapshot(
        benchmark_version="api-family-evidence-v1",
        runner_version="benchmark-runner-v1",
        run_date=_RUN_DATE,
        cases=(_case(),),
        targets=(_target(),),
        observations=second_observations,
        scorecards=second_scorecards,
    )

    assert first.snapshot_id != second.snapshot_id


def test_legacy_execution_identity_remains_valid_without_api_family() -> None:
    observations, scorecards = _run(
        ProviderCall(
            output={"label": "circle"},
            latency_ms=21,
            provider="openai",
            model="gpt-control",
            deployment="openai-primary",
        )
    )
    snapshot = build_snapshot(
        benchmark_version="legacy-execution-identity-v1",
        runner_version="benchmark-runner-v1",
        run_date=_RUN_DATE,
        cases=(_case(),),
        targets=(_target(),),
        observations=observations,
        scorecards=scorecards,
    )

    assert '"api_family":' not in canonical_snapshot_json(snapshot)


@pytest.mark.parametrize("api_family", ["", " openai-responses", "openai-responses "])
def test_provider_call_rejects_non_normalized_api_family(api_family: str) -> None:
    with pytest.raises(ValueError, match="api_family must be normalized"):
        ProviderCall(
            output={"label": "circle"},
            latency_ms=1,
            provider="openai",
            model="gpt-control",
            deployment="openai-primary",
            api_family=api_family,
        )


def test_api_family_requires_execution_identity() -> None:
    with pytest.raises(ValueError, match="api_family requires execution identity"):
        ProviderCall(
            output={"label": "circle"},
            latency_ms=1,
            api_family="openai-responses",
        )
