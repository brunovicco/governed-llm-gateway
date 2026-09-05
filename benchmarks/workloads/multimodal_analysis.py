"""Deterministic multimodal-analysis benchmark contract and scorer."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from benchmarks.contracts import BenchmarkCase, BenchmarkDataset, BenchmarkWorkload, JsonValue
from benchmarks.fixture_publication import (
    BenchmarkFixturePublicationManifest,
    load_fixture_publication_manifest,
    validate_fixture_publications,
)
from benchmarks.fixtures import BenchmarkFixtureManifest, load_fixture_manifest

MULTIMODAL_ANALYSIS_BENCHMARK_VERSION = "multimodal-analysis-v1"
MULTIMODAL_ANALYSIS_CONTRACT_VERSION = "1.0"
MULTIMODAL_ANALYSIS_SCORER_ID = "multimodal_analysis_v1"

_QUADRANTS = ("top_left", "top_right", "bottom_left", "bottom_right")
_ALLOWED_METADATA_FIELDS = {
    "contract_version",
    "fixture_digest",
    "fixture_id",
    "fixture_media_type",
    "response_format",
    "synthetic",
}
_RESPONSE_FORMAT = "quadrant_colors_v1"


@dataclass(frozen=True, slots=True, order=True)
class MultimodalAnalysisIssue:
    """Stable reason code and JSON-pointer-like path for one visual-answer issue."""

    code: str
    path: str


@dataclass(frozen=True, slots=True)
class MultimodalAnalysisAssessment:
    """Explainable deterministic evidence for one structured visual answer."""

    score: Decimal
    matched_quadrants: int
    total_quadrants: int
    issues: tuple[MultimodalAnalysisIssue, ...]

    @property
    def visual_task_success(self) -> bool:
        """Return whether all reviewed quadrant labels matched exactly."""
        return self.score == Decimal("1") and not self.issues


def load_multimodal_analysis_dataset(
    dataset_path: Path,
    fixture_manifest_path: Path,
    publication_manifest_path: Path,
) -> BenchmarkDataset:
    """Load multimodal v1 and validate every case against published fixture provenance."""
    from benchmarks.dataset import load_dataset

    dataset = load_dataset(dataset_path)
    if dataset.benchmark_version != MULTIMODAL_ANALYSIS_BENCHMARK_VERSION:
        raise ValueError("multimodal analysis v1 requires benchmark_version multimodal-analysis-v1")

    case_ids = [case.case_id for case in dataset.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("multimodal analysis v1 case IDs must be unique")

    fixtures = load_fixture_manifest(fixture_manifest_path)
    publications = load_fixture_publication_manifest(publication_manifest_path)
    validate_fixture_publications(fixtures, publications)

    for case in dataset.cases:
        validate_multimodal_analysis_case(case)
        validate_multimodal_fixture_binding(case, fixtures, publications)
    return dataset


def validate_multimodal_analysis_case(case: BenchmarkCase) -> None:
    """Fail closed when a case drifts from the reviewed v1 visual-task contract."""
    if case.workload is not BenchmarkWorkload.MULTIMODAL_ANALYSIS:
        raise ValueError("multimodal analysis v1 dataset contains a different workload")
    if case.scorer != MULTIMODAL_ANALYSIS_SCORER_ID:
        raise ValueError("multimodal analysis v1 requires its versioned deterministic scorer")

    metadata = case.metadata
    unknown_metadata = sorted(set(metadata) - _ALLOWED_METADATA_FIELDS)
    if unknown_metadata:
        fields = ", ".join(unknown_metadata)
        raise ValueError(f"multimodal analysis v1 metadata contains unknown fields: {fields}")
    if metadata.get("contract_version") != MULTIMODAL_ANALYSIS_CONTRACT_VERSION:
        raise ValueError("multimodal analysis v1 contract_version must be 1.0")
    if metadata.get("synthetic") is not True:
        raise ValueError("multimodal analysis v1 cases must be explicitly synthetic")
    if metadata.get("response_format") != _RESPONSE_FORMAT:
        raise ValueError("multimodal analysis v1 response_format must be quadrant_colors_v1")

    for key in ("fixture_id", "fixture_media_type", "fixture_digest"):
        value = metadata.get(key)
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError(f"multimodal analysis v1 {key} must be a normalized string")

    _validated_expected(case.expected)


def validate_multimodal_fixture_binding(
    case: BenchmarkCase,
    fixtures: BenchmarkFixtureManifest,
    publications: BenchmarkFixturePublicationManifest,
) -> None:
    """Bind one benchmark case to the exact reviewed local and published fixture identity."""
    fixture_id = case.metadata.get("fixture_id")
    media_type = case.metadata.get("fixture_media_type")
    digest = case.metadata.get("fixture_digest")
    if (
        not isinstance(fixture_id, str)
        or not isinstance(media_type, str)
        or not isinstance(digest, str)
    ):
        raise ValueError("multimodal analysis v1 fixture metadata is invalid")

    fixture = fixtures.require(fixture_id)
    publication = publications.require(fixture_id)
    if fixture.media_type != media_type:
        raise ValueError("multimodal analysis v1 fixture media type does not match fixture catalog")
    if fixture.digest != digest:
        raise ValueError("multimodal analysis v1 fixture digest does not match fixture catalog")
    if publication.digest != digest:
        raise ValueError("multimodal analysis v1 fixture digest does not match publication catalog")


def assess_multimodal_analysis(
    case: BenchmarkCase,
    output: JsonValue,
) -> MultimodalAnalysisAssessment:
    """Return deterministic per-quadrant visual-answer evidence."""
    validate_multimodal_analysis_case(case)
    expected = _validated_expected(case.expected)

    if not isinstance(output, dict) or set(output) != set(_QUADRANTS):
        return _zero_assessment(MultimodalAnalysisIssue("invalid_output_shape", "/"))

    matches = 0
    issues: list[MultimodalAnalysisIssue] = []
    for quadrant in _QUADRANTS:
        value = output.get(quadrant)
        if not isinstance(value, str):
            issues.append(MultimodalAnalysisIssue("wrong_label_type", f"/{quadrant}"))
            continue
        if value == expected[quadrant]:
            matches += 1
        else:
            issues.append(MultimodalAnalysisIssue("wrong_color", f"/{quadrant}"))

    score = Decimal(matches) / Decimal(len(_QUADRANTS))
    return MultimodalAnalysisAssessment(
        score=score,
        matched_quadrants=matches,
        total_quadrants=len(_QUADRANTS),
        issues=tuple(issues),
    )


def score_multimodal_analysis(case: BenchmarkCase, output: JsonValue) -> Decimal:
    """Return the scalar v1 score consumed by BenchmarkRunner."""
    return assess_multimodal_analysis(case, output).score


def _validated_expected(expected: JsonValue) -> dict[str, str]:
    if not isinstance(expected, dict) or set(expected) != set(_QUADRANTS):
        raise ValueError(
            "multimodal analysis v1 expected output must contain exactly four quadrants"
        )

    normalized: dict[str, str] = {}
    for quadrant in _QUADRANTS:
        value = expected.get(quadrant)
        valid = (
            isinstance(value, str)
            and bool(value)
            and value.strip() == value
            and value.casefold() == value
        )
        if not valid:
            raise ValueError(
                "multimodal analysis v1 expected colors must be lowercase normalized strings"
            )
        normalized[quadrant] = value
    return normalized


def _zero_assessment(issue: MultimodalAnalysisIssue) -> MultimodalAnalysisAssessment:
    return MultimodalAnalysisAssessment(
        score=Decimal("0"),
        matched_quadrants=0,
        total_quadrants=len(_QUADRANTS),
        issues=(issue,),
    )
