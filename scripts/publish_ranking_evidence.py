"""Run the reviewed ranking benchmark and publish the approved ranking artifact.

This closes the Phase 10 -> Phase 11 loop for one model group. Phase 10 runs the
deterministic dataset against every reviewed deployment in the group and persists an
immutable content-addressed snapshot. Phase 11 promotes that snapshot through explicit
operator-approved mappings and compiles the promoted quality/availability evidence onto
the existing static ranking base, producing a pinned approved ranking artifact.

The two phases stay separable: ``--snapshot-only`` stops after persisting evidence.
Promotion never invents a score. It fails closed when any deployment in the base policy
lacks promoted evidence, so a partial run can never silently leave part of the group on
hand-written placeholders.

Requires provider credentials in the process environment for every enabled deployment in
the selected group. Nothing here grants authorization: the Policy Model Router still
decides what may execute, and ranking still reorders only an already-authorized set.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from governed_llm_gateway_core.adapters import (
    EnvironmentProviderSecretResolver,
    build_static_provider_resolver,
    dump_approved_ranking_artifact_text,
    load_model_registry,
    load_provider_runtime_document,
    load_ranking_policy,
    validate_provider_runtime_registry,
)
from governed_llm_gateway_core.domain.evidence_ranking import compile_benchmark_hybrid_policy
from governed_llm_gateway_core.domain.ranking import RankingPolicy
from governed_llm_gateway_core.domain.ranking_evidence import build_promoted_ranking_evidence
from governed_llm_gateway_core.domain.ranking_override import ApprovedRankingArtifact

from benchmarks.contracts import (
    BenchmarkCase,
    BenchmarkObservation,
    BenchmarkSnapshot,
    BenchmarkTarget,
    BenchmarkWorkload,
)
from benchmarks.promotion import (
    PromotionMapping,
    canonical_promoted_evidence_json,
    promote_snapshot,
)
from benchmarks.provider_execution import RegistryDeploymentExecutor, registry_bindings
from benchmarks.runner import BenchmarkRunner, build_scorecards
from benchmarks.scoring import build_default_scorers
from benchmarks.snapshot import build_snapshot, persist_snapshot
from benchmarks.targets import load_targets
from benchmarks.workloads.rag_answer import load_rag_answer_dataset

ROOT = Path(__file__).resolve().parents[1]
RUNNER_VERSION = "registry-deployment-runner-v1"
TARGET_ID_PREFIX = "pd-balanced-"
ARTIFACT_FILENAME = "approved_ranking.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the explicit reviewed inputs this publication step is allowed to use."""
    parser = argparse.ArgumentParser(description="Publish approved ranking evidence.")
    parser.add_argument("--profile", default=Path("config/profiles/personal-default"), type=Path)
    parser.add_argument(
        "--dataset", default=Path("benchmarks/datasets/rag-answer-v1.json"), type=Path
    )
    parser.add_argument("--targets", default=Path("benchmarks/runners/targets-v4.json"), type=Path)
    parser.add_argument("--model-group", default="balanced")
    parser.add_argument("--runtime-workload", default="rag.answer")
    parser.add_argument("--evidence-root", default=Path("benchmarks/scorecards"), type=Path)
    parser.add_argument("--promotion-version", default="personal-default-balanced-v1")
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--policy-version", default="personal-default-v2")
    parser.add_argument("--score-snapshot-id", default="personal-default-rag-answer-v1")
    parser.add_argument("--snapshot-only", action="store_true")
    parser.add_argument("--timeout-seconds", default=120.0, type=float)
    parser.add_argument("--target-concurrency", default=1, type=int)
    return parser.parse_args(argv)


async def run_benchmark(args: argparse.Namespace) -> BenchmarkSnapshot:
    """Execute the dataset against every reviewed deployment and persist the snapshot."""
    profile: Path = ROOT / args.profile
    registry = load_model_registry(profile / "model_registry.yaml")
    runtime_document = load_provider_runtime_document(profile / "provider_runtime.json")
    validate_provider_runtime_registry(runtime_document, registry)
    resolver = build_static_provider_resolver(
        runtime_document.bindings, EnvironmentProviderSecretResolver()
    )

    dataset = load_rag_answer_dataset(ROOT / args.dataset)
    matrix_version, targets = load_targets(ROOT / args.targets)
    executor = RegistryDeploymentExecutor(
        registry=registry,
        resolver=resolver,
        bindings=registry_bindings(
            registry,
            model_group=args.model_group,
            target_id_prefix=TARGET_ID_PREFIX,
        ),
        timeout_seconds=args.timeout_seconds,
    )
    # Fail before spending a credential when a declared target contradicts the registry.
    for target in targets:
        executor.deployment_for(target)

    concurrency = max(1, int(args.target_concurrency))
    print(
        f"running {len(dataset.cases)} cases x {len(targets)} targets "
        f"(target concurrency {concurrency})",
        flush=True,
    )
    runner = BenchmarkRunner(executor, build_default_scorers())
    observations = await _run_targets(runner, dataset.cases, targets, concurrency)
    scorecards = build_scorecards(observations)

    snapshot = build_snapshot(
        benchmark_version=dataset.benchmark_version,
        runner_version=RUNNER_VERSION,
        run_date=datetime.now(UTC).date(),
        cases=dataset.cases,
        targets=targets,
        observations=observations,
        scorecards=scorecards,
        target_matrix_version=matrix_version,
    )
    # persist_snapshot already nests by benchmark version; scorecards/ is the reviewed,
    # committed evidence directory, while results/ stays local scratch and is gitignored.
    evidence_root: Path = ROOT / args.evidence_root
    evidence_root.mkdir(parents=True, exist_ok=True)
    path = persist_snapshot(evidence_root, snapshot)
    print(f"snapshot {snapshot.snapshot_id}")
    print(f"persisted {path.relative_to(ROOT)}")
    report_scorecards(snapshot)
    return snapshot


def publish(args: argparse.Namespace, snapshot: BenchmarkSnapshot) -> Path:
    """Promote the snapshot and write the pinned approved ranking artifact."""
    mappings = tuple(
        PromotionMapping(
            target_id=card.target_id,
            benchmark_workload=BenchmarkWorkload.RAG_ANSWER,
            deployment_id=card.target_id.removeprefix(TARGET_ID_PREFIX),
            runtime_workload=args.runtime_workload,
        )
        for card in sorted(snapshot.scorecards, key=lambda item: item.target_id)
    )
    approval_date = datetime.now(UTC).date()
    evidence = promote_snapshot(
        snapshot,
        promotion_version=args.promotion_version,
        approval_date=approval_date,
        approved_by=args.approved_by,
        mappings=mappings,
    )
    print(f"promoted evidence {evidence.evidence_id} ({len(evidence.records)} records)")

    promoted = build_promoted_ranking_evidence(
        json.loads(canonical_promoted_evidence_json(evidence))
    )
    profile: Path = ROOT / args.profile
    base_policy = restrict_to_workload(
        load_ranking_policy(profile / "ranking_policy.yaml"),
        args.runtime_workload,
    )
    artifact = ApprovedRankingArtifact(
        policy=compile_benchmark_hybrid_policy(
            base_policy,
            promoted,
            policy_version=args.policy_version,
            score_snapshot_id=args.score_snapshot_id,
            source_date=approval_date,
        ),
        approval_version=args.promotion_version,
        approval_date=approval_date,
        approved_by=args.approved_by,
    )

    target_path: Path = profile / ARTIFACT_FILENAME
    target_path.write_text(dump_approved_ranking_artifact_text(artifact), encoding="utf-8")
    print(f"approved ranking artifact {artifact.artifact_id}")
    print(f"wrote {target_path.relative_to(ROOT)}")
    return target_path


def restrict_to_workload(policy: RankingPolicy, runtime_workload: str) -> RankingPolicy:
    """Keep only the workload this publication run actually produced evidence for."""
    workloads = tuple(item for item in policy.workloads if item.workload == runtime_workload)
    if not workloads:
        raise ValueError(f"base ranking policy has no workload {runtime_workload!r}")
    return replace(policy, workloads=workloads)


async def _run_targets(
    runner: BenchmarkRunner,
    cases: Sequence[BenchmarkCase],
    targets: Sequence[BenchmarkTarget],
    concurrency: int,
) -> tuple[BenchmarkObservation, ...]:
    """Run each target's cases in declared order, optionally overlapping distinct targets.

    Cases stay sequential within a target so per-target latency evidence is never
    distorted by self-contention. Targets are separate provider endpoints, so overlapping
    them changes throughput rather than what any single target measures.
    """
    limit = asyncio.Semaphore(concurrency)

    async def _one(target: BenchmarkTarget) -> tuple[BenchmarkObservation, ...]:
        async with limit:
            observations, _ = await runner.run(cases, (target,))
            print(f"  done {target.target_id}", flush=True)
            return observations

    results = await asyncio.gather(*(_one(target) for target in targets))
    return tuple(item for group in results for item in group)


def report_scorecards(snapshot: BenchmarkSnapshot) -> None:
    """Print the per-target evidence a reviewer needs before approving promotion."""
    print(f"\n{'target':<52}{'quality':>9}{'avail':>8}{'p95 ms':>9}{'cost usd':>12}")
    for card in sorted(snapshot.scorecards, key=lambda item: item.target_id):
        quality = "n/a" if card.mean_quality_score is None else f"{card.mean_quality_score:.3f}"
        latency = "n/a" if card.latency_p95_ms is None else str(card.latency_p95_ms)
        print(
            f"{card.target_id:<52}{quality:>9}{card.availability_rate:>8.2f}"
            f"{latency:>9}{card.total_cost_usd:>12.6f}"
        )
    print()


def main(argv: list[str] | None = None) -> int:
    """Run the benchmark, then publish approved ranking evidence unless told not to."""
    args = parse_args(argv)
    snapshot = asyncio.run(run_benchmark(args))
    if args.snapshot_only:
        print("--snapshot-only: stopping before promotion")
        return 0
    publish(args, snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
