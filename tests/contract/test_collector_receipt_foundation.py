"""Contracts for isolated positive Collector receipt verification."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE = _ROOT / "compose.collector-receipt.yml"
_COLLECTOR = _ROOT / "tests/integration/otel-collector-receipt.yaml"
_INTEGRATION_TEST = _ROOT / "tests/integration/test_collector_receipt.py"
_WORKFLOW = _ROOT / ".github/workflows/collector-receipt.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_receipt_collector_is_pinned_loopback_only_and_hardened() -> None:
    compose = _text(_COMPOSE)

    assert "image: otel/opentelemetry-collector-contrib:0.160.0" in compose
    assert ":latest" not in compose
    assert "127.0.0.1:4318:4318" in compose
    assert "0.0.0.0:4318:4318" not in compose
    assert "read_only: true" in compose
    assert "      - ALL" in compose
    assert "      - no-new-privileges:true" in compose
    assert "GATEWAY_COLLECTOR_RECEIPT_DIR" in compose


def test_receipt_collector_exports_only_to_ephemeral_file() -> None:
    config = _text(_COLLECTOR)

    assert "endpoint: 0.0.0.0:4318" in config
    assert "file/receipt:" in config
    assert "path: /receipts/traces.jsonl" in config
    assert "flush_interval: 100ms" in config
    assert "        - file/receipt" in config
    assert "otlp/tempo" not in config
    assert "http://" not in config
    assert "https://" not in config


def test_receipt_test_requires_appended_service_and_gateway_span_evidence() -> None:
    integration = _text(_INTEGRATION_TEST)

    assert '"governed-llm-gateway-collector-integration"' in integration
    assert '"llm.gateway.request"' in integration
    assert "initial_size = receipt.stat().st_size" in integration
    assert "handle.seek(initial_size)" in integration
    assert "observability.flush(5)" in integration
    assert "_EXPECTED_SPAN in appended and _EXPECTED_SERVICE in appended" in integration
    assert "prompt" not in integration.lower()
    assert "completion" not in integration.lower()
    assert "authorization" not in integration.lower()


def test_receipt_workflow_is_credential_free_bounded_and_always_tears_down() -> None:
    workflow = _text(_WORKFLOW)

    assert "timeout-minutes: 10" in workflow
    assert "for attempt in {1..30}" in workflow
    assert "GATEWAY_COLLECTOR_ENDPOINT" in workflow
    assert "GATEWAY_COLLECTOR_RECEIPT_FILE" in workflow
    assert "pytest -m integration tests/integration/test_collector_receipt.py" in workflow
    assert "if: always()" in workflow
    assert "down --volumes --remove-orphans" in workflow
    assert "secrets." not in workflow
