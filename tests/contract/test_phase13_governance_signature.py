import base64
import hashlib
import json
from copy import deepcopy

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from governed_llm_gateway_core.adapters.governance_authorization import (
    GovernanceAuthorizationVerificationError,
    StaticGovernanceKeyResolver,
    verify_governance_authorization_text,
)

_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
_PUBLIC_KEY = _PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
)
_KEY_ID = "governance-key-1"


def _claims() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "authorization_id": "11111111-1111-4111-8111-111111111111",
        "issuer": "verifiable-ai-governance",
        "audience": ["governed-llm-gateway"],
        "issued_at": "2026-09-04T13:30:00Z",
        "not_before": "2026-09-04T13:30:00Z",
        "expires_at": "2026-09-04T13:35:00Z",
        "subject": {
            "initiative_id": "22222222-2222-4222-8222-222222222222",
            "ai_system_id": "33333333-3333-4333-8333-333333333333",
            "ai_system_version": 2,
            "agent_id": "44444444-4444-4444-8444-444444444444",
            "agent_version": 3,
            "agent_review_digest": "a" * 64,
        },
        "request": {
            "workflow_id": "workflow-1",
            "task_id": "task-1",
            "workload": "rag.answer",
            "context_tokens_estimated": 2048,
            "max_output_tokens_estimated": 512,
            "structured_output_required": False,
            "max_latency_ms": 5000,
            "max_cost_usd_micros": 250_000,
        },
        "scope": {
            "risk_tier": "high",
            "data_classification": "internal",
            "autonomy_level": "a1_recommendation",
            "models": [
                {
                    "model_id": "55555555-5555-4555-8555-555555555555",
                    "entity_version": 4,
                    "model_version": "2026-08-01",
                    "routing_group": "agentic-strong",
                    "review_digest": "b" * 64,
                    "allowed_data_classes": ["internal", "public"],
                },
                {
                    "model_id": "66666666-6666-4666-8666-666666666666",
                    "entity_version": 1,
                    "model_version": "2026-07-15",
                    "routing_group": "balanced",
                    "review_digest": "c" * 64,
                    "allowed_data_classes": ["public"],
                },
            ],
            "allowed_tools": [],
            "permissions": [],
            "max_runtime_seconds": 120,
            "human_approval_points": [],
            "kill_switch_enabled": True,
        },
        "scope_digest": "d" * 64,
        "policy": {
            "policy_id": "governance-policy",
            "policy_version": "2.0.0",
            "policy_digest": "e" * 64,
            "control_catalog_id": "enterprise-controls",
            "control_catalog_version": "2.0.0",
            "control_catalog_digest": "f" * 64,
        },
    }


def _protected(*, algorithm: str = "Ed25519", key_id: str = _KEY_ID) -> dict[str, object]:
    return {
        "typ": "application/vnd.verifiable-ai-governance.runtime-authorization+json",
        "alg": algorithm,
        "kid": key_id,
    }


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _signed_text(
    *,
    protected: dict[str, object] | None = None,
    claims: dict[str, object] | None = None,
    signing_key: Ed25519PrivateKey = _PRIVATE_KEY,
) -> str:
    protected_value = protected or _protected()
    claims_value = claims or _claims()
    signature = signing_key.sign(
        _canonical_bytes({"protected": protected_value, "claims": claims_value})
    )
    encoded = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return json.dumps(
        {
            "protected": protected_value,
            "claims": claims_value,
            "signature": encoded,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _resolver() -> StaticGovernanceKeyResolver:
    return StaticGovernanceKeyResolver({_KEY_ID: _PUBLIC_KEY})


def test_valid_vaig_v1_signature_projects_verified_authorization() -> None:
    text = _signed_text()
    authorization = verify_governance_authorization_text(text, keys=_resolver())

    expected_signing_bytes = _canonical_bytes(
        {"protected": _protected(), "claims": _claims()}
    )
    assert str(authorization.authorization_id) == "11111111-1111-4111-8111-111111111111"
    assert authorization.key_id == _KEY_ID
    assert authorization.request.workflow_id == "workflow-1"
    assert authorization.request.task_id == "task-1"
    assert authorization.authorized_model_groups == frozenset({"agentic-strong"})
    assert authorization.signing_digest == hashlib.sha256(expected_signing_bytes).hexdigest()


def test_unknown_kid_fails_closed_without_key_discovery() -> None:
    text = _signed_text(protected=_protected(key_id="unknown-key"))
    with pytest.raises(GovernanceAuthorizationVerificationError, match="unknown signing key"):
        verify_governance_authorization_text(text, keys=_resolver())


def test_algorithm_substitution_fails_before_signature_acceptance() -> None:
    text = _signed_text(protected=_protected(algorithm="EdDSA"))
    with pytest.raises(GovernanceAuthorizationVerificationError, match="signature algorithm"):
        verify_governance_authorization_text(text, keys=_resolver())


def test_tampered_claims_fail_signature_verification() -> None:
    original = json.loads(_signed_text())
    original["claims"]["request"]["workload"] = "agent.orchestration"
    tampered = json.dumps(original, separators=(",", ":"))

    with pytest.raises(GovernanceAuthorizationVerificationError, match="signature verification"):
        verify_governance_authorization_text(tampered, keys=_resolver())


def test_signature_from_untrusted_private_key_fails() -> None:
    other_key = Ed25519PrivateKey.from_private_bytes(bytes(range(33, 65)))
    text = _signed_text(signing_key=other_key)
    with pytest.raises(GovernanceAuthorizationVerificationError, match="signature verification"):
        verify_governance_authorization_text(text, keys=_resolver())


def test_duplicate_json_keys_fail_closed() -> None:
    valid = json.loads(_signed_text())
    signature = valid["signature"]
    duplicate = (
        '{"protected":{"typ":"application/vnd.verifiable-ai-governance.runtime-authorization+json",'
        '"alg":"Ed25519","kid":"governance-key-1","kid":"governance-key-1"},'
        f'"claims":{json.dumps(valid["claims"], separators=(",", ":"))},'
        f'"signature":"{signature}"}}'
    )
    with pytest.raises(GovernanceAuthorizationVerificationError, match="strict JSON"):
        verify_governance_authorization_text(duplicate, keys=_resolver())


def test_unknown_schema_field_fails_closed_even_when_signed() -> None:
    claims = deepcopy(_claims())
    claims["future_authority"] = "must-not-be-ignored"
    text = _signed_text(claims=claims)
    with pytest.raises(GovernanceAuthorizationVerificationError, match="fields do not match v1 schema"):
        verify_governance_authorization_text(text, keys=_resolver())


def test_excessive_signed_lifetime_fails_closed() -> None:
    claims = deepcopy(_claims())
    claims["expires_at"] = "2026-09-04T13:40:01Z"
    text = _signed_text(claims=claims)
    with pytest.raises(GovernanceAuthorizationVerificationError, match="lifetime exceeds"):
        verify_governance_authorization_text(text, keys=_resolver())


def test_non_utc_timestamp_fails_closed() -> None:
    claims = deepcopy(_claims())
    claims["issued_at"] = "2026-09-04T10:30:00-03:00"
    text = _signed_text(claims=claims)
    with pytest.raises(GovernanceAuthorizationVerificationError, match="UTC with Z"):
        verify_governance_authorization_text(text, keys=_resolver())


def test_scope_without_model_for_runtime_data_class_fails_closed() -> None:
    claims = deepcopy(_claims())
    scope = claims["scope"]
    assert isinstance(scope, dict)
    models = scope["models"]
    assert isinstance(models, list)
    for model in models:
        assert isinstance(model, dict)
        model["allowed_data_classes"] = ["public"]
    text = _signed_text(claims=claims)
    with pytest.raises(GovernanceAuthorizationVerificationError, match="runtime data classification"):
        verify_governance_authorization_text(text, keys=_resolver())


def test_key_resolver_rejects_invalid_key_material() -> None:
    with pytest.raises(ValueError, match="exactly 32 bytes"):
        StaticGovernanceKeyResolver({_KEY_ID: b"short"})
