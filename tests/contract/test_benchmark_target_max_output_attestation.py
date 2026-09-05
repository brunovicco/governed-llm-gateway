"""Contract tests for explicit benchmark target max-output attestation."""

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
_TARGETS_V2 = _ROOT / "benchmarks/runners/targets-v2.json"
_TARGETS_V3 = _ROOT / "benchmarks/runners/targets-v3.json"
_TODAY = date(2026, 9, 5)


class _StaticExecutor:
    def __init__(self, call: ProviderCall) -> None:
        self._call = call

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        del case, target
        return self._call


def _case() -> BenchmarkCase:
    return BenchmarkCase(
        case_id="max-output-attestation",
        workload=BenchmarkWorkload.STRUCTURED_EXTRACTION,
        scorer="exact_json",
        prompt="Return the public synthetic value.",
        expected={"value": 1},
        metadata={"synthetic": True},
    )


def _target(*, max_output_tokens: int | None) -> BenchmarkTarget:
    return BenchmarkTarget(
        target_id="openai-control",
        provider="openai",
        model="gpt-control",
        api="openai/responses",
        configuration="access=test;reasoning=medium;max_output=4096",
        source_date=_TODAY,
        api_family="openai-responses",
        max_output_tokens=max_output_tokens,
    )


def _call(*, max_output_tokens: int | None) -> ProviderCall:
    return ProviderCall(
        output={"value": 1},
        latency_ms=25,
        provider="openai",
        model="gpt-control",
        deployment="openai-primary",
        api_family="openai-responses",
        max_output_tokens=max_output_tokens,
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


def test_target_matrix_v3_declares_reviewed_max_output_tokens() -> None:
    matrix_version, targets = load_targets(_TARGETS_V3)

    assert matrix_version == "phase10-targets-v3"
    assert len(targets) == 6
    by_provider = {target.provider: target.max_output_tokens for target in targets}
    assert by_provider == {
        "nvidia": 16384,
        "groq": 4096,
        "openrouter": 4096,
        "google": 4096,
        "openai": 4096,
        "anthropic": 4096,
    }
    assert all(target.api_family is not None for target in targets)


def test_schema_1_1_rejects_max_output_tokens_extension(tmp_path: Path) -> None:
    payload = json.loads(_TARGETS_V2.read_text(encoding="utf-8"))
    payload["targets"][0]["max_output_tokens"] = 4096
    path = tmp_path / "targets-v2-invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown fields: max_output_tokens"):
        load_targets(path)


def test_schema_1_2_requires_max_output_tokens(tmp_path: Path) -> None:
    payload = json.loads(_TARGETS_V3.read_text(encoding="utf-8"))
    del payload["targets"][0]["max_output_tokens"]
    path = tmp_path / "targets-v3-missing-max-output.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="max_output_tokens must be a positive integer"):
        load_targets(path)


@pytest.mark.parametrize("value", [0, -1, True, "4096"])
def test_schema_1_2_rejects_invalid_max_output_tokens(tmp_path: Path, value: object) -> None:
    payload = json.loads(_TARGETS_V3.read_text(encoding="utf-8"))
    payload["targets"][0]["max_output_tokens"] = value
    path = tmp_path / "targets-v3-invalid-max-output.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="max_output_tokens must be a positive integer"):
        load_targets(path)


@pytest.mark.parametrize("max_output_tokens", [0, -1])
def test_target_rejects_non_positive_max_output_tokens(max_output_tokens: int) -> None:
    with pytest.raises(ValueError, match="max_output_tokens must be positive"):
        _target(max_output_tokens=max_output_tokens)


def test_attested_target_accepts_exact_observed_max_output_tokens() -> None:
    observations, _ = _run(
        _target(max_output_tokens=4096),
        _call(max_output_tokens=4096),
    )

    assert observations[0].max_output_tokens == 4096


def test_attested_target_rejects_missing_observed_max_output_tokens() -> None:
    with pytest.raises(
        BenchmarkTargetMismatchError,
        match="max_output_tokens requires observed terminal evidence",
    ):
        _run(_target(max_output_tokens=4096), _call(max_output_tokens=None))


def test_attested_target_rejects_mismatched_observed_max_output_tokens() -> None:
    with pytest.raises(BenchmarkTargetMismatchError, match="max_output_tokens does not match"):
        _run(
            _target(max_output_tokens=4096),
            _call(max_output_tokens=2048),
        )


def test_max_output_attested_target_rejects_call_without_execution_identity() -> None:
    call = ProviderCall(output={"value": 1}, latency_ms=25)

    with pytest.raises(
        BenchmarkTargetMismatchError,
        match="execution attestation requires terminal execution evidence",
    ):
        _run(_target(max_output_tokens=4096), call)


def test_legacy_target_does_not_infer_max_output_from_configuration_string() -> None:
    target = _target(max_output_tokens=None)
    changed = replace(
        target,
        configuration="access=test;reasoning=medium;max_output=999999",
    )
    observations, _ = _run(changed, _call(max_output_tokens=4096))

    assert observations[0].max_output_tokens == 4096


def test_provider_call_max_output_requires_execution_identity() -> None:
    with pytest.raises(ValueError, match="max_output_tokens requires execution identity"):
        ProviderCall(output={"value": 1}, latency_ms=25, max_output_tokens=4096)


def test_snapshot_id_covers_declared_and_observed_max_output_tokens() -> None:
    target = _target(max_output_tokens=4096)
    observations, scorecards = _run(target, _call(max_output_tokens=4096))
    first = build_snapshot(
        benchmark_version="target-max-output-attestation-v1",
        runner_version="benchmark-runner-v1",
        run_date=_TODAY,
        cases=(_case(),),
        targets=(target,),
        observations=observations,
        scorecards=scorecards,
    )
    changed_target = replace(target, max_output_tokens=8192)
    second = build_snapshot(
        benchmark_version="target-max-output-attestation-v1",
        runner_version="benchmark-runner-v1",
        run_date=_TODAY,
        cases=(_case(),),
        targets=(changed_target,),
        observations=observations,
        scorecards=scorecards,
    )

    assert first.snapshot_id != second.snapshot_id
    serialized = canonical_snapshot_json(first)
    assert '"max_output_tokens":4096' in serialized


def test_legacy_target_snapshot_shape_omits_declared_max_output_tokens() -> None:
    target = _target(max_output_tokens=None)
    observations, scorecards = _run(target, _call(max_output_tokens=4096))
    snapshot = build_snapshot(
        benchmark_version="legacy-target-max-output-v1",
        runner_version="benchmark-runner-v1",
        run_date=_TODAY,
        cases=(_case(),),
        targets=(target,),
        observations=observations,
        scorecards=scorecards,
    )
    serialized = canonical_snapshot_json(snapshot)

    target_fragment = serialized.split('"targets":[', maxsplit=1)[1].split("],", maxsplit=1)[0]
    assert '"max_output_tokens":' not in target_fragment
    assert '"max_output_tokens":4096' in serialized
