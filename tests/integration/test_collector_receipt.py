"""Positive Collector receipt evidence for stable Gateway observability metadata."""

import os
import time
from pathlib import Path

import pytest
from a2a_otel_kit import Observability, ObservabilitySettings

_ENDPOINT_ENV = "GATEWAY_COLLECTOR_ENDPOINT"
_RECEIPT_ENV = "GATEWAY_COLLECTOR_RECEIPT_FILE"
_EXPECTED_SERVICE = "governed-llm-gateway-collector-integration"
_EXPECTED_SPAN = "llm.gateway.request"
_RECEIPT_TIMEOUT_SECONDS = 5.0


@pytest.mark.integration
def test_collector_receives_gateway_metadata_span() -> None:
    """Require positive Collector evidence beyond exporter flush success."""
    endpoint = os.environ.get(_ENDPOINT_ENV)
    receipt_value = os.environ.get(_RECEIPT_ENV)
    if endpoint is None or receipt_value is None:
        pytest.skip(f"set {_ENDPOINT_ENV} and {_RECEIPT_ENV} to run Collector receipt integration")

    receipt = Path(receipt_value).resolve()
    if not receipt.is_file():
        pytest.fail(f"Collector receipt file does not exist: {receipt}")
    initial_size = receipt.stat().st_size

    observability = Observability.configure(
        ObservabilitySettings(
            service_name=_EXPECTED_SERVICE,
            service_version="0.1.0",
            environment="integration",
            enabled=True,
            otlp_endpoint=endpoint,
            otlp_timeout_seconds=5,
        )
    )
    with observability.start_span(_EXPECTED_SPAN):
        pass
    try:
        assert observability.flush(5), "OTLP exporter did not flush within five seconds"
    finally:
        observability.shutdown(5)

    deadline = time.monotonic() + _RECEIPT_TIMEOUT_SECONDS
    appended = ""
    while time.monotonic() < deadline:
        with receipt.open("rb") as handle:
            handle.seek(initial_size)
            appended = handle.read().decode("utf-8", errors="replace")
        if _EXPECTED_SPAN in appended and _EXPECTED_SERVICE in appended:
            break
        time.sleep(0.05)

    assert _EXPECTED_SPAN in appended
    assert _EXPECTED_SERVICE in appended
