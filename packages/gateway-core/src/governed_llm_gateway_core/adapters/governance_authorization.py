"""Strict Verifiable AI Governance v1 runtime-authorization verification adapter."""

import base64
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from governed_llm_gateway_contracts import DataClassification, RiskLevel

from governed_llm_gateway_core.domain.governance import (
    GovernancePolicyProvenance,
    GovernanceRequestBinding,
    VerifiedGovernanceAuthorization,
)

_MEDIA_TYPE = "application/vnd.verifiable-ai-governance.runtime-authorization+json"
_SCHEMA_VERSION = "1.0"
_ALGORITHM = "Ed25519"
_MAX_AUTHORIZATION_LIFETIME_SECONDS = 600
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_ROUTING_GROUP_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,99}$")
_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")
_SIGNATURE_RE = re.compile(r"^[A-Za-z0-9_-]{86}$")

_ROOT_FIELDS = frozenset({"protected", "claims", "signature"})
_PROTECTED_FIELDS = frozenset({"typ", "alg", "kid"})
_CLAIMS_FIELDS = frozenset(
    {
        "schema_version",
        "authorization_id",
        "issuer",
        "audience",
        "issued_at",
        "not_before",
        "expires_at",
        "subject",
        "request",
        "scope",
        "scope_digest",
        "policy",
    }
)
_SUBJECT_FIELDS = frozenset(
    {
        "initiative_id",
        "ai_system_id",
        "ai_system_version",
        "agent_id",
        "agent_version",
        "agent_review_digest",
    }
)
_REQUEST_FIELDS = frozenset(
    {
        "workflow_id",
        "task_id",
        "workload",
        "context_tokens_estimated",
        "max_output_tokens_estimated",
        "structured_output_required",
        "max_latency_ms",
        "max_cost_usd_micros",
    }
)
_SCOPE_FIELDS = frozenset(
    {
        "risk_tier",
        "data_classification",
        "autonomy_level",
        "models",
        "allowed_tools",
        "permissions",
        "max_runtime_seconds",
        "human_approval_points",
        "kill_switch_enabled",
    }
)
_MODEL_FIELDS = frozenset(
    {
        "model_id",
        "entity_version",
        "model_version",
        "routing_group",
        "review_digest",
        "allowed_data_classes",
    }
)
_POLICY_FIELDS = frozenset(
    {
        "policy_id",
        "policy_version",
        "policy_digest",
        "control_catalog_id",
        "control_catalog_version",
        "control_catalog_digest",
    }
)


class GovernanceAuthorizationVerificationError(ValueError):
    """Sanitized failure while validating a signed governance authorization."""


class _DuplicateJsonKeyError(ValueError):
    pass


class StaticGovernanceKeyResolver:
    """Explicit in-memory Ed25519 public-key allowlist keyed by trusted ``kid`` values."""

    def __init__(self, keys: Mapping[str, bytes]) -> None:
        """Validate and freeze raw 32-byte Ed25519 public keys."""
        normalized: dict[str, Ed25519PublicKey] = {}
        for key_id, public_bytes in keys.items():
            _require_identifier(key_id, "trusted key id")
            if not isinstance(public_bytes, bytes) or len(public_bytes) != 32:
                raise ValueError("trusted Ed25519 public keys must be exactly 32 bytes")
            normalized[key_id] = Ed25519PublicKey.from_public_bytes(public_bytes)
        if not normalized:
            raise ValueError("at least one trusted governance public key is required")
        self._keys = normalized

    def resolve(self, key_id: str) -> Ed25519PublicKey:
        """Return one explicitly configured key or fail closed without network discovery."""
        try:
            return self._keys[key_id]
        except KeyError as exc:
            raise GovernanceAuthorizationVerificationError(
                "governance authorization references an unknown signing key"
            ) from exc


def verify_governance_authorization_text(
    text: str,
    *,
    keys: StaticGovernanceKeyResolver,
) -> VerifiedGovernanceAuthorization:
    """Parse, verify, and project one VAIG v1 JSON authorization envelope."""
    try:
        payload = cast(
            object,
            json.loads(text, object_pairs_hook=_unique_json_object),
        )
    except (json.JSONDecodeError, _DuplicateJsonKeyError) as exc:
        raise GovernanceAuthorizationVerificationError(
            "governance authorization is not valid strict JSON"
        ) from exc
    root = _require_object(payload, "authorization envelope")
    _require_exact_fields(root, _ROOT_FIELDS, "authorization envelope")

    protected = _require_object(root["protected"], "protected header")
    claims = _require_object(root["claims"], "authorization claims")
    _require_exact_fields(protected, _PROTECTED_FIELDS, "protected header")
    _require_exact_fields(claims, _CLAIMS_FIELDS, "authorization claims")

    if _require_string(protected["typ"], "protected.typ") != _MEDIA_TYPE:
        raise GovernanceAuthorizationVerificationError("unsupported governance authorization type")
    if _require_string(protected["alg"], "protected.alg") != _ALGORITHM:
        raise GovernanceAuthorizationVerificationError(
            "unsupported governance authorization signature algorithm"
        )
    key_id = _require_identifier(protected["kid"], "protected.kid")
    signature = _decode_signature(root["signature"])
    signing_bytes = _canonical_json_bytes({"protected": protected, "claims": claims})
    try:
        keys.resolve(key_id).verify(signature, signing_bytes)
    except InvalidSignature as exc:
        raise GovernanceAuthorizationVerificationError(
            "governance authorization signature verification failed"
        ) from exc

    return _project_verified_authorization(
        protected=protected,
        claims=claims,
        signing_bytes=signing_bytes,
    )


def _project_verified_authorization(
    *,
    protected: dict[str, object],
    claims: dict[str, object],
    signing_bytes: bytes,
) -> VerifiedGovernanceAuthorization:
    if _require_string(claims["schema_version"], "claims.schema_version") != _SCHEMA_VERSION:
        raise GovernanceAuthorizationVerificationError(
            "unsupported governance authorization schema version"
        )

    issued_at = _require_utc_datetime(claims["issued_at"], "claims.issued_at")
    not_before = _require_utc_datetime(claims["not_before"], "claims.not_before")
    expires_at = _require_utc_datetime(claims["expires_at"], "claims.expires_at")
    if not_before < issued_at:
        raise GovernanceAuthorizationVerificationError("governance not_before precedes issued_at")
    if expires_at <= not_before:
        raise GovernanceAuthorizationVerificationError(
            "governance expires_at must follow not_before"
        )
    if (expires_at - issued_at).total_seconds() > _MAX_AUTHORIZATION_LIFETIME_SECONDS:
        raise GovernanceAuthorizationVerificationError(
            "governance authorization lifetime exceeds v1 maximum"
        )

    subject = _require_object(claims["subject"], "authorization subject")
    request = _require_object(claims["request"], "request binding")
    scope = _require_object(claims["scope"], "authorization scope")
    policy = _require_object(claims["policy"], "governance policy provenance")
    _require_exact_fields(subject, _SUBJECT_FIELDS, "authorization subject")
    _require_exact_fields(request, _REQUEST_FIELDS, "request binding")
    _require_exact_fields(scope, _SCOPE_FIELDS, "authorization scope")
    _require_exact_fields(policy, _POLICY_FIELDS, "governance policy provenance")

    _require_positive_int(subject["ai_system_version"], "subject.ai_system_version")
    _require_positive_int(subject["agent_version"], "subject.agent_version")
    agent_review_digest = _require_digest(subject["agent_review_digest"], "subject.agent_review_digest")

    audience = _require_identifier_tuple(claims["audience"], "claims.audience")
    if not audience:
        raise GovernanceAuthorizationVerificationError("claims.audience must not be empty")

    runtime_request = GovernanceRequestBinding(
        workflow_id=_require_identifier(request["workflow_id"], "request.workflow_id"),
        task_id=_require_identifier(request["task_id"], "request.task_id"),
        workload=_require_identifier(request["workload"], "request.workload"),
        context_tokens_estimated=_require_bounded_int(
            request["context_tokens_estimated"],
            "request.context_tokens_estimated",
            minimum=0,
            maximum=10_000_000,
        ),
        max_output_tokens_estimated=_require_bounded_int(
            request["max_output_tokens_estimated"],
            "request.max_output_tokens_estimated",
            minimum=0,
            maximum=1_000_000,
        ),
        structured_output_required=_require_bool(
            request["structured_output_required"], "request.structured_output_required"
        ),
        max_latency_ms=_require_bounded_int(
            request["max_latency_ms"], "request.max_latency_ms", minimum=1, maximum=3_600_000
        ),
        max_cost_usd_micros=_require_bounded_int(
            request["max_cost_usd_micros"],
            "request.max_cost_usd_micros",
            minimum=0,
            maximum=1_000_000_000_000,
        ),
    )

    risk_level = _require_enum(scope["risk_tier"], RiskLevel, "scope.risk_tier")
    data_classification = _require_enum(
        scope["data_classification"], DataClassification, "scope.data_classification"
    )
    _require_identifier(scope["autonomy_level"], "scope.autonomy_level")
    _require_bounded_int(
        scope["max_runtime_seconds"],
        "scope.max_runtime_seconds",
        minimum=1,
        maximum=86_400,
    )
    if _require_bool(scope["kill_switch_enabled"], "scope.kill_switch_enabled") is not True:
        raise GovernanceAuthorizationVerificationError("scope.kill_switch_enabled must be true")
    _require_identifier_tuple(scope["allowed_tools"], "scope.allowed_tools")
    _require_identifier_tuple(scope["permissions"], "scope.permissions")
    _require_short_text_tuple(scope["human_approval_points"], "scope.human_approval_points")
    authorized_groups = _parse_models(scope["models"], data_classification=data_classification)

    return VerifiedGovernanceAuthorization(
        authorization_id=_require_uuid(claims["authorization_id"], "claims.authorization_id"),
        issuer=_require_identifier(claims["issuer"], "claims.issuer"),
        audience=audience,
        key_id=_require_identifier(protected["kid"], "protected.kid"),
        signing_digest=hashlib.sha256(signing_bytes).hexdigest(),
        not_before=not_before,
        expires_at=expires_at,
        initiative_id=_require_uuid(subject["initiative_id"], "subject.initiative_id"),
        ai_system_id=_require_uuid(subject["ai_system_id"], "subject.ai_system_id"),
        agent_id=_require_uuid(subject["agent_id"], "subject.agent_id"),
        agent_review_digest=agent_review_digest,
        request=runtime_request,
        risk_level=risk_level,
        data_classification=data_classification,
        scope_digest=_require_digest(claims["scope_digest"], "claims.scope_digest"),
        authorized_model_groups=frozenset(authorized_groups),
        policy=GovernancePolicyProvenance(
            policy_id=_require_identifier(policy["policy_id"], "policy.policy_id"),
            policy_version=_require_identifier(policy["policy_version"], "policy.policy_version"),
            policy_digest=_require_digest(policy["policy_digest"], "policy.policy_digest"),
            control_catalog_id=_require_identifier(
                policy["control_catalog_id"], "policy.control_catalog_id"
            ),
            control_catalog_version=_require_identifier(
                policy["control_catalog_version"], "policy.control_catalog_version"
            ),
            control_catalog_digest=_require_digest(
                policy["control_catalog_digest"], "policy.control_catalog_digest"
            ),
        ),
    )


def _parse_models(value: object, *, data_classification: DataClassification) -> set[str]:
    models = _require_list(value, "scope.models")
    if not models:
        raise GovernanceAuthorizationVerificationError("scope.models must not be empty")
    model_ids: set[UUID] = set()
    authorized_groups: set[str] = set()
    data_class_allowed = False
    for index, item in enumerate(models):
        model = _require_object(item, f"scope.models[{index}]")
        _require_exact_fields(model, _MODEL_FIELDS, f"scope.models[{index}]")
        model_id = _require_uuid(model["model_id"], f"scope.models[{index}].model_id")
        if model_id in model_ids:
            raise GovernanceAuthorizationVerificationError(
                "scope.models contains duplicate model identifiers"
            )
        model_ids.add(model_id)
        _require_positive_int(model["entity_version"], f"scope.models[{index}].entity_version")
        _require_identifier(model["model_version"], f"scope.models[{index}].model_version")
        routing_group = _require_routing_group(
            model["routing_group"], f"scope.models[{index}].routing_group"
        )
        _require_digest(model["review_digest"], f"scope.models[{index}].review_digest")
        classes = _require_enum_tuple(
            model["allowed_data_classes"],
            DataClassification,
            f"scope.models[{index}].allowed_data_classes",
        )
        if not classes:
            raise GovernanceAuthorizationVerificationError(
                "authorized model allowed_data_classes must not be empty"
            )
        if data_classification in classes:
            data_class_allowed = True
            authorized_groups.add(routing_group)
    if not data_class_allowed:
        raise GovernanceAuthorizationVerificationError(
            "no authorized governance model permits the runtime data classification"
        )
    return authorized_groups


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(key)
        result[key] = value
    return result


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise GovernanceAuthorizationVerificationError(
            "governance authorization is not canonically serializable"
        ) from exc


def _require_exact_fields(
    value: Mapping[str, object], allowed: frozenset[str], context: str
) -> None:
    actual = set(value)
    if actual != allowed:
        missing = sorted(allowed - actual)
        unknown = sorted(actual - allowed)
        raise GovernanceAuthorizationVerificationError(
            f"{context} fields do not match v1 schema; missing={missing!r}, unknown={unknown!r}"
        )


def _require_object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise GovernanceAuthorizationVerificationError(f"{context} must be a JSON object")
    return cast(dict[str, object], value)


def _require_list(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise GovernanceAuthorizationVerificationError(f"{context} must be a JSON array")
    return cast(list[object], value)


def _require_string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise GovernanceAuthorizationVerificationError(
            f"{context} must be a normalized non-empty string"
        )
    return value


def _require_identifier(value: object, context: str) -> str:
    text = _require_string(value, context)
    if _IDENTIFIER_RE.fullmatch(text) is None:
        raise GovernanceAuthorizationVerificationError(f"{context} is not a valid identifier")
    return text


def _require_routing_group(value: object, context: str) -> str:
    text = _require_string(value, context)
    if _ROUTING_GROUP_RE.fullmatch(text) is None:
        raise GovernanceAuthorizationVerificationError(f"{context} is not a valid routing group")
    return text


def _require_digest(value: object, context: str) -> str:
    text = _require_string(value, context)
    if _DIGEST_RE.fullmatch(text) is None:
        raise GovernanceAuthorizationVerificationError(f"{context} must be a SHA-256 hex digest")
    return text


def _require_uuid(value: object, context: str) -> UUID:
    text = _require_string(value, context)
    try:
        parsed = UUID(text)
    except ValueError as exc:
        raise GovernanceAuthorizationVerificationError(f"{context} must be a UUID") from exc
    if parsed.int == 0:
        raise GovernanceAuthorizationVerificationError(f"{context} must not be the nil UUID")
    return parsed


def _require_utc_datetime(value: object, context: str) -> datetime:
    text = _require_string(value, context)
    if not text.endswith("Z"):
        raise GovernanceAuthorizationVerificationError(f"{context} must be expressed in UTC with Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise GovernanceAuthorizationVerificationError(f"{context} is not a valid datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise GovernanceAuthorizationVerificationError(f"{context} must be UTC")
    return parsed.astimezone(UTC)


def _require_bool(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise GovernanceAuthorizationVerificationError(f"{context} must be boolean")
    return value


def _require_positive_int(value: object, context: str) -> int:
    return _require_bounded_int(value, context, minimum=1, maximum=2_147_483_647)


def _require_bounded_int(value: object, context: str, *, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum or value > maximum:
        raise GovernanceAuthorizationVerificationError(
            f"{context} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _require_identifier_tuple(value: object, context: str) -> tuple[str, ...]:
    return tuple(_require_identifier(item, context) for item in _require_list(value, context))


def _require_short_text_tuple(value: object, context: str) -> tuple[str, ...]:
    result: list[str] = []
    for item in _require_list(value, context):
        text = _require_string(item, context)
        if len(text) > 300:
            raise GovernanceAuthorizationVerificationError(f"{context} items exceed 300 characters")
        result.append(text)
    return tuple(result)


def _require_enum_tuple(value: object, enum_type: type[DataClassification], context: str) -> tuple[DataClassification, ...]:
    return tuple(_require_enum(item, enum_type, context) for item in _require_list(value, context))


def _require_enum(value: object, enum_type: type[RiskLevel] | type[DataClassification], context: str) -> RiskLevel | DataClassification:
    text = _require_string(value, context)
    try:
        return enum_type(text)
    except ValueError as exc:
        raise GovernanceAuthorizationVerificationError(f"{context} contains an unsupported value") from exc


def _decode_signature(value: object) -> bytes:
    text = _require_string(value, "signature")
    if _SIGNATURE_RE.fullmatch(text) is None:
        raise GovernanceAuthorizationVerificationError("signature is not valid unpadded base64url")
    try:
        decoded = base64.urlsafe_b64decode(text + "==")
    except (ValueError, UnicodeError) as exc:
        raise GovernanceAuthorizationVerificationError("signature is not valid base64url") from exc
    if len(decoded) != 64:
        raise GovernanceAuthorizationVerificationError("signature must decode to exactly 64 bytes")
    return decoded
