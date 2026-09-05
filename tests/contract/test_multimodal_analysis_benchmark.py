from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.contracts import BenchmarkCase, BenchmarkWorkload
from benchmarks.fixture_publication import load_fixture_publication_manifest
from benchmarks.fixtures import load_fixture_manifest
from benchmarks.scoring import build_default_scorers
from benchmarks.workloads.multimodal_analysis import (
    MULTIMODAL_ANALYSIS_SCORER_ID,
    assess_multimodal_analysis,
    load_multimodal_analysis_dataset,
    validate_multimodal_fixture_binding,
)

_FIXTURE_ID = "multimodal.quadrants_rgb_001"
_DIGEST = "sha256:c016362530bd9a02aff8d3bf0b7114b38d7499b03e2acacb566f657f94bb5f76"
_EXPECTED = {
    "top_left": "red",
    "top_right": "green",
    "bottom_left": "blue",
    "bottom_right": "yellow",
}


def _paths() -> tuple[Path, Path, Path]:
    repo_root = Path(__file__).resolve().parents[2]
    fixture_root = repo_root / "benchmarks" / "fixtures" / "multimodal-v1"
    return (
        repo_root / "benchmarks" / "datasets" / "multimodal-analysis-v1.json",
        fixture_root / "manifest.json",
        fixture_root / "publication.json",
    )


def _case(*, digest: str = _DIGEST) -> BenchmarkCase:
    return BenchmarkCase(
        case_id="multimodal.quadrant-colors.test",
        workload=BenchmarkWorkload.MULTIMODAL_ANALYSIS,
        scorer=MULTIMODAL_ANALYSIS_SCORER_ID,
        prompt="Inspect the four image quadrants.",
        expected=dict(_EXPECTED),
        metadata={
            "contract_version": "1.0",
            "synthetic": True,
            "fixture_id": _FIXTURE_ID,
            "fixture_media_type": "image/png",
            "fixture_digest": digest,
            "response_format": "quadrant_colors_v1",
        },
    )


def test_checked_in_multimodal_dataset_binds_to_reviewed_fixture_publication() -> None:
    dataset_path, fixture_manifest_path, publication_manifest_path = _paths()

    dataset = load_multimodal_analysis_dataset(
        dataset_path,
        fixture_manifest_path,
        publication_manifest_path,
    )

    assert dataset.benchmark_version == "multimodal-analysis-v1"
    assert len(dataset.cases) == 1
    case = dataset.cases[0]
    assert case.workload is BenchmarkWorkload.MULTIMODAL_ANALYSIS
    assert case.metadata["fixture_id"] == _FIXTURE_ID
    assert case.metadata["fixture_digest"] == _DIGEST


def test_multimodal_analysis_scores_exact_visual_answer() -> None:
    assessment = assess_multimodal_analysis(_case(), dict(_EXPECTED))

    assert assessment.score == Decimal("1")
    assert assessment.matched_quadrants == 4
    assert assessment.total_quadrants == 4
    assert assessment.issues == ()
    assert assessment.visual_task_success is True


def test_multimodal_analysis_scores_each_quadrant_independently() -> None:
    output = dict(_EXPECTED)
    output["bottom_right"] = "blue"

    assessment = assess_multimodal_analysis(_case(), output)

    assert assessment.score == Decimal("0.75")
    assert assessment.matched_quadrants == 3
    assert assessment.visual_task_success is False
    assert [(issue.code, issue.path) for issue in assessment.issues] == [
        ("wrong_color", "/bottom_right")
    ]


def test_multimodal_analysis_rejects_wrong_shape_without_partial_credit() -> None:
    assessment = assess_multimodal_analysis(
        _case(),
        {"top_left": "red", "top_right": "green"},
    )

    assert assessment.score == Decimal("0")
    assert assessment.matched_quadrants == 0
    assert assessment.issues[0].code == "invalid_output_shape"


def test_multimodal_analysis_reports_wrong_label_type() -> None:
    output = dict(_EXPECTED)
    output["top_left"] = 1

    assessment = assess_multimodal_analysis(_case(), output)

    assert assessment.score == Decimal("0.75")
    assert assessment.issues[0].code == "wrong_label_type"
    assert assessment.issues[0].path == "/top_left"


def test_multimodal_fixture_binding_rejects_dataset_digest_drift() -> None:
    _, fixture_manifest_path, publication_manifest_path = _paths()
    fixtures = load_fixture_manifest(fixture_manifest_path)
    publications = load_fixture_publication_manifest(publication_manifest_path)

    with pytest.raises(ValueError, match="fixture digest does not match fixture catalog"):
        validate_multimodal_fixture_binding(
            _case(digest="sha256:" + "0" * 64),
            fixtures,
            publications,
        )


def test_default_scorer_registry_includes_multimodal_analysis_v1() -> None:
    scorers = build_default_scorers()

    scorer = scorers[MULTIMODAL_ANALYSIS_SCORER_ID]
    assert scorer(_case(), dict(_EXPECTED)) == Decimal("1")
