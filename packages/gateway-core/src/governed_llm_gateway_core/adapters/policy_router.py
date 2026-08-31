"""Fail-closed HTTP adapter for Policy Model Router API 1.0."""

import asyncio
import http.client
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, cast
from urllib.parse import urlsplit

from governed_llm_gateway_contracts import PolicyProvenance

from governed_llm_gateway_core.application.policy import (
    PolicyAuthorizationDecision,
    PolicyDecisionError,
    PolicyDecisionErrorCode,
    PolicyRequestMetadata,
)
from governed_llm_gateway_core.domain.authorization import PolicyAuthorization

_MAX_RESPONSE_BYTES = 512 * 1024
_POLICY_IDENTIFIER_RE = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$")
_POLICY_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SUCCESS_FIELDS = frozenset(
    {
        "schema_version",
        "routing_decision_id",
        "decided_at",
        "workflow_id",
        "task_id",
        "selected_model_group",
        "reason",
        "rejected_candidates",
        "policy_id",
        "policy_version",
        "policy_digest",
        "service_version",
        "environment",
    }
)
_REJECTION_FIELDS = frozenset(
    {
        "schema_version",
        "routing_decision_id",
        "decided_at",
        "workflow_id",
        "task_id",
        "workload",
        "rejected_model_group",
        "reason",
        "reason_code",
        "observed_value",
        "required_value",
        "policy_id",
        "policy_version",
        "policy_digest",
        "service_version",
        "environment",
    }
)


class PolicyTransportFailureKind(StrEnum):
    """Sanitized infrastructure failures before PDP-level normalization."""

    TIMEOUT = "timeout"
    NETWORK = "network"
    INVALID_RESPONSE = "invalid_response"


class PolicyTransportFailure(RuntimeError):
    """Transport failure that carries no raw body, URL credentials, or API key."""

    def __init__(self, kind: PolicyTransportFailureKind, message: str) -> None:
        """Create a sanitized transport failure."""
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True, slots=True)
class PolicyHttpResponse:
    """Bounded PDP response with only allowlisted operational headers."""

    status_code: int
    retry_after: str | None
    payload: Mapping[str, object] | None


class PolicyTransport(Protocol):
    """Injectable HTTP boundary used by deterministic adapter contract tests."""

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> PolicyHttpResponse:
        """POST one policy-only JSON object and return bounded parsed metadata."""
        ...


class StdlibPolicyTransport:
    """HTTPS-only stdlib transport that parses only 200/422 PDP bodies."""

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> PolicyHttpResponse:
        """Execute blocking stdlib HTTP outside the event-loop thread."""
        return await asyncio.to_thread(
            self._post_json_sync,
            url=url,
            headers=headers,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def _post_json_sync(
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> PolicyHttpResponse:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("policy router endpoint must be an absolute HTTPS URL")
        if parsed.username is not None or parsed.password is not None or parsed.fragment:
            raise ValueError("policy router endpoint must not contain userinfo or a fragment")
        if timeout_seconds <= 0:
            raise ValueError("policy router timeout_seconds must be positive")

        port = parsed.port or 443
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        connection = http.client.HTTPSConnection(
            parsed.hostname,
            port=port,
            timeout=timeout_seconds,
        )
        try:
            connection.request("POST", path, body=body, headers=dict(headers))
            response = connection.getresponse()
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
            retry_after = response.getheader("Retry-After")
        except TimeoutError as exc:
            raise PolicyTransportFailure(
                PolicyTransportFailureKind.TIMEOUT,
                "policy router request timed out",
            ) from exc
        except (OSError, http.client.HTTPException) as exc:
            raise PolicyTransportFailure(
                PolicyTransportFailureKind.NETWORK,
                "policy router transport failed",
            ) from exc
        finally:
            connection.close()

        if len(raw) > _MAX_RESPONSE_BYTES:
            raise PolicyTransportFailure(
                PolicyTransportFailureKind.INVALID_RESPONSE,
                "policy router response exceeded the bounded response size",
            )

        payload_out: Mapping[str, object] | None = None
        if response.status in {200, 422}:
            try:
                decoded = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise PolicyTransportFailure(
                    PolicyTransportFailureKind.INVALID_RESPONSE,
                    "policy router returned invalid JSON",
                ) from exc
            if not isinstance(decoded, dict):
                raise PolicyTransportFailure(
                    PolicyTransportFailureKind.INVALID_RESPONSE,
                    "policy router response must be a JSON object",
                )
            payload_out = cast(dict[str, object], decoded)

        return PolicyHttpResponse(
            status_code=response.status,
            retry_after=retry_after,
            payload=payload_out,
        )


class PolicyRouterHttpAdapter:
    """PolicyDecisionPort implementation for Policy Model Router ``POST /route`` API 1.0."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_keys_by_client: Mapping[str, str],
        transport: PolicyTransport | None = None,
        now: Callable[[], datetime] | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        """Bind trusted identity credentials and an injectable transport/clock."""
        if not endpoint:
            raise ValueError("policy router endpoint must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("policy router timeout_seconds must be positive")
        if not api_keys_by_client:
            raise ValueError("api_keys_by_client must not be empty")
        if any(not key or not value for key, value in api_keys_by_client.items()):
            raise ValueError("api_keys_by_client must contain non-empty client/key pairs")
        self._endpoint = endpoint
        self._api_keys_by_client = dict(api_keys_by_client)
        self._transport = transport or StdlibPolicyTransport()
        self._now = now or (lambda: datetime.now(UTC))
        self._timeout_seconds = timeout_seconds

    async def authorize(self, request: PolicyRequestMetadata) -> PolicyAuthorizationDecision:
        """Submit prompt-free policy metadata and normalize one deterministic PDP decision."""
        api_key = self._api_keys_by_client.get(request.client_id)
        if api_key is None:
            raise PolicyDecisionError(
                code=PolicyDecisionErrorCode.AUTHENTICATION,
                message="no Policy Model Router credential is configured for the trusted client",
                retryable=False,
            )

        requested_at = self._now()
        if requested_at.tzinfo is None or requested_at.utcoffset() != UTC.utcoffset(requested_at):
            raise PolicyDecisionError(
                code=PolicyDecisionErrorCode.INVALID_REQUEST,
                message="Policy Model Router request clock must return UTC",
                retryable=False,
            )

        request_id = str(request.request_id)
        payload: dict[str, object] = {
            "schema_version": "1.0",
            "requested_at": requested_at.isoformat().replace("+00:00", "Z"),
            "workflow_id": request_id,
            "task_id": request_id,
            "agent_name": request.client_id,
            "workload": request.workload,
            "risk_level": request.risk_level.value,
            "data_classification": request.data_classification.value,
            "context_tokens_estimated": request.context_tokens_estimated,
            "max_output_tokens_estimated": request.max_output_tokens_estimated,
            "structured_output_required": request.structured_output_required,
            "max_latency_ms": request.max_latency_ms,
            "max_cost_usd": str(request.max_cost_usd),
        }
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "x-api-key": api_key,
        }

        try:
            response = await self._transport.post_json(
                url=self._endpoint,
                headers=headers,
                payload=payload,
                timeout_seconds=self._timeout_seconds,
            )
        except PolicyTransportFailure as exc:
            if exc.kind is PolicyTransportFailureKind.TIMEOUT:
                raise PolicyDecisionError(
                    code=PolicyDecisionErrorCode.TIMEOUT,
                    message="Policy Model Router request timed out",
                    retryable=True,
                ) from exc
            if exc.kind is PolicyTransportFailureKind.NETWORK:
                raise PolicyDecisionError(
                    code=PolicyDecisionErrorCode.TRANSPORT,
                    message="Policy Model Router transport failed",
                    retryable=True,
                ) from exc
            raise PolicyDecisionError(
                code=PolicyDecisionErrorCode.INVALID_RESPONSE,
                message="Policy Model Router returned an invalid response",
                retryable=False,
            ) from exc

        if response.status_code == 200:
            return _parse_success(response.payload, request)
        if response.status_code == 422:
            _raise_unprocessable(response.payload, request)
        if response.status_code == 401:
            raise _policy_error(PolicyDecisionErrorCode.AUTHENTICATION, response, retryable=False)
        if response.status_code == 403:
            raise _policy_error(PolicyDecisionErrorCode.AUTHORIZATION, response, retryable=False)
        if response.status_code == 429:
            raise _policy_error(PolicyDecisionErrorCode.RATE_LIMIT, response, retryable=True)
        if response.status_code == 500:
            raise _policy_error(PolicyDecisionErrorCode.MISCONFIGURED, response, retryable=False)
        if 500 <= response.status_code <= 599:
            raise _policy_error(PolicyDecisionErrorCode.UNAVAILABLE, response, retryable=True)
        raise _policy_error(PolicyDecisionErrorCode.INVALID_RESPONSE, response, retryable=False)


def _policy_error(
    code: PolicyDecisionErrorCode,
    response: PolicyHttpResponse,
    *,
    retryable: bool,
) -> PolicyDecisionError:
    return PolicyDecisionError(
        code=code,
        message=f"Policy Model Router request failed with status {response.status_code}",
        retryable=retryable,
        status_code=response.status_code,
    )


def _parse_success(
    payload: Mapping[str, object] | None,
    request: PolicyRequestMetadata,
) -> PolicyAuthorizationDecision:
    if payload is None:
        raise _invalid_response("Policy Model Router success response had no JSON object")
    _require_exact_fields(payload, _SUCCESS_FIELDS, "route decision")
    _require_schema_version(payload)
    request_id = str(request.request_id)
    if _require_string(payload["workflow_id"], "workflow_id") != request_id:
        raise _invalid_response("Policy Model Router workflow_id did not match the request")
    if _require_string(payload["task_id"], "task_id") != request_id:
        raise _invalid_response("Policy Model Router task_id did not match the request")
    environment = _require_string(payload["environment"], "environment")
    if environment != request.environment:
        raise _invalid_response("Policy Model Router environment did not match trusted context")
    rejected_candidates = payload["rejected_candidates"]
    if not isinstance(rejected_candidates, list):
        raise _invalid_response("Policy Model Router rejected_candidates must be an array")

    decision_id = _require_string(payload["routing_decision_id"], "routing_decision_id")
    selected_group = _require_policy_identifier(
        payload["selected_model_group"], "selected_model_group"
    )
    provenance = _provenance(payload, decision_id)
    return PolicyAuthorizationDecision(
        authorization=PolicyAuthorization(
            decision_id=decision_id,
            authorized_model_groups=frozenset({selected_group}),
        ),
        provenance=provenance,
        decided_at=_require_utc_datetime(payload["decided_at"], "decided_at"),
        reason=_require_string(payload["reason"], "reason"),
        service_version=_require_string(payload["service_version"], "service_version"),
        environment=environment,
    )


def _raise_unprocessable(
    payload: Mapping[str, object] | None,
    request: PolicyRequestMetadata,
) -> None:
    if payload is None:
        raise _invalid_response("Policy Model Router 422 response had no JSON object")
    error = payload.get("error")
    if not isinstance(error, dict):
        raise _invalid_response("Policy Model Router 422 response had no error object")
    error_code = _require_string(error.get("code"), "error.code")
    if error_code != "no_viable_model_group":
        raise PolicyDecisionError(
            code=PolicyDecisionErrorCode.INVALID_REQUEST,
            message="Policy Model Router rejected the projected request",
            retryable=False,
            status_code=422,
        )

    decision = payload.get("decision")
    if not isinstance(decision, dict):
        raise _invalid_response("Policy Model Router rejection had no decision provenance")
    typed = cast(dict[str, object], decision)
    _require_exact_fields(typed, _REJECTION_FIELDS, "route rejection")
    _require_schema_version(typed)
    request_id = str(request.request_id)
    if _require_string(typed["workflow_id"], "workflow_id") != request_id:
        raise _invalid_response("Policy Model Router rejection workflow_id did not match request")
    if _require_string(typed["task_id"], "task_id") != request_id:
        raise _invalid_response("Policy Model Router rejection task_id did not match request")
    if _require_string(typed["workload"], "workload") != request.workload:
        raise _invalid_response("Policy Model Router rejection workload did not match request")
    if _require_string(typed["environment"], "environment") != request.environment:
        raise _invalid_response(
            "Policy Model Router rejection environment did not match trusted context"
        )
    decision_id = _require_string(typed["routing_decision_id"], "routing_decision_id")
    raise PolicyDecisionError(
        code=PolicyDecisionErrorCode.REJECTED,
        message="Policy Model Router denied the requested workload",
        retryable=False,
        status_code=422,
        provenance=_provenance(typed, decision_id),
        reason_code=_require_string(typed["reason_code"], "reason_code"),
    )


def _provenance(payload: Mapping[str, object], decision_id: str) -> PolicyProvenance:
    digest = _require_string(payload["policy_digest"], "policy_digest")
    if not _POLICY_DIGEST_RE.fullmatch(digest):
        raise _invalid_response("Policy Model Router policy_digest was not a SHA-256 digest")
    return PolicyProvenance(
        decision_id=decision_id,
        policy_id=_require_string(payload["policy_id"], "policy_id"),
        policy_version=_require_string(payload["policy_version"], "policy_version"),
        policy_digest=digest,
    )


def _require_schema_version(payload: Mapping[str, object]) -> None:
    if payload["schema_version"] != "1.0":
        raise _invalid_response("unsupported Policy Model Router response schema_version")


def _require_exact_fields(
    payload: Mapping[str, object],
    expected: frozenset[str],
    label: str,
) -> None:
    fields = frozenset(payload)
    if fields != expected:
        raise _invalid_response(f"Policy Model Router {label} fields did not match API 1.0")


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise _invalid_response(f"Policy Model Router {label} must be a non-empty string")
    return value


def _require_policy_identifier(value: object, label: str) -> str:
    text = _require_string(value, label)
    if not _POLICY_IDENTIFIER_RE.fullmatch(text):
        raise _invalid_response(f"Policy Model Router {label} was not a valid policy identifier")
    return text


def _require_utc_datetime(value: object, label: str) -> datetime:
    text = _require_string(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid_response(f"Policy Model Router {label} was not an ISO datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise _invalid_response(f"Policy Model Router {label} must be expressed in UTC")
    return parsed


def _invalid_response(message: str) -> PolicyDecisionError:
    return PolicyDecisionError(
        code=PolicyDecisionErrorCode.INVALID_RESPONSE,
        message=message,
        retryable=False,
    )
