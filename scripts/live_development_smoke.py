"""Opt-in metadata-only smoke harness for the governed live-development profile."""

import argparse
import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from governed_llm_gateway_client import GatewayClient
from governed_llm_gateway_client.errors import GatewayClientError, GatewayConfigurationError
from governed_llm_gateway_contracts import (
    DataClassification,
    ExecutionStatus,
    GatewayResponse,
    Message,
    MessageRole,
    RiskLevel,
)

_PROFILE_GATEWAY_URL = "http://127.0.0.1:8000"
_PROFILE_MODEL_GROUP = "balanced"
_PROFILE_EXECUTIONS: Mapping[str, tuple[str, str]] = {
    "google-gemini-3-8-flash-dev": ("google", "gemini-3.8-flash"),
    "openai-gpt-5-6-luna-dev": ("openai", "gpt-5.6-luna"),
    "anthropic-claude-sonnet-5-dev": ("anthropic", "claude-sonnet-5"),
    "nvidia-nemotron-3-super-dev": ("nvidia", "nvidia/nemotron-3-super-120b-a12b"),
    "groq-gpt-oss-120b-dev": ("groq", "openai/gpt-oss-120b"),
    "openrouter-llama-3-3-70b-dev": ("openrouter", "meta-llama/llama-3.3-70b-instruct"),
}
_SMOKE_PROMPT = "Answer in one sentence: what does deterministic model routing mean?"


class LiveDevelopmentSmokeError(RuntimeError):
    """Raised when live smoke evidence violates the reviewed profile contract."""


@dataclass(frozen=True, slots=True)
class LiveDevelopmentSmokeSummary:
    """Metadata-only summary of one successful governed live execution."""

    request_id: str
    authorized_model_group: str
    provider: str
    model: str
    deployment: str
    api_family: str | None
    latency_ms: int
    attempt_number: int
    fallback_index: int
    input_tokens: int
    output_tokens: int

    def as_dict(self) -> dict[str, object]:
        """Return bounded JSON-safe metadata without prompt or completion content."""
        return {
            "api_family": self.api_family,
            "attempt_number": self.attempt_number,
            "authorized_model_group": self.authorized_model_group,
            "deployment": self.deployment,
            "fallback_index": self.fallback_index,
            "input_tokens": self.input_tokens,
            "latency_ms": self.latency_ms,
            "model": self.model,
            "output_tokens": self.output_tokens,
            "provider": self.provider,
            "request_id": self.request_id,
            "status": ExecutionStatus.SUCCEEDED.value,
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one explicit live request through the reviewed PC-33 development profile."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="explicitly permit the live network request; omitted means no network execution",
    )
    return parser


def _validate_response(response: GatewayResponse) -> LiveDevelopmentSmokeSummary:
    if response.status is not ExecutionStatus.SUCCEEDED:
        raise LiveDevelopmentSmokeError("gateway response did not complete successfully")
    if not response.content:
        raise LiveDevelopmentSmokeError("gateway response completed without model content")

    routing = response.routing
    execution = response.execution
    if execution is None or execution.status is not ExecutionStatus.SUCCEEDED:
        raise LiveDevelopmentSmokeError(
            "gateway response lacks successful terminal execution evidence"
        )
    if routing.authorized_model_group != _PROFILE_MODEL_GROUP:
        raise LiveDevelopmentSmokeError("unexpected authorized model group in terminal provenance")

    expected_execution = _PROFILE_EXECUTIONS.get(execution.deployment)
    if expected_execution is None:
        raise LiveDevelopmentSmokeError(
            "terminal execution used a deployment outside the reviewed profile"
        )
    if (execution.provider, execution.model) != expected_execution:
        raise LiveDevelopmentSmokeError(
            "terminal execution identity contradicts the reviewed profile"
        )
    if (routing.provider, routing.model, routing.deployment) != (
        execution.provider,
        execution.model,
        execution.deployment,
    ):
        raise LiveDevelopmentSmokeError("routing and execution terminal identities disagree")

    usage = execution.usage
    if usage is None:
        raise LiveDevelopmentSmokeError("successful terminal execution is missing normalized usage")

    return LiveDevelopmentSmokeSummary(
        request_id=str(response.request_id),
        authorized_model_group=routing.authorized_model_group,
        provider=execution.provider,
        model=execution.model,
        deployment=execution.deployment,
        api_family=execution.api_family,
        latency_ms=execution.latency_ms,
        attempt_number=execution.attempt_number,
        fallback_index=execution.fallback_index,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )


async def _run_live() -> LiveDevelopmentSmokeSummary:
    async with GatewayClient.from_env() as gateway:
        if gateway.base_url != _PROFILE_GATEWAY_URL:
            raise LiveDevelopmentSmokeError(
                "live-development smoke requires the reviewed Gateway URL http://127.0.0.1:8000"
            )
        response = await gateway.generate(
            workload="rag.answer",
            messages=(Message(role=MessageRole.USER, content=_SMOKE_PROMPT),),
            risk_level=RiskLevel.LOW,
            data_classification=DataClassification.PUBLIC,
            context_tokens_estimated=128,
            max_output_tokens=128,
            provider_timeout_seconds=30.0,
        )
    return _validate_response(response)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the live smoke only after explicit opt-in and emit metadata-only evidence."""
    args = _parser().parse_args(argv)
    if not args.live:
        print("live smoke disabled: pass --live to permit network execution", file=sys.stderr)
        return 2

    try:
        summary = asyncio.run(_run_live())
    except GatewayConfigurationError as exc:
        print(f"live smoke configuration failed: {exc}", file=sys.stderr)
        return 2
    except LiveDevelopmentSmokeError as exc:
        print(f"live smoke validation failed: {exc}", file=sys.stderr)
        return 1
    except GatewayClientError:
        print("live smoke gateway request failed", file=sys.stderr)
        return 1

    print(json.dumps(summary.as_dict(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
