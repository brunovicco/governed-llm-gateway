"""Audit approved ranking coverage without loading credentials or serving requests."""

import argparse
import json
from pathlib import Path

from governed_llm_gateway_core.adapters import (
    load_approved_ranking_artifact,
    load_ranking_policy,
)


def audit_coverage(
    *, profile: Path, artifact_path: Path, expected_artifact_id: str
) -> dict[str, object]:
    """Compare one exactly pinned approved artifact with the profile's declared workloads."""
    base = load_ranking_policy(profile / "ranking_policy.yaml")
    artifact = load_approved_ranking_artifact(
        artifact_path, expected_artifact_id=expected_artifact_id
    )
    declared = {item.workload: item for item in base.workloads}
    active = {item.workload: item for item in artifact.policy.workloads}
    for workload, policy in active.items():
        reference = declared.get(workload)
        if reference is None:
            raise ValueError(f"approved artifact contains undeclared workload: {workload}")
        approved_deployments = {item.deployment_id for item in policy.deployments}
        declared_deployments = {item.deployment_id for item in reference.deployments}
        if approved_deployments != declared_deployments:
            raise ValueError(f"approved artifact deployment coverage differs: {workload}")
    return {
        "artifact_id": artifact.artifact_id,
        "covered_workloads": sorted(active),
        "missing_workloads": sorted(declared.keys() - active.keys()),
        "profile": profile.as_posix(),
    }


def main() -> int:
    """Print metadata-only coverage for an explicit artifact and exact expected identity."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--artifact", required=True, type=Path)
    parser.add_argument("--expected-artifact-id", required=True)
    args = parser.parse_args()
    try:
        report = audit_coverage(
            profile=args.profile,
            artifact_path=args.artifact,
            expected_artifact_id=args.expected_artifact_id,
        )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"ranking coverage audit failed: {exc}\n")
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
