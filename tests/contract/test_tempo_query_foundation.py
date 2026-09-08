"""Contracts for the credential-free Collector-to-Tempo query proof."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BASE_COMPOSE_PATH = _ROOT / "compose.observability.yml"
_QUERY_OVERLAY_PATH = _ROOT / "compose.tempo-query.yml"
_QUERY_TEMPO_CONFIG_PATH = _ROOT / "tests/integration/tempo-query.yaml"
_QUERY_WORKFLOW_PATH = _ROOT / ".github/workflows/tempo-query.yml"
_INTEGRATION_TEST_PATH = _ROOT / "tests/integration/test_tempo_query.py"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_tempo_query_overlay_exposes_only_reviewed_loopback_ports() -> None:
    base = _text(_BASE_COMPOSE_PATH)
    overlay = _text(_QUERY_OVERLAY_PATH)

    assert "3200:3200" not in base
    assert overlay.count("127.0.0.1:3200:3200") == 1
    assert "0.0.0.0:3200:3200" not in overlay
    assert "127.0.0.1:4318:4318" not in overlay
    assert "tempo-query-host: {}" in overlay
    assert "internal: true" not in overlay
    assert overlay.count("      - observability") == 2
    assert overlay.count("      - tempo-query-host") == 2
    assert (
        "./tests/integration/tempo-query.yaml:/etc/tempo/tempo.yaml:ro" in overlay
    )


def test_tempo_query_config_changes_recent_search_only_for_integration() -> None:
    base = _text(_ROOT / "deploy/observability/tempo.yaml")
    integration = _text(_QUERY_TEMPO_CONFIG_PATH)

    assert "query_end_cutoff" not in base
    assert "fail_on_high_lag" not in base
    assert "query_frontend:\n  query_end_cutoff: 0s" in integration
    assert "live_store:\n  fail_on_high_lag: false" in integration
    assert "backend: local" in integration
    assert "endpoint: 0.0.0.0:4317" in integration


def test_tempo_query_proof_emits_through_collector_and_queries_tempo() -> None:
    integration = _text(_INTEGRATION_TEST_PATH)

    assert "GATEWAY_TEMPO_QUERY_COLLECTOR_ENDPOINT" in integration
    assert "GATEWAY_TEMPO_QUERY_ENDPOINT" in integration
    assert "resource.service.name" in integration
    assert "span:name" in integration
    assert "llm.gateway.request" in integration
    assert "/api/v2/traces/" in integration
    assert "/api/search" in integration
    assert "tempo:4317" not in integration
    assert "4317" not in integration


def test_tempo_query_workflow_is_credential_free_and_always_tears_down() -> None:
    workflow = _text(_QUERY_WORKFLOW_PATH)

    assert "permissions:\n  contents: read" in workflow
    assert "GATEWAY_TEMPO_QUERY_COLLECTOR_ENDPOINT: http://127.0.0.1:4318/v1/traces" in workflow
    assert "GATEWAY_TEMPO_QUERY_ENDPOINT: http://127.0.0.1:3200" in workflow
    assert "docker compose -f compose.observability.yml -f compose.tempo-query.yml" in workflow
    assert "down --volumes --remove-orphans" in workflow
    assert "tests/integration/tempo-query.yaml" in workflow
    assert "secrets." not in workflow
    assert "provider" not in workflow.lower()
