"""Promote one already-reviewed immutable benchmark snapshot without rerunning providers."""

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

from benchmarks.snapshot_loading import load_snapshot
from scripts.publish_ranking_evidence import publish, report_scorecards

ROOT = Path(__file__).resolve().parents[1]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the exact immutable evidence and publication metadata to promote."""
    parser = argparse.ArgumentParser(
        description="Promote one reviewed benchmark snapshot without executing providers."
    )
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--profile", default=Path("config/profiles/personal-default"), type=Path)
    parser.add_argument("--runtime-workload", required=True)
    parser.add_argument("--benchmark-workload", required=True)
    parser.add_argument("--target-id-prefix", required=True)
    parser.add_argument("--artifact-filename", required=True)
    parser.add_argument("--promotion-version", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--policy-version", required=True)
    parser.add_argument("--score-snapshot-id", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Verify, review-print, and promote exactly the supplied content-addressed snapshot."""
    args = parse_args(argv)
    snapshot_path = args.snapshot if args.snapshot.is_absolute() else ROOT / args.snapshot
    snapshot = load_snapshot(snapshot_path)

    print(f"reviewed snapshot {snapshot.snapshot_id}")
    print(f"loaded {snapshot_path.relative_to(ROOT) if snapshot_path.is_relative_to(ROOT) else snapshot_path}")
    report_scorecards(snapshot)

    publication_args = SimpleNamespace(
        profile=args.profile,
        runtime_workload=args.runtime_workload,
        benchmark_workload=args.benchmark_workload,
        target_id_prefix=args.target_id_prefix,
        artifact_filename=args.artifact_filename,
        promotion_version=args.promotion_version,
        approved_by=args.approved_by,
        policy_version=args.policy_version,
        score_snapshot_id=args.score_snapshot_id,
    )
    publish(publication_args, snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
