"""Contract tests for deployment-owned activation settings above the staged bootstrap."""

from collections.abc import Iterator, Mapping
from decimal import Decimal
from pathlib import Path

import pytest
from governed_llm_gateway_api import GovernedDeploymentSettings, activate_governed_deployment
from governed_llm_gateway_core.domain.model_registry import ModelRegistryError


class RecordingEnvironment(Mapping[str, str]):
    """Environment mapping that records every credential lookup attempt."""

    def __init__(self) -> None:
        self.lookups: list[str] = []

    def __getitem__(self, key: str) -> str:
        self.lookups.append(key)
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0

    def get(self, key: str, default: str | None = None) -> str | None:
        self.lookups.append(key)
        return default


def _settings(root: Path, **overrides: object) -> GovernedDeploymentSettings:
    values: dict[str, object] = {
        "deployment_root": root,
        "model_registry_path": Path("config/model-registry.yaml"),
        "provider_runtime_path": Path("config/provider-runtime.json"),
        "client_auth_path": Path("config/client-auth.json"),
        "policy_router_path": Path("config/policy-router.json"),
        "ranking_policy_path": Path("config/ranking.yaml"),
        "default_max_latency_ms": 5_000,
        "default_max_cost_usd": Decimal("1.25"),
    }
    values.update(overrides)
    return GovernedDeploymentSettings(**values)  # type: ignore[arg-type]


def test_settings_resolve_relative_paths_deterministically(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    settings = _settings(root, complexity_routing_path=Path("config/complexity.json"))

    first = settings.bootstrap_paths
    second = settings.bootstrap_paths

    assert first == second
    assert first.process.model_registry_path == root / "config/model-registry.yaml"
    assert first.process.provider_runtime_path == root / "config/provider-runtime.json"
    assert first.process.client_auth_path == root / "config/client-auth.json"
    assert first.process.policy_router_path == root / "config/policy-router.json"
    assert first.ranking_policy_path == root / "config/ranking.yaml"
    assert first.complexity_routing_path == root / "config/complexity.json"
    assert settings.projection_defaults.max_latency_ms == 5_000
    assert settings.projection_defaults.max_cost_usd == Decimal("1.25")


def test_relative_artifact_path_cannot_escape_deployment_root(tmp_path: Path) -> None:
    settings = _settings(tmp_path.resolve(), model_registry_path=Path("../registry.yaml"))

    with pytest.raises(ValueError, match="model_registry_path must not escape deployment_root"):
        _ = settings.bootstrap_paths


def test_absolute_artifact_path_remains_explicit(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    external = (tmp_path.parent / "external-registry.yaml").resolve()
    settings = _settings(root, model_registry_path=external)

    assert settings.bootstrap_paths.process.model_registry_path == external


def test_ambiguous_ranking_source_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="static or approved, not both"):
        _settings(
            tmp_path.resolve(),
            approved_ranking_artifact_path=Path("approved.json"),
            expected_ranking_artifact_id="sha256:" + "a" * 64,
        )


def test_approved_ranking_requires_path_and_exact_expected_identity(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must be supplied together"):
        _settings(
            tmp_path.resolve(),
            ranking_policy_path=None,
            approved_ranking_artifact_path=Path("approved.json"),
        )


def test_invalid_projection_defaults_fail_during_secret_free_settings_validation(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="default max_latency_ms must be positive"):
        _settings(tmp_path.resolve(), default_max_latency_ms=0)


def test_invalid_artifact_fails_before_environment_secret_lookup(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    config = root / "config"
    config.mkdir()
    (config / "model-registry.yaml").write_text("not-a-mapping\n", encoding="utf-8")
    environment = RecordingEnvironment()
    settings = _settings(root)

    with pytest.raises(ModelRegistryError, match="root must be a mapping"):
        activate_governed_deployment(settings, environ=environment)

    assert environment.lookups == []
