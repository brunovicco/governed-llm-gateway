"""Repository-profile checks for the read-only ranking coverage audit."""

from pathlib import Path

import pytest

from scripts.audit_ranking_coverage import audit_coverage

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "config/profiles/personal-default"
ACTIVE_ARTIFACT = PROFILE / "approved_ranking.json"
ACTIVE_ID = "sha256:4d58f86b791267b2d38c6a95edad576ab35a5b97a8ee43a78a9d527ac8ee56ad"


def test_personal_default_reports_actual_active_coverage() -> None:
    report = audit_coverage(
        profile=PROFILE,
        artifact_path=ACTIVE_ARTIFACT,
        expected_artifact_id=ACTIVE_ID,
    )
    assert report["artifact_id"] == ACTIVE_ID
    assert report["covered_workloads"] == ["rag.answer"]
    assert report["missing_workloads"] == [
        "agent.orchestration",
        "agent.tool-use",
        "classification.simple",
        "code.generate",
        "code.review",
        "extraction.structured",
        "reasoning.complex",
        "security.analysis",
    ]


def test_audit_refuses_an_incorrect_pin() -> None:
    with pytest.raises(ValueError):
        audit_coverage(
            profile=PROFILE,
            artifact_path=ACTIVE_ARTIFACT,
            expected_artifact_id="sha256:" + "0" * 64,
        )
