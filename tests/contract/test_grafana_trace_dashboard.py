"""Contracts for the first read-only Grafana Tempo dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE_PATH = _ROOT / "compose.observability.yml"
_PROVIDER_PATH = _ROOT / "deploy/observability/grafana-dashboard-provider.yaml"
_DASHBOARD_PATH = _ROOT / "deploy/observability/gateway-traces-dashboard.json"
_WORKFLOW_PATH = _ROOT / ".github/workflows/grafana-dashboard.yml"

_DASHBOARD_UID = "governed-llm-gateway-traces"
_DASHBOARD_TITLE = "Governed LLM Gateway — Traces"
_TRACE_QUERY = '{ span:name = "llm.gateway.request" }'


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _dashboard() -> dict[str, Any]:
    payload: object = json.loads(_text(_DASHBOARD_PATH))
    assert isinstance(payload, dict)
    return payload


def test_compose_mounts_read_only_grafana_dashboard_provisioning() -> None:
    compose = _text(_COMPOSE_PATH)

    assert (
        "./deploy/observability/grafana-dashboard-provider.yaml:"
        "/etc/grafana/provisioning/dashboards/gateway.yaml:ro" in compose
    )
    assert (
        "./deploy/observability/gateway-traces-dashboard.json:"
        "/etc/grafana/dashboards/gateway-traces.json:ro" in compose
    )
    assert compose.count("127.0.0.1:3000:3000") == 1
    assert "0.0.0.0:3000:3000" not in compose
    assert "3200:3200" not in compose
    assert "  observability:\n    internal: true" in compose
    assert compose.count("      - grafana-host-access") == 1
    assert "  grafana-host-access:\n    driver: bridge" in compose


def test_dashboard_provider_is_file_backed_and_disallows_ui_updates() -> None:
    provider = _text(_PROVIDER_PATH)

    assert provider.count("  - name: Governed LLM Gateway") == 1
    assert "    orgId: 1" in provider
    assert "    folder: Governed LLM Gateway" in provider
    assert "    type: file" in provider
    assert "    allowUiUpdates: false" in provider
    assert "    options:\n      path: /etc/grafana/dashboards" in provider
    assert "http://" not in provider
    assert "https://" not in provider


def test_dashboard_is_read_only_and_uses_only_the_tempo_trace_query() -> None:
    dashboard = _dashboard()

    assert dashboard["uid"] == _DASHBOARD_UID
    assert dashboard["title"] == _DASHBOARD_TITLE
    assert dashboard["editable"] is False
    assert dashboard["refresh"] == "10s"

    panels = dashboard["panels"]
    assert isinstance(panels, list)
    assert len(panels) == 1
    panel = panels[0]
    assert isinstance(panel, dict)
    assert panel["type"] == "table"
    assert panel["datasource"] == {"type": "tempo", "uid": "tempo"}

    targets = panel["targets"]
    assert isinstance(targets, list)
    assert len(targets) == 1
    target = targets[0]
    assert isinstance(target, dict)
    assert target["datasource"] == {"type": "tempo", "uid": "tempo"}
    assert target["queryType"] == "traceql"
    assert target["query"] == _TRACE_QUERY
    assert target["limit"] == 20


def test_dashboard_contains_no_fake_metrics_mutations_or_external_backends() -> None:
    raw = _text(_DASHBOARD_PATH).lower()

    for banned_term in (
        "prometheus",
        "loki",
        "langfuse",
        "datadog",
        "mutation",
        "disable deployment",
        "reset circuit",
        "fake cost",
        "synthetic cost",
    ):
        assert banned_term not in raw


def test_grafana_dashboard_workflow_is_credential_free_and_fails_closed() -> None:
    workflow = _text(_WORKFLOW_PATH)

    assert "permissions:\n  contents: read" in workflow
    assert "docker compose -f compose.observability.yml up -d tempo grafana" in workflow
    assert "http://127.0.0.1:3000/api/health" in workflow
    assert (
        "http://127.0.0.1:3000/api/dashboards/uid/governed-llm-gateway-traces" in workflow
    )
    assert (
        'target.get("query") != \'{ span:name = "llm.gateway.request" }\'' in workflow
    )
    assert "metadata.get(\"provisioned\") is not True" in workflow
    assert "down --volumes --remove-orphans" in workflow
    assert "secrets." not in workflow
    assert "Authorization:" not in workflow
    assert "api-key" not in workflow.lower()
