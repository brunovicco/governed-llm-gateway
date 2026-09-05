"""Contract tests for explicit benchmark target API-family attestation."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from benchmarks import (
    BenchmarkCase,
    BenchmarkObservation,
    BenchmarkRunner,
    BenchmarkTarget,
    BenchmarkTargetMismatchError,
    BenchmarkWorkload,
    ProviderCall,
    Scorecard,
    build_default_scorers,
    build_snapshot,
    canonical_snapshot_json,
    load_targets,
)

_ROOT = Path(__file__).resolve().parents[2]
_TARGETS_V1 = _ROOT / "benchmarks/runners/targets-v1.json"
_TARGETS_V2 = _ROOT / "benchmarks/runners/targets-v2.json"
_TODAY = date(2026, 9, 5)


class _StaticExecutor:
    def __init__(self, call: ProviderCall) -> None:
        self._call = call

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        del case, target
        return self._call


def _case() -> BenchmarkCase:
    return BenchmarkCase(
        case_id="api-family-attestation",
        workload=BenchmarkWorkload.STRUCTURED_EXTRACTION,
        scorer="exact_json",
        prompt="Return the public synthetic value.",
        expected={"value": 1},
        metadata={"synthetic": True},
    )


def _target(*, api_family: str | None) -> BenchmarkTarget:
    return BenchmarkTarget(
        target_id="openai-control",
        provider="openai",
        model="gpt-control",
        api="openai/responses",
        configuration="access=test;reasoning=medium",
        source_date=_TODAY,
        api_family=api_family,
    )


def _call(*, api_family: str | None) -> ProviderCall:
    return ProviderCall(
        output={"value": 1},
        latency_ms=25,
        provider="openai",
        model="gpt-control",
        deployment="openai-primary",
        api_family=api_family,
    )


def _run(
    target: BenchmarkTarget,
    call: ProviderCall,
) -> tuple[tuple[BenchmarkObservation, ...], tuple[Scorecard, ...]]:
    return asyncio.run(
        BenchmarkRunner(_StaticExecutor(call), build_default_scorers()).run(
            (_case(),),
            (target,),
        )
    )


def test_historical_target_matrix_v1_remains_unattested() -> None:
    matrix_version, targets = load_targets(_TARGETS_V1)

    assert matrix_version == "phase10-targets-v1"
    assert len(targets) == 6
    assert all(target.api_family is None for target in targets)


def test_target_matrix_v2_declares_reviewed_api_families() -> None:
    matrix_version, targets = load_targets(_TARGETS_V2)

    assert matrix_version == "phase10-targets-v2"
    assert len(targets) == 6
    assert {target.api_family for target in targets} == {
        "anthropic",
        "gemini",
        "openai-compatible",
        "openai-responses",
    }
    by_provider = {target.provider: target.api_family for target in targets}
    assert by_provider["nvidia"] == "openai-compatible"
    assert by_provider["groq"] == "openai-compatible"
    assert by_provider["openrouter"] == "openai-compatible"
    assert by_provider["google"] == "gemini"
    assert by_provider["openai"] == "openai-responses"
    assert by_provider["anthropic"] == "anthropic"


def test_schema_1_0_rejects_api_family_extension(tmp_path: Path) -> None:
    payload = json.loads(_TARGETS_V1.read_text(encoding="utf-8"))
    payload["targets"][0]["api_family"] = "openai-compatible"
    path = tmp_path / "targets-v1-invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown fields: api_family"):
        load_targets(path)


def test_schema_1_1_requires_api_family(tmp_path: Path) -> None:
    payload = json.loads(_TARGETS_V2.read_text(encoding="utf-8"))
    del payload["targets"][0]["api_family"]
    path = tmp_path / "targets-v2-missing-api-family.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="api_family must be a normalized non-empty string"):
        load_targets(path)


@pytest.mark.parametrize("api_family", ["", " openai-responses", "openai-responses "])
def test_target_rejects_non_normalized_api_family(api_family: str) -> None:
    with pytest.raises(ValueError, match="api_family must be normalized"):
        _target(api_family=api_family)


def test_attested_target_accepts_exact_observed_api_family() -> None:
    observations, _ = _run(
        _target(api_family="openai-responses"),
        _call(api_family="openai-responses"),
    )

    assert observations[0].api_family == "openai-responses"


def test_attested_target_rejects_missing_observed_api_family() -> None:
    with pytest.raises(
        BenchmarkTargetMismatchError,
        match="requires observed terminal api_family evidence",
    ):
        _run(_target(api_family="openai-responses"), _call(api_family=None))


def test_attested_target_rejects_mismatched_observed_api_family() -> None:
    with pytest.raises(BenchmarkTargetMismatchError, match="api_family does not match"):
        _run(
            _target(api_family="openai-responses"),
            _call(api_family="openai-compatible"),
        )


def test_attested_target_rejects_call_without_execution_identity() -> None:
    call = ProviderCall(output={"value": 1}, latency_ms=25)

    with pytest.raises(
        BenchmarkTargetMismatchError,
        match="requires terminal execution evidence",
    ):
        _run(_target(api_family="openai-responses"), call)


def test_legacy_target_does_not_infer_attestation_from_api_surface() -> None:
    observations, _ = _run(
        _target(api_family=None),
        _call(api_family="openai-compatible"),
    )

    assert observations[0].api_family == "openai-compatible"


def test_snapshot_id_covers_explicit_target_api_family() -> None:
    target = _target(api_family="openai-responses")
    observations, scorecards = _run(target, _call(api_family="openai-responses"))
    first = build_snapshot(
        benchmark_version="target-api-family-attestation-v1",
        runner_version="benchmark-runner-v1",
        run_date=_TODAY,
        cases=(_case(),),
        targets=(target,),
        observations=observations,
        scorecards=scorecards,
    )
    changed_target = replace(target, api_family="openai-compatible")
    second = build_snapshot(
        benchmark_version="target-api-family-attestation-v1",
        runner_version="benchmark-runner-v1",
        run_date=_TODAY,
        cases=(_case(),),
        targets=(changed_target,),
        observations=observations,
        scorecards=scorecards,
    )

    assert first.snapshot_id != second.snapshot_id
    assert '"api_family":"openai-responses"' in canonical_snapshot_json(first)


def test_legacy_target_snapshot_shape_omits_target_api_family() -> None:
    target = _target(api_family=None)
    observations, scorecards = _run(target, _call(api_family="openai-responses"))
    snapshot = build_snapshot(
        benchmark_version="legacy-target-api-v1",
        runner_version="benchmark-runner-v1",
        run_date=_TODAY,
        cases=(_case(),),
        targets=(target,),
        observations=observations,
        scorecards=scorecards,
    )
    serialized = canonical_snapshot_json(snapshot)

    target_fragment = (
        serialized.split('"targets":[', maxsplit=1)[1].split('],', maxsplit=1)[0]
    )
    assert '"api_family":' not in target_fragment
