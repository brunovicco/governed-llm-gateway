"""Credential-free benchmark framework for Governed LLM Gateway evaluations."""

from .contracts import (
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkObservation,
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
from .scoring import DeterministicScorer, build_default_scorers
from .snapshot import (
    build_snapshot,
    canonical_snapshot_json,
    dataset_digest,
    persist_snapshot,
)
from .targets import load_targets

__all__ = [
    "BenchmarkCase",
    "BenchmarkDataset",
    "BenchmarkExecutor",
    "BenchmarkObservation",
    "BenchmarkProviderFailure",
    "BenchmarkRunner",
    "BenchmarkSnapshot",
    "BenchmarkTarget",
    "BenchmarkTargetMismatchError",
    "BenchmarkWorkload",
    "DeterministicScorer",
    "ObservationStatus",
    "ProviderCall",
    "Scorecard",
    "build_default_scorers",
    "build_scorecards",
    "build_snapshot",
    "canonical_snapshot_json",
    "dataset_digest",
    "load_dataset",
    "load_targets",
    "persist_snapshot",
]
