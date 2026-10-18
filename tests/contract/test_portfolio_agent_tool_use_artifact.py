from pathlib import Path

from governed_llm_gateway_core.adapters import load_approved_ranking_artifact

from scripts.personal_default_launcher import _APPROVED_RANKING_ARTIFACT_ID

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "config/profiles/personal-default"
PORTFOLIO_ARTIFACT = ROOT / "config/portfolio/agent-tool-use/approved_ranking.json"
PORTFOLIO_ARTIFACT_ID = "sha256:53cb9aeca737b2b4daa1e62b977bcb74128e238175f936292f74d515ca28274d"


def test_portfolio_tool_use_artifact_is_separate_from_the_active_rag_pin() -> None:
    portfolio_artifact = load_approved_ranking_artifact(
        PORTFOLIO_ARTIFACT, expected_artifact_id=PORTFOLIO_ARTIFACT_ID
    )
    active_artifact = load_approved_ranking_artifact(
        PROFILE / "approved_ranking.json",
        expected_artifact_id=_APPROVED_RANKING_ARTIFACT_ID,
    )

    assert _APPROVED_RANKING_ARTIFACT_ID == (
        "sha256:4d58f86b791267b2d38c6a95edad576ab35a5b97a8ee43a78a9d527ac8ee56ad"
    )
    assert {item.workload for item in portfolio_artifact.policy.workloads} == {"agent.tool-use"}
    assert {item.workload for item in active_artifact.policy.workloads} == {"rag.answer"}
    assert portfolio_artifact.artifact_id != active_artifact.artifact_id
