"""Shared fail-closed translation utilities for provider-compatible northbound protocols."""

from collections.abc import Sequence
from dataclasses import dataclass
from re import fullmatch
from uuid import UUID

from fastapi import HTTPException
from governed_llm_gateway_contracts import (
    AudioBlock,
    ClientProtocol,
    DataClassification,
    DocumentBlock,
    GatewayRequest,
    ImageBlock,
    Message,
    RequestLimits,
    RiskLevel,
    RoutingProvenance,
    StructuredOutputSchema,
    ToolDefinition,
    ToolResultBlock,
    ToolUseBlock,
    WorkloadRequirements,
)

DEFAULT_AGENT_WORKLOAD = "agent.tool-use"
# Provider-compatible protocols do not carry the Gateway governance vocabulary. These are
# deliberately the least restrictive *caller claims*, not the effective security context.
# EffectiveContextResolver authenticates the credential, rejects workloads outside the client
# binding, and raises risk/classification to the binding floors before PDP authorization/ranking.
# A deployment that needs a stricter posture must configure stricter client-auth floors; protocol
# clients cannot lower those floors with request fields or provider-shaped metadata.
_PROTOCOL_CALLER_RISK_CLAIM = RiskLevel.LOW
_PROTOCOL_CALLER_DATA_CLAIM = DataClassification.PUBLIC
_WORKLOAD_PATTERN = r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
_CHARS_PER_TOKEN = 4
_NON_TEXT_BLOCK_TOKEN_ESTIMATE = 1024
_SAFE_PROVENANCE_HEADER_VALUE_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}"


@dataclass(frozen=True, slots=True)
class ProtocolGenerationPayload:
    """Protocol translation projected onto the sole governed coordinator input."""

    request: GatewayRequest
    context_tokens_estimated: int
    max_output_tokens: int
    provider_timeout_seconds: float = 30.0
    client_controls: tuple[str, ...] = ()

    @property
    def request_id(self) -> UUID:
        """Expose request identity to the shared coordinator."""
        return self.request.request_id

    @property
    def workload(self) -> str:
        """Expose the policy workload to observability and the shared coordinator."""
        return self.request.workload

    def to_gateway_request(self) -> GatewayRequest:
        """Return the already-validated immutable canonical request."""
        return self.request


def resolve_workload(value: str | None) -> str:
    """Resolve a deployment workload hint without treating a model alias as authority."""
    workload = value or DEFAULT_AGENT_WORKLOAD
    if fullmatch(_WORKLOAD_PATTERN, workload) is None:
        raise ValueError("gateway workload must be a dotted policy-defined identifier")
    return workload


def resolve_protocol_credential(
    *,
    authorization: str | None,
    x_api_key: str | None,
    gateway_api_key: str | None,
) -> str:
    """Accept standard SDK credential headers while rejecting ambiguity and malformed values."""
    candidates: list[str] = []
    if authorization is not None:
        scheme, separator, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or separator != " " or not token.strip():
            raise HTTPException(status_code=401, detail={"code": "invalid_gateway_credential"})
        candidates.append(token.strip())
    for candidate in (x_api_key, gateway_api_key):
        if candidate is not None:
            if not candidate.strip() or candidate.strip() != candidate:
                raise HTTPException(status_code=401, detail={"code": "invalid_gateway_credential"})
            candidates.append(candidate)
    if not candidates:
        raise HTTPException(status_code=401, detail={"code": "invalid_gateway_credential"})
    if len(set(candidates)) != 1:
        raise HTTPException(status_code=400, detail={"code": "ambiguous_gateway_credential"})
    return candidates[0]


def build_protocol_payload(
    *,
    request_id: UUID,
    workload: str,
    messages: tuple[Message, ...],
    max_output_tokens: int,
    client_protocol: ClientProtocol,
    tools: tuple[ToolDefinition, ...] = (),
    structured_output: StructuredOutputSchema | None = None,
    parallel_tool_calling: bool = False,
) -> ProtocolGenerationPayload:
    """Build an immutable request whose capability requirements are inferred, never weakened."""
    blocks = tuple(block for message in messages for block in message.canonical_blocks)
    tool_transcript = any(isinstance(block, ToolUseBlock | ToolResultBlock) for block in blocks)
    requirements = WorkloadRequirements(
        tool_calling=bool(tools) or tool_transcript,
        structured_output=structured_output is not None,
        vision=any(isinstance(block, ImageBlock) for block in blocks),
        streaming=True,
        audio=any(isinstance(block, AudioBlock) for block in blocks),
        document=any(isinstance(block, DocumentBlock) for block in blocks),
        parallel_tool_calling=parallel_tool_calling,
    )
    request = GatewayRequest(
        schema_version="1.0",
        request_id=request_id,
        workload=workload,
        risk_level=_PROTOCOL_CALLER_RISK_CLAIM,
        data_classification=_PROTOCOL_CALLER_DATA_CLAIM,
        requirements=requirements,
        limits=RequestLimits(),
        messages=messages,
        tools=tools,
        structured_output=structured_output,
        client_protocol=client_protocol,
    )
    return ProtocolGenerationPayload(
        request=request,
        context_tokens_estimated=estimate_context_tokens(messages),
        max_output_tokens=max_output_tokens,
    )


def estimate_context_tokens(messages: Sequence[Message]) -> int:
    """Return a conservative routing estimate; it is a ceiling input, never authorization."""
    text_characters = sum(len(message.text_content) for message in messages)
    non_text_blocks = sum(
        not hasattr(block, "text") for message in messages for block in message.canonical_blocks
    )
    return max(1, text_characters // _CHARS_PER_TOKEN) + (
        non_text_blocks * _NON_TEXT_BLOCK_TOKEN_ESTIMATE
    )


def safe_http_error_code(exc: HTTPException) -> str:
    """Extract only a stable gateway code from a preflight error."""
    if isinstance(exc.detail, dict):
        code = exc.detail.get("code")
        if isinstance(code, str):
            return code
    return "gateway_request_failed"


def safe_provenance_headers(routing: RoutingProvenance) -> dict[str, str]:
    """Expose bounded identifiers useful for audit correlation, never prompts or credentials."""
    candidates = {
        "x-gateway-routing-decision-id": routing.routing_decision_id,
        "x-gateway-policy-id": routing.policy.policy_id,
        "x-gateway-policy-version": routing.policy.policy_version,
        "x-gateway-model-group": routing.authorized_model_group,
        "x-gateway-registry-digest": routing.model_registry_digest,
    }
    return {
        name: value
        for name, value in candidates.items()
        if fullmatch(_SAFE_PROVENANCE_HEADER_VALUE_PATTERN, value) is not None
    }
