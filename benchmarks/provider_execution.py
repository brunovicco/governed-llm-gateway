"""Credential-backed benchmark execution against reviewed Model Registry deployments.

Phase 10 quality evidence requires real provider calls, so this executor binds one
benchmark target to exactly one already-reviewed registry deployment and calls it
through the same provider adapters the Gateway itself uses. Evidence therefore
describes the deployment that will actually be ranked, not a look-alike.

The executor grants no authority. A deployment must already exist in the registry, be
enabled, and be reachable through a reviewed provider-runtime binding; the declared
target must match that deployment's provider, model and API family exactly, and a
mismatch fails before any credential is spent.

Response normalization is deliberately bounded and identical for every target: the
first fenced block is unwrapped and the result parsed as JSON. Text that does not parse
is handed to the deterministic scorer unchanged and scores zero, so a malformed answer
stays a quality failure rather than becoming a provider failure. The normalization
identifier belongs in each target's ``configuration`` string, which is covered by the
target-matrix digest and therefore by the snapshot ID.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from governed_llm_gateway_contracts import Message, MessageRole
from governed_llm_gateway_core.application.provider import (
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
)
from governed_llm_gateway_core.application.resilience import ProviderResolver
from governed_llm_gateway_core.domain.model_registry import (
    ModelDeployment,
    ModelRegistry,
    PricingMetadata,
)

from .contracts import BenchmarkCase, BenchmarkTarget, JsonValue, ProviderCall
from .runner import BenchmarkProviderFailure

RESPONSE_NORMALIZATION_ID = "fenced_json_v1"
DEFAULT_MAX_OUTPUT_TOKENS = 4096
DEFAULT_TIMEOUT_SECONDS = 120.0
_FENCE = "```"
_MICRO_USD_EXPONENT = Decimal("0.000001")

Clock = Callable[[], float]


class BenchmarkExecutionBindingError(ValueError):
    """Raised when a benchmark target cannot be bound to a reviewed deployment."""


@dataclass(frozen=True, slots=True)
class TargetDeploymentBinding:
    """Operator-reviewed mapping from one benchmark target to one registry deployment."""

    target_id: str
    deployment_id: str

    def __post_init__(self) -> None:
        """Require normalized identities on both sides of the binding."""
        for name in ("target_id", "deployment_id"):
            value = getattr(self, name)
            if not value or value.strip() != value:
                raise BenchmarkExecutionBindingError(f"{name} must be non-empty and normalized")


class RegistryDeploymentExecutor:
    """Execute benchmark cases against reviewed deployments through Gateway adapters."""

    def __init__(
        self,
        *,
        registry: ModelRegistry,
        resolver: ProviderResolver,
        bindings: tuple[TargetDeploymentBinding, ...],
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        clock: Clock = time.monotonic,
    ) -> None:
        """Bind reviewed registry/provider dependencies and validate the target mapping."""
        if timeout_seconds <= 0:
            raise BenchmarkExecutionBindingError("timeout_seconds must be positive")
        mapping: dict[str, str] = {}
        for binding in bindings:
            if binding.target_id in mapping:
                raise BenchmarkExecutionBindingError(
                    f"duplicate benchmark target binding: {binding.target_id}"
                )
            mapping[binding.target_id] = binding.deployment_id
        if not mapping:
            raise BenchmarkExecutionBindingError("at least one target binding is required")

        self._registry = registry
        self._resolver = resolver
        self._bindings = mapping
        self._timeout_seconds = timeout_seconds
        self._clock = clock

    def deployment_for(self, target: BenchmarkTarget) -> ModelDeployment:
        """Resolve and verify the reviewed deployment a declared target must execute on."""
        deployment_id = self._bindings.get(target.target_id)
        if deployment_id is None:
            raise BenchmarkExecutionBindingError(
                f"benchmark target {target.target_id!r} has no reviewed deployment binding"
            )
        try:
            deployment = self._registry.by_id(deployment_id)
        except KeyError as exc:
            raise BenchmarkExecutionBindingError(
                f"bound deployment {deployment_id!r} is absent from the model registry"
            ) from exc

        if not deployment.enabled:
            raise BenchmarkExecutionBindingError(
                f"bound deployment {deployment_id!r} is disabled in the model registry"
            )
        observed = (deployment.provider, deployment.model_id, deployment.api_family)
        declared = (target.provider, target.model, target.api_family)
        if target.api_family is not None and observed != declared:
            raise BenchmarkExecutionBindingError(
                f"benchmark target {target.target_id!r} declares {declared} but bound "
                f"deployment {deployment_id!r} is {observed}"
            )
        return deployment

    async def execute(self, case: BenchmarkCase, target: BenchmarkTarget) -> ProviderCall:
        """Call one reviewed deployment and return normalized evidence for one case."""
        deployment = self.deployment_for(target)
        provider = self._resolver.resolve(deployment)
        max_output_tokens = target.max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS
        request = ProviderRequest(
            model=deployment.model_id,
            messages=(Message(role=MessageRole.USER, content=case.prompt),),
            max_output_tokens=max_output_tokens,
            timeout_seconds=self._timeout_seconds,
        )

        started = self._clock()
        try:
            response = await provider.generate(request)
        except ProviderError as exc:
            raise BenchmarkProviderFailure(
                code=exc.code.value,
                status_code=exc.status_code,
                latency_ms=_elapsed_ms(started, self._clock()),
            ) from exc

        latency_ms = _elapsed_ms(started, self._clock())
        return ProviderCall(
            output=normalize_response_output(response),
            latency_ms=latency_ms,
            input_units=response.usage.input_tokens,
            output_units=response.usage.output_tokens,
            cost_usd=observed_cost_usd(deployment.pricing, response.usage),
            provider=deployment.provider,
            model=deployment.model_id,
            deployment=deployment.deployment_id,
            api_family=deployment.api_family,
            max_output_tokens=max_output_tokens,
        )


def normalize_response_output(response: ProviderResponse) -> JsonValue:
    """Unwrap one fenced block and parse JSON, returning raw text when it does not parse."""
    if response.structured_output is not None:
        return cast(JsonValue, response.structured_output)
    text = response.text
    if text is None:
        return None

    candidate = _strip_fence(text.strip())
    try:
        return cast(JsonValue, json.loads(candidate))
    except json.JSONDecodeError:
        return text


def observed_cost_usd(pricing: PricingMetadata | None, usage: ProviderUsage) -> Decimal | None:
    """Derive call cost from reviewed registry pricing and provider-reported usage."""
    if usage.total_cost_usd is not None:
        return usage.total_cost_usd
    if pricing is None:
        return None
    per_million = (
        Decimal(usage.input_tokens) * pricing.input_usd_per_million_tokens
        + Decimal(usage.output_tokens) * pricing.output_usd_per_million_tokens
    )
    return (per_million / Decimal(1_000_000)).quantize(_MICRO_USD_EXPONENT)


def registry_bindings(
    registry: ModelRegistry,
    *,
    model_group: str,
    target_id_prefix: str,
) -> tuple[TargetDeploymentBinding, ...]:
    """Bind every enabled deployment in one model group to a deterministic target ID."""
    bindings = [
        TargetDeploymentBinding(
            target_id=f"{target_id_prefix}{deployment.deployment_id}",
            deployment_id=deployment.deployment_id,
        )
        for deployment in registry.deployments
        if deployment.model_group == model_group and deployment.enabled
    ]
    if not bindings:
        raise BenchmarkExecutionBindingError(
            f"model group {model_group!r} has no enabled deployments to benchmark"
        )
    return tuple(sorted(bindings, key=lambda item: item.target_id))


def _strip_fence(text: str) -> str:
    if not text.startswith(_FENCE):
        return text
    without_open = text[len(_FENCE) :]
    newline = without_open.find("\n")
    if newline == -1:
        return text
    body = without_open[newline + 1 :]
    close = body.rfind(_FENCE)
    if close == -1:
        return text
    return body[:close].strip()


def _elapsed_ms(started: float, ended: float) -> int:
    return max(0, round((ended - started) * 1000))
