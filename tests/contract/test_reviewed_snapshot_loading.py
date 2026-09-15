"""Reviewed snapshot promotion consumes exactly the persisted immutable evidence."""

import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import (
    BenchmarkCase,
    BenchmarkObservation,
    BenchmarkQualityMetric,
    BenchmarkTarget,
    BenchmarkWorkload,
    ObservationStatus,
    Scorecard,
)
from benchmarks.snapshot import build_snapshot, canonical_snapshot_json, persist_snapshot
from benchmarks.snapshot_loading import load_snapshot


class ReviewedSnapshotLoadingTests(unittest.TestCase):
    def test_persisted_snapshot_round_trips_with_content_identity(self) -> None:
        snapshot = _snapshot()
        with tempfile.TemporaryDirectory() as directory:
            path = persist_snapshot(Path(directory), snapshot)
            loaded = load_snapshot(path)

        self.assertEqual(loaded.snapshot_id, snapshot.snapshot_id)
        self.assertEqual(canonical_snapshot_json(loaded), canonical_snapshot_json(snapshot))

    def test_tampered_snapshot_fails_before_promotion(self) -> None:
        snapshot = _snapshot()
        with tempfile.TemporaryDirectory() as directory:
            path = persist_snapshot(Path(directory), snapshot)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["scorecards"][0]["total_cost_usd"] = "9"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "snapshot_id mismatch"):
                load_snapshot(path)


def _snapshot():
    case = BenchmarkCase(
        case_id="reviewed-snapshot.001",
        workload=BenchmarkWorkload.MULTI_STEP_TOOL_USE,
        scorer="reviewed_snapshot_test",
        prompt="Synthetic reviewed snapshot test prompt.",
        expected={"steps": []},
    )
    target = BenchmarkTarget(
        target_id="pd-agentic-test",
        provider="test",
        model="test-model",
        api="test-api",
        configuration="test-config",
        source_date=date(2026, 9, 15),
        api_family="openai-responses",
        max_output_tokens=100,
    )
    metrics = {
        BenchmarkQualityMetric.TOOL_SELECTION_ACCURACY: Decimal("1"),
        BenchmarkQualityMetric.TOOL_ARGUMENT_ACCURACY: Decimal("1"),
        BenchmarkQualityMetric.TRAJECTORY_SUCCESS: Decimal("1"),
    }
    observation = BenchmarkObservation(
        target_id=target.target_id,
        case_id=case.case_id,
        workload=case.workload,
        status=ObservationStatus.SUCCEEDED,
        quality_score=Decimal("1"),
        latency_ms=10,
        ttft_ms=None,
        input_units=10,
        output_units=5,
        cost_usd=Decimal("0.001"),
        fallback_count=0,
        provider="test",
        model="test-model",
        deployment="test-deployment",
        api_family="openai-responses",
        max_output_tokens=100,
        quality_metrics=metrics,
    )
    scorecard = Scorecard(
        target_id=target.target_id,
        workload=case.workload,
        total_cases=1,
        completed_calls=1,
        provider_failures=0,
        quality_successes=1,
        quality_failures=0,
        availability_rate=Decimal("1"),
        quality_success_rate=Decimal("1"),
        mean_quality_score=Decimal("1"),
        latency_p50_ms=10,
        latency_p95_ms=10,
        ttft_p50_ms=None,
        ttft_p95_ms=None,
        total_input_units=10,
        total_output_units=5,
        total_cost_usd=Decimal("0.001"),
        rate_limit_errors=0,
        fallback_frequency=Decimal("0"),
        provider_error_counts={},
        mean_quality_metrics=metrics,
    )
    return build_snapshot(
        benchmark_version="reviewed-snapshot-test-v1",
        runner_version="reviewed-snapshot-test-runner-v1",
        run_date=date(2026, 9, 15),
        cases=(case,),
        targets=(target,),
        observations=(observation,),
        scorecards=(scorecard,),
        target_matrix_version="reviewed-snapshot-test-matrix-v1",
    )


if __name__ == "__main__":
    unittest.main()
