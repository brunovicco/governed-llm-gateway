import json
import unittest
from pathlib import Path

from governed_llm_gateway_core.adapters import (
    load_approved_ranking_artifact,
    load_model_registry,
    load_ranking_policy,
)
from governed_llm_gateway_core.domain.evidence_ranking import (
    EvidenceDrivenRankingPolicy,
    ScoreProvenanceMode,
)

from scripts.personal_default_launcher import _APPROVED_RANKING_ARTIFACT_ID

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "config/profiles/personal-default"
ARTIFACT_PATH = PROFILE / "approved_ranking.json"
SCORECARDS = ROOT / "benchmarks/scorecards"
RUNTIME_WORKLOAD = "rag.answer"
MODEL_GROUP = "balanced"


class ApprovedRankingArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.artifact = load_approved_ranking_artifact(
            ARTIFACT_PATH, expected_artifact_id=_APPROVED_RANKING_ARTIFACT_ID
        )

    def test_launcher_pins_the_committed_artifact(self) -> None:
        self.assertEqual(self.artifact.artifact_id, _APPROVED_RANKING_ARTIFACT_ID)

    def test_policy_is_benchmark_derived_not_hand_written(self) -> None:
        policy = self.artifact.policy
        self.assertIsInstance(policy, EvidenceDrivenRankingPolicy)
        assert isinstance(policy, EvidenceDrivenRankingPolicy)
        self.assertIs(policy.score_provenance_mode, ScoreProvenanceMode.BENCHMARK_HYBRID)
        self.assertTrue(policy.benchmark_snapshot_id.startswith("sha256:"))
        self.assertTrue(policy.promotion_evidence_id.startswith("sha256:"))
        self.assertIsNone(policy.manual_override_id)

    def test_covers_every_enabled_deployment_in_the_group(self) -> None:
        registry = load_model_registry(PROFILE / "model_registry.yaml")
        expected = {
            deployment.deployment_id
            for deployment in registry.deployments
            if deployment.model_group == MODEL_GROUP and deployment.enabled
        }
        workloads = {item.workload: item for item in self.artifact.policy.workloads}
        self.assertIn(RUNTIME_WORKLOAD, workloads)
        scored = {item.deployment_id for item in workloads[RUNTIME_WORKLOAD].deployments}

        self.assertEqual(scored, expected)

    def test_quality_and_availability_carry_real_signal(self) -> None:
        """The regression this closes: promoted scores must not be uniform placeholders."""
        deployments = {item.workload: item for item in self.artifact.policy.workloads}[
            RUNTIME_WORKLOAD
        ].deployments

        self.assertGreater(len({item.quality for item in deployments}), 1)
        self.assertGreater(len({item.availability for item in deployments}), 1)

    def test_referenced_benchmark_snapshot_is_committed(self) -> None:
        policy = self.artifact.policy
        assert isinstance(policy, EvidenceDrivenRankingPolicy)
        digest = policy.benchmark_snapshot_id.removeprefix("sha256:")
        matches = sorted(SCORECARDS.rglob(f"{digest}.json"))

        self.assertEqual(len(matches), 1, "approved artifact must cite a committed snapshot")
        snapshot = json.loads(matches[0].read_text(encoding="utf-8"))
        self.assertEqual(snapshot["snapshot_id"], policy.benchmark_snapshot_id)

    def test_static_base_policy_remains_available_for_recompilation(self) -> None:
        base = load_ranking_policy(PROFILE / "ranking_policy.yaml")

        self.assertIn(RUNTIME_WORKLOAD, {item.workload for item in base.workloads})


if __name__ == "__main__":
    unittest.main()
