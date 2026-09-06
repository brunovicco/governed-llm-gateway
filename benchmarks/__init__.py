"""Credential-free benchmark framework for Governed LLM Gateway evaluations."""

from .contracts import (
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkObservation,
    BenchmarkQualityMetric,
    BenchmarkSnapshot,
    BenchmarkTarget,
    BenchmarkWorkload,
    ObservationStatus,
    ProviderCall,
    Scorecard,
)
from .dataset import load_dataset
from .runner import (
    BenchmarkExecutor,
    BenchmarkProviderFailure,
    BenchmarkRunner,
    BenchmarkTargetMismatchError,
    build_scorecards,
)
from .scoring import (
    DeterministicScorer,
    QualityMeasurement,
    build_default_scorers,
    evaluate_scorer,
)
from .snapshot import (
    build_snapshot,
    canonical_snapshot_json,
    dataset_digest,
    persist_snapshot,
    target_matrix_digest,
)
from .targets import load_targets

__all__ = [
    "BenchmarkCase",
    "BenchmarkDataset",
    "BenchmarkExecutor",
    "BenchmarkObservation",
    "BenchmarkProviderFailure",
    "BenchmarkQualityMetric",
    "BenchmarkRunner",
    "BenchmarkSnapshot",
    "BenchmarkTarget",
    "BenchmarkTargetMismatchError",
    "BenchmarkWorkload",
    "DeterministicScorer",
    "ObservationStatus",
    "ProviderCall",
    "QualityMeasurement",
    "Scorecard",
    "build_default_scorers",
    "build_scorecards",
    "build_snapshot",
    "canonical_snapshot_json",
    "dataset_digest",
    "evaluate_scorer",
    "load_dataset",
    "load_targets",
    "persist_snapshot",
    "target_matrix_digest",
]
