from governed_llm_gateway_core.application.telemetry import (
    GatewaySpanEventName,
    GatewaySpanName,
)


def test_gateway_span_vocabulary_preserves_phase9_runtime_names() -> None:
    assert tuple(member.value for member in GatewaySpanName) == (
        "llm.gateway.request",
        "policy.route",
        "provider.inference",
        "llm.gateway.stream",
    )


def test_gateway_span_event_vocabulary_preserves_resilience_names() -> None:
    assert tuple(member.value for member in GatewaySpanEventName) == (
        "llm.gateway.retry",
        "llm.gateway.fallback",
    )


def test_gateway_telemetry_vocabulary_has_no_duplicate_values() -> None:
    span_names = tuple(member.value for member in GatewaySpanName)
    event_names = tuple(member.value for member in GatewaySpanEventName)

    assert len(span_names) == len(set(span_names))
    assert len(event_names) == len(set(event_names))
    assert set(span_names).isdisjoint(event_names)
