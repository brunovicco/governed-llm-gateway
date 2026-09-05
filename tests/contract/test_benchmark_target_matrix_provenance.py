"""Contract tests for explicit benchmark target-matrix snapshot provenance."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from benchmarks import (
    BenchmarkCase,
    BenchmarkSnapshot,
    BenchmarkWorkload,
    build_snapshot,
    canonical_snapshot_json,
    load_targets,
    target_matrix_digest,
)

_ROOT = Path(__file__).resolve().parents[2]
_TARGETS_V3 = _ROOT / "benchmarks/runners/targets-v3.json"
_RUN_DATE = date(2026, 9, 5)


def _case() -> BenchmarkCase:
    return BenchmarkCase(
        case_id="target-matrix-provenance",
        workload=BenchmarkWorkload.STRUCTURED_EXTRACTION,
        scorer="exact_json",
        prompt="Return the public synthetic value.",
        expected={"value": 1},
        metadata={"synthetic": True},
    )


def test_target_matrix_digest_is_deterministic_for_checked_in_v3() -> None:
    matrix_version, targets = load_targets(_TARGETS_V3)

    first = target_matrix_digest(matrix_version, targets)
    second = target_matrix_digest(matrix_version, targets)

    assert first == second
    assert first.startswith("sha256:")
    assert len(first) == len("sha256:") + 64


def test_target_matrix_digest_covers_matrix_version_and_target_configuration() -> None:
    matrix_version, targets = load_targets(_TARGETS_V3)
    baseline = target_matrix_digest(matrix_version, targets)

    changed_version = target_matrix_digest("phase10-targets-v3-revision", targets)
    changed_target = replace(
        targets[0],
        configuration=targets[0].configuration + ";review=changed",
    )
    changed_configuration = target_matrix_digest(
        matrix_version,
        (changed_target, *targets[1:]),
    )

    assert changed_version != baseline
    assert changed_configuration != baseline


def test_target_matrix_digest_covers_attested_fields_and_source_date() -> None:
    matrix_version, targets = load_targets(_TARGETS_V3)
    baseline = target_matrix_digest(matrix_version, targets)

    changed_max_output = replace(
        targets[0],
        max_output_tokens=targets[0].max_output_tokens + 1
        if targets[0].max_output_tokens is not None
        else 1,
    )
    changed_api_family = replace(targets[0], api_family="reviewed-different-family")
    changed_source_date = replace(targets[0], source_date=date(2026, 9, 6))

    assert target_matrix_digest(matrix_version, (changed_max_output, *targets[1:])) != baseline
    assert target_matrix_digest(matrix_version, (changed_api_family, *targets[1:])) != baseline
    assert target_matrix_digest(matrix_version, (changed_source_date, *targets[1:])) != baseline


@pytest.mark.parametrize("matrix_version", ["", " phase10-targets-v3", "phase10-targets-v3 "])
def test_target_matrix_digest_rejects_non_normalized_version(matrix_version: str) -> None:
    _, targets = load_targets(_TARGETS_V3)

    with pytest.raises(ValueError, match="target matrix version must be non-empty and normalized"):
        target_matrix_digest(matrix_version, targets)


def test_snapshot_v1_1_exposes_target_matrix_version_and_digest() -> None:
    matrix_version, targets = load_targets(_TARGETS_V3)
    expected_digest = target_matrix_digest(matrix_version, targets)

    snapshot = build_snapshot(
        benchmark_version="target-matrix-provenance-v1",
        runner_version="benchmark-runner-v1",
        run_date=_RUN_DATE,
        cases=(_case(),),
        targets=targets,
        observations=(),
        scorecards=(),
        target_matrix_version=matrix_version,
    )
    serialized = canonical_snapshot_json(snapshot)

    assert snapshot.schema_version == "1.1"
    assert snapshot.target_matrix_version == matrix_version
    assert snapshot.target_matrix_digest == expected_digest
    assert f'"target_matrix_version":"{matrix_version}"' in serialized
    assert f'"target_matrix_digest":"{expected_digest}"' in serialized


def test_snapshot_id_covers_target_matrix_version() -> None:
    matrix_version, targets = load_targets(_TARGETS_V3)

    first = build_snapshot(
        benchmark_version="target-matrix-provenance-v1",
        runner_version="benchmark-runner-v1",
        run_date=_RUN_DATE,
        cases=(_case(),),
        targets=targets,
        observations=(),
        scorecards=(),
        target_matrix_version=matrix_version,
    )
    second = build_snapshot(
        benchmark_version="target-matrix-provenance-v1",
        runner_version="benchmark-runner-v1",
        run_date=_RUN_DATE,
        cases=(_case(),),
        targets=targets,
        observations=(),
        scorecards=(),
        target_matrix_version="phase10-targets-v3-revision",
    )

    assert first.snapshot_id != second.snapshot_id
    assert first.target_matrix_digest != second.target_matrix_digest


def test_legacy_snapshot_shape_remains_schema_v1_0_without_matrix_provenance() -> None:
    _, targets = load_targets(_TARGETS_V3)

    snapshot = build_snapshot(
        benchmark_version="legacy-snapshot-v1",
        runner_version="benchmark-runner-v1",
        run_date=_RUN_DATE,
        cases=(_case(),),
        targets=targets,
        observations=(),
        scorecards=(),
    )
    serialized = canonical_snapshot_json(snapshot)

    assert snapshot.schema_version == "1.0"
    assert snapshot.target_matrix_version is None
    assert snapshot.target_matrix_digest is None
    assert '"target_matrix_version"' not in serialized
    assert '"target_matrix_digest"' not in serialized


def test_snapshot_contract_rejects_matrix_provenance_on_schema_v1_0() -> None:
    _, targets = load_targets(_TARGETS_V3)

    with pytest.raises(ValueError, match="schema 1.0 must not carry target matrix provenance"):
        BenchmarkSnapshot(
            schema_version="1.0",
            benchmark_version="legacy-snapshot-v1",
            runner_version="benchmark-runner-v1",
            run_date=_RUN_DATE,
            dataset_digest="sha256:" + "1" * 64,
            snapshot_id="sha256:" + "2" * 64,
            targets=targets,
            observations=(),
            scorecards=(),
            target_matrix_version="phase10-targets-v3",
            target_matrix_digest="sha256:" + "3" * 64,
        )


def test_snapshot_contract_requires_complete_schema_v1_1_matrix_provenance() -> None:
    _, targets = load_targets(_TARGETS_V3)

    with pytest.raises(ValueError, match="requires canonical target_matrix_digest"):
        BenchmarkSnapshot(
            schema_version="1.1",
            benchmark_version="target-matrix-provenance-v1",
            runner_version="benchmark-runner-v1",
            run_date=_RUN_DATE,
            dataset_digest="sha256:" + "1" * 64,
            snapshot_id="sha256:" + "2" * 64,
            targets=targets,
            observations=(),
            scorecards=(),
            target_matrix_version="phase10-targets-v3",
            target_matrix_digest=None,
        )
