import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml  # type: ignore[import-untyped]

from scripts.composition_pin import PIN_PATH, RouterPinError, verify_router_revision

_REVISION = "3140181c45ce55a3139a292dbe30448012909fdf"


def test_router_pin_accepts_exact_full_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin = tmp_path / "router.commit"
    pin.write_text(_REVISION + "\n", encoding="utf-8")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=_REVISION + "\n"),
    )

    assert verify_router_revision(tmp_path, pin_path=pin) == _REVISION


def test_router_pin_rejects_revision_drift_without_printing_repository_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pin = tmp_path / "router.commit"
    pin.write_text(_REVISION + "\n", encoding="utf-8")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="a" * 40 + "\n"),
    )

    with pytest.raises(RouterPinError, match="does not match the reviewed pinned revision"):
        verify_router_revision(tmp_path, pin_path=pin)


def test_router_pin_rejects_short_pin_before_git_execution(tmp_path: Path) -> None:
    pin = tmp_path / "router.commit"
    pin.write_text("deadbeef\n", encoding="utf-8")

    with pytest.raises(RouterPinError, match="full lowercase commit ID"):
        verify_router_revision(tmp_path, pin_path=pin)


def test_credential_free_ci_checks_out_the_same_pinned_router_revision() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = yaml.safe_load(
        (root / ".github/workflows/portfolio-execution-demo.yml").read_text(encoding="utf-8")
    )
    checkout = next(
        step
        for step in workflow["jobs"]["execution-demo"]["steps"]
        if step.get("with", {}).get("repository") == "brunovicco/policy-model-router"
    )

    assert checkout["with"]["ref"] == PIN_PATH.read_text(encoding="utf-8").strip()
