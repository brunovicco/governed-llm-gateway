"""Agent tool-use ranking publication stays evidence-backed and deployment-bound."""

import unittest
from pathlib import Path

from governed_llm_gateway_core.adapters import load_model_registry

from benchmarks.contracts import BenchmarkWorkload
from benchmarks.targets import load_targets
from scripts.publish_ranking_evidence import (
    deployment_id_from_target,
    load_reviewed_dataset,
    normalized_artifact_filename,
)

ROOT = Path(__file__).resolve().parents[2]


class AgentToolUseRankingPublicationTests(unittest.TestCase):
    def test_reviewed_multi_step_dataset_is_supported_for_publication(self) -> None:
        dataset = load_reviewed_dataset(
            ROOT / "benchmarks/datasets/multi-step-tool-use-v1.json",
            BenchmarkWorkload.MULTI_STEP_TOOL_USE,
        )

        self.assertEqual(dataset.benchmark_version, "multi-step-tool-use-v1")
        self.assertEqual(len(dataset.cases), 4)
        self.assertTrue(
            all(case.workload is BenchmarkWorkload.MULTI_STEP_TOOL_USE for case in dataset.cases)
        )

    def test_agentic_target_matrix_matches_reviewed_registry_deployments(self) -> None:
        registry = load_model_registry(
            ROOT / "config/profiles/personal-default/model_registry.yaml"
        )
        _, targets = load_targets(ROOT / "benchmarks/runners/targets-agentic-v1.json")
        deployments = {deployment.deployment_id: deployment for deployment in registry.deployments}

        self.assertEqual(len(targets), 2)
        for target in targets:
            deployment_id = deployment_id_from_target(target.target_id, "pd-agentic-")
            deployment = deployments[deployment_id]
            self.assertEqual(deployment.model_group, "agentic-strong")
            self.assertEqual(deployment.provider, target.provider)
            self.assertEqual(deployment.model_id, target.model)
            self.assertEqual(deployment.api_family, target.api_family)
            self.assertTrue(deployment.capabilities.tool_calling)

    def test_target_prefix_and_artifact_filename_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            deployment_id_from_target("wrong-openai", "pd-agentic-")
        with self.assertRaises(ValueError):
            normalized_artifact_filename("../approved_ranking.json")

        self.assertEqual(
            normalized_artifact_filename("approved_ranking_agent_tool_use.json"),
            "approved_ranking_agent_tool_use.json",
        )


if __name__ == "__main__":
    unittest.main()
