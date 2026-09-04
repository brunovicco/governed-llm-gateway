"""Phase 14 terminal execution provenance expansion regressions."""

from decimal import Decimal

import pytest
from governed_llm_gateway_contracts import ExecutionStatus, ProviderExecution, Usage


def test_usage_preserves_optional_provider_returned_detail() -> None:
    usage = Usage(
        input_tokens=10,
        output_tokens=4,
        total_tokens=14,
        cache_read_input_tokens=3,
        cache_write_input_tokens=2,
        total_cost_usd=Decimal("0.0012"),
    )
    assert usage.total_tokens == 14
    assert usage.cache_read_input_tokens == 3
    assert usage.cache_write_input_tokens == 2
    assert usage.total_cost_usd == Decimal("0.0012")


def test_usage_does_not_fabricate_optional_provider_detail() -> None:
    usage = Usage(input_tokens=10, output_tokens=4)
    assert usage.total_tokens is None
    assert usage.cache_read_input_tokens is None
    assert usage.cache_write_input_tokens is None
    assert usage.total_cost_usd is None


def test_usage_rejects_contradictory_provider_total() -> None:
    with pytest.raises(ValueError, match="total_tokens"):
        Usage(input_tokens=10, output_tokens=4, total_tokens=15)


def test_execution_preserves_request_finish_attempt_and_fallback_provenance() -> None:
    execution = ProviderExecution(
        provider="anthropic",
        model="claude",
        deployment="claude-primary",
        status=ExecutionStatus.SUCCEEDED,
        latency_ms=42,
        provider_request_id="req_provider_123",
        finish_reason="end_turn",
        attempt_number=2,
        fallback_index=1,
    )
    assert execution.provider_request_id == "req_provider_123"
    assert execution.finish_reason == "end_turn"
    assert execution.attempt_number == 2
    assert execution.fallback_index == 1


def test_execution_rejects_invalid_attempt_provenance() -> None:
    with pytest.raises(ValueError, match="attempt_number"):
        ProviderExecution(
            provider="anthropic",
            model="claude",
            deployment="d",
            status=ExecutionStatus.SUCCEEDED,
            latency_ms=1,
            attempt_number=0,
        )
