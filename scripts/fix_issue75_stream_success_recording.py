from pathlib import Path

path = Path("packages/gateway-core/src/governed_llm_gateway_core/application/streaming.py")
text = path.read_text()
old = '''                                    latency_ms = _latency_ms(started_at, self._clock())
                                    record_operational_attempt_best_effort(
                                        self._operational_recorder,
                                        utc_clock=self._utc_clock,
                                        request=request,
                                        deployment_id=deployment_id,
                                        attempt_number=attempt_number,
                                        fallback_index=len(fallback_sequence) - 1,
                                        latency_ms=latency_ms,
                                    )
                                    attempt_terminal_recorded = True
                                    self._health.record_success(
'''
new = '''                                    latency_ms = _latency_ms(started_at, self._clock())
                                    self._health.record_success(
'''
if text.count(old) != 1:
    raise SystemExit(f"expected one early success-recording block, found {text.count(old)}")
text = text.replace(old, new, 1)
old = '''                                    if (
                                        provider_response_id is not None
                                        and event.response_id is not None
                                        and provider_response_id != event.response_id
                                    ):
                                        raise _invalid_stream_event(
                                            deployment.provider,
                                            "provider response id changed during the stream",
                                        )
                                    execution = ProviderExecution(
'''
new = '''                                    if (
                                        provider_response_id is not None
                                        and event.response_id is not None
                                        and provider_response_id != event.response_id
                                    ):
                                        raise _invalid_stream_event(
                                            deployment.provider,
                                            "provider response id changed during the stream",
                                        )
                                    record_operational_attempt_best_effort(
                                        self._operational_recorder,
                                        utc_clock=self._utc_clock,
                                        request=request,
                                        deployment_id=deployment_id,
                                        attempt_number=attempt_number,
                                        fallback_index=len(fallback_sequence) - 1,
                                        latency_ms=latency_ms,
                                    )
                                    attempt_terminal_recorded = True
                                    execution = ProviderExecution(
'''
if text.count(old) != 1:
    raise SystemExit(f"expected one terminal validation block, found {text.count(old)}")
path.write_text(text.replace(old, new, 1))
