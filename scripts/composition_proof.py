"""Prove the Gateway and the Policy Model Router actually compose, against a running Router.

The authority chain `Governance -> Policy Model Router -> Gateway -> provider` is asserted on each
side separately and, until this script, had never been executed end to end. Both repositories keep
a hand-written mirror of the Verifiable AI Governance runtime-authorization contract, because the
canonical signing bytes must stay byte-identical and neither side may import the other. If those
mirrors drift by one field, signature verification fails in production and nothing in either CI
notices. Running this is what notices.

Four scenarios, in order:

1. a forwarded envelope is accepted and a model group comes back;
2. the same request without an envelope is refused - the behavior that made the pair unusable
   before the Gateway learned to forward, kept here so the regression is visible rather than
   remembered;
3. an envelope signed by a key the Gateway trusts and the Router does not is refused, so
   scenario 1 is not passing on shape alone;
4. replaying the envelope from scenario 1 is refused, because the Router consumes the
   authorization ID exactly once - the cross-service replay boundary this pair now has.

Scenarios 2 to 4 all surface at the Gateway as one non-retryable authorization failure. That is
the design, not a gap: the Router does not tell a caller *why* it denied, and the reason stays in
its own logs and evidence. `docker compose -f compose.pdp-composition.yml logs policy-model-router`
shows them.

Usage:

    uv run python -m scripts.composition_fixture \\
        --write-key-set .composition/runtime-authorization-keys.json
    docker compose -f compose.pdp-composition.yml up -d --build
    uv run python -m scripts.composition_proof
    docker compose -f compose.pdp-composition.yml down -v
"""

import argparse
import asyncio
import http.client
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from governed_llm_gateway_contracts import (
    DataClassification,
    GatewayRequest,
    Message,
    MessageRole,
    RequestLimits,
    RiskLevel,
    WorkloadRequirements,
)
from governed_llm_gateway_core.adapters.governance_authorization import (
    StaticGovernanceKeyResolver,
    verify_governance_authorization_envelope,
)
from governed_llm_gateway_core.adapters.policy_router import PolicyRouterHttpAdapter
from governed_llm_gateway_core.adapters.policy_router_runtime import (
    EnvironmentPolicyRouterSecretResolver,
    build_policy_router_adapter,
)
from governed_llm_gateway_core.adapters.policy_router_runtime_json import (
    load_policy_router_runtime_document,
)
from governed_llm_gateway_core.application.policy import (
    PolicyDecisionError,
    PolicyDecisionErrorCode,
    PolicyProjectionDefaults,
    project_policy_request,
)
from governed_llm_gateway_core.domain.governance import ForwardableGovernanceAuthorization
from governed_llm_gateway_core.domain.trust import EffectivePolicyContext

from scripts import composition_fixture as fixture

_REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPOSITORY_ROOT / "config" / "composition-proof" / "policy_router.json"
_ROUTER_HOST = "127.0.0.1"
_ROUTER_PORT = 8001
_REQUEST_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


@dataclass(frozen=True, slots=True)
class Outcome:
    """One scenario's verdict, rendered as a single line of the report."""

    scenario: str
    expected: str
    observed: str
    passed: bool


def _gateway_request() -> GatewayRequest:
    return GatewayRequest(
        schema_version="1.0",
        request_id=_REQUEST_ID,
        workload=fixture.WORKLOAD,
        risk_level=RiskLevel.HIGH,
        data_classification=DataClassification.CONFIDENTIAL,
        requirements=WorkloadRequirements(
            tool_calling=False,
            structured_output=fixture.STRUCTURED_OUTPUT_REQUIRED,
            min_context_tokens=fixture.CONTEXT_TOKENS_ESTIMATED,
        ),
        limits=RequestLimits(
            max_latency_ms=fixture.MAX_LATENCY_MS,
            max_cost_usd=Decimal(fixture.MAX_COST_USD_MICROS) / Decimal(1_000_000),
        ),
        messages=(Message(role=MessageRole.USER, content="composition proof"),),
        agent_identity=fixture.CLIENT_ID,
    )


def _effective_context() -> EffectivePolicyContext:
    return EffectivePolicyContext(
        client_id=fixture.CLIENT_ID,
        environment=fixture.ENVIRONMENT,
        workload=fixture.WORKLOAD,
        risk_level=RiskLevel.HIGH,
        data_classification=DataClassification.CONFIDENTIAL,
    )


def _defaults() -> PolicyProjectionDefaults:
    return PolicyProjectionDefaults(
        max_latency_ms=fixture.MAX_LATENCY_MS,
        max_cost_usd=Decimal(fixture.MAX_COST_USD_MICROS) / Decimal(1_000_000),
    )


def _key_resolver() -> StaticGovernanceKeyResolver:
    """Trust both keys on the Gateway side.

    The Gateway must be able to verify and forward the rogue envelope for scenario 3 to say
    anything about the Router; if the Gateway refused it first, the scenario would prove only that
    the Gateway has a key allowlist, which its own unit tests already cover.
    """
    return StaticGovernanceKeyResolver(
        {
            fixture.TRUSTED_KEY_ID: fixture.public_key_bytes(fixture.trusted_private_key()),
            fixture.UNTRUSTED_KEY_ID: fixture.public_key_bytes(fixture.untrusted_private_key()),
        }
    )


def _forwardable(envelope: dict[str, object]) -> ForwardableGovernanceAuthorization:
    return verify_governance_authorization_envelope(json.dumps(envelope), keys=_key_resolver())


def _adapter() -> PolicyRouterHttpAdapter:
    os.environ.setdefault(fixture.API_KEY_ENV_REFERENCE, fixture.API_KEY)
    document = load_policy_router_runtime_document(_CONFIG_PATH)
    adapter = build_policy_router_adapter(document.runtime, EnvironmentPolicyRouterSecretResolver())
    if adapter is None:
        raise RuntimeError("composition-proof Policy Router configuration is disabled")
    return adapter


def _wait_for_router(*, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error = "no attempt was made"
    while time.monotonic() < deadline:
        connection = http.client.HTTPConnection(_ROUTER_HOST, _ROUTER_PORT, timeout=2.0)
        try:
            connection.request("GET", "/health")
            if connection.getresponse().status == 200:
                return
            last_error = "health endpoint did not answer 200"
        except OSError as error:
            last_error = str(error)
        finally:
            connection.close()
        time.sleep(1.0)
    raise RuntimeError(
        f"Policy Model Router at {_ROUTER_HOST}:{_ROUTER_PORT} never became ready: {last_error}"
    )


async def _authorize(
    adapter: PolicyRouterHttpAdapter,
    authorization: ForwardableGovernanceAuthorization | None,
) -> str:
    metadata = project_policy_request(
        _gateway_request(),
        _effective_context(),
        context_tokens_estimated=fixture.CONTEXT_TOKENS_ESTIMATED,
        max_output_tokens_estimated=fixture.MAX_OUTPUT_TOKENS_ESTIMATED,
        defaults=_defaults(),
        runtime_authorization=authorization,
    )
    decision = await adapter.authorize(metadata)
    return next(iter(decision.authorization.authorized_model_groups))


async def _accepted(
    adapter: PolicyRouterHttpAdapter,
    authorization: ForwardableGovernanceAuthorization,
    *,
    scenario: str,
) -> Outcome:
    expected = f"authorized model group {fixture.MODEL_GROUP!r}"
    try:
        group = await _authorize(adapter, authorization)
    except PolicyDecisionError as error:
        return Outcome(scenario, expected, f"denied with {error.code.value}", passed=False)
    return Outcome(
        scenario,
        expected,
        f"authorized model group {group!r}",
        passed=group == fixture.MODEL_GROUP,
    )


async def _denied(
    adapter: PolicyRouterHttpAdapter,
    authorization: ForwardableGovernanceAuthorization | None,
    *,
    scenario: str,
) -> Outcome:
    expected = "non-retryable authorization denial, no provider call"
    try:
        group = await _authorize(adapter, authorization)
    except PolicyDecisionError as error:
        passed = (
            error.code is PolicyDecisionErrorCode.AUTHORIZATION
            and error.status_code == 403
            and not error.retryable
        )
        observed = f"{error.code.value} (status {error.status_code}, retryable={error.retryable})"
        return Outcome(scenario, expected, observed, passed=passed)
    return Outcome(scenario, expected, f"authorized model group {group!r}", passed=False)


async def run() -> list[Outcome]:
    adapter = _adapter()
    now = datetime.now(UTC)

    accepted_envelope = fixture.mint_envelope(now=now, authorization_id=str(uuid4()))
    accepted = _forwardable(accepted_envelope)
    rogue = _forwardable(
        fixture.mint_envelope(
            now=now,
            authorization_id=str(uuid4()),
            key_id=fixture.UNTRUSTED_KEY_ID,
            private_key=fixture.untrusted_private_key(),
        )
    )

    return [
        await _accepted(adapter, accepted, scenario="forwarded envelope is accepted"),
        await _denied(adapter, None, scenario="no envelope is refused"),
        await _denied(adapter, rogue, scenario="envelope signed by an untrusted key is refused"),
        await _denied(adapter, accepted, scenario="replayed envelope is refused"),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the PDP/PEP composition proof.")
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=90.0,
        help="how long to wait for the Router container to answer /health",
    )
    arguments = parser.parse_args()

    _wait_for_router(timeout_seconds=arguments.wait_seconds)
    outcomes = asyncio.run(run())

    width = max(len(outcome.scenario) for outcome in outcomes)
    for outcome in outcomes:
        mark = "PASS" if outcome.passed else "FAIL"
        print(f"{mark}  {outcome.scenario.ljust(width)}  {outcome.observed}")
        if not outcome.passed:
            print(f"      expected: {outcome.expected}", file=sys.stderr)

    failures = sum(not outcome.passed for outcome in outcomes)
    print()
    print(f"{len(outcomes) - failures}/{len(outcomes)} scenarios passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
