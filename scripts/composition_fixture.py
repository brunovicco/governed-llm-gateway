"""Test-only stand-in for the Verifiable AI Governance issuer.

Governance is the only system allowed to sign a runtime authorization, and it does not exist as a
running service yet. The composition proof still needs an envelope to forward, so this module mints
one. It is deliberately not a Governance implementation: the signing key is derived from a sentence
printed below in plain text, nothing in `governed_llm_gateway_core` imports it, and its output is
only ever pointed at a throwaway Policy Model Router container.

Two details here are load-bearing and easy to get wrong. The Policy Model Router recomputes the
signing bytes from its *parsed pydantic model*, not from the bytes it received, so every value must
already be in the form pydantic would emit: UTC timestamps as `...Z` with no microseconds, UUIDs
lowercase and hyphenated, and every set-like collection sorted and deduplicated. And the Router
binds `requested_at` to `issued_at`, so an envelope is only usable for a few minutes and cannot be
committed as a static fixture - it is minted at run time, every time.
"""

import argparse
import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_TRUSTED_SEED_PHRASE = b"governed-llm-gateway composition proof: trusted issuer, not a real key"
_UNTRUSTED_SEED_PHRASE = b"governed-llm-gateway composition proof: untrusted issuer, not a real key"

TRUSTED_KEY_ID = "composition-proof-key-1"
UNTRUSTED_KEY_ID = "composition-proof-rogue-key"

ISSUER = "verifiable-ai-governance:composition-proof"
GATEWAY_AUDIENCE = "governed-llm-gateway"
ROUTER_AUDIENCE = "policy-model-router"

CLIENT_ID = "composition-proof-client"
ENVIRONMENT = "development"
API_KEY_ENV_REFERENCE = "POLICY_ROUTER_COMPOSITION_API_KEY"
API_KEY = "composition-proof-api-key"

AGENT_ID = "44444444-4444-4444-8444-444444444444"
INITIATIVE_ID = "22222222-2222-4222-8222-222222222222"
AI_SYSTEM_ID = "33333333-3333-4333-8333-333333333333"
MODEL_ID = "55555555-5555-4555-8555-555555555555"

POLICY_ID = "composition-proof-governance-policy"
POLICY_VERSION = "1.0.0"
POLICY_DIGEST = "1" * 64
CONTROL_CATALOG_ID = "composition-proof-controls"
CONTROL_CATALOG_VERSION = "1.0.0"
CONTROL_CATALOG_DIGEST = "2" * 64

# The Gateway requires a dotted workload identifier and the Router accepts any policy identifier,
# so a composed deployment has to use the dotted form on both sides. The Router's own example
# policy uses underscored names, which is why this proof mounts a policy of its own.
WORKLOAD = "credit.cashflow-analysis"
MODEL_GROUP = "reasoning-medium"

WORKFLOW_ID = "composition-proof-workflow"
TASK_ID = "composition-proof-task"
CONTEXT_TOKENS_ESTIMATED = 2048
MAX_OUTPUT_TOKENS_ESTIMATED = 512
STRUCTURED_OUTPUT_REQUIRED = False
MAX_LATENCY_MS = 20_000
MAX_COST_USD_MICROS = 50_000
RISK_TIER = "high"
DATA_CLASSIFICATION = "confidential"

AUTHORIZATION_LIFETIME_SECONDS = 300


def _private_key(seed_phrase: bytes) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(seed_phrase).digest())


def trusted_private_key() -> Ed25519PrivateKey:
    return _private_key(_TRUSTED_SEED_PHRASE)


def untrusted_private_key() -> Ed25519PrivateKey:
    return _private_key(_UNTRUSTED_SEED_PHRASE)


def public_key_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _utc_text(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def trusted_key_set(*, now: datetime) -> dict[str, Any]:
    """Build the public-only key set the Router loads at startup.

    Only the trusted key is listed. The rogue key is deliberately absent: that absence is what the
    untrusted-key scenario proves.
    """
    return {
        "schema_version": "1.0",
        "generation": 1,
        "keys": [
            {
                "kid": TRUSTED_KEY_ID,
                "status": "active",
                "not_before": _utc_text(now - timedelta(days=1)),
                "verify_until": _utc_text(now + timedelta(days=365)),
                "jwk": {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "x": _b64url(public_key_bytes(trusted_private_key())),
                },
            }
        ],
    }


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def mint_envelope(
    *,
    now: datetime,
    authorization_id: str,
    key_id: str = TRUSTED_KEY_ID,
    private_key: Ed25519PrivateKey | None = None,
) -> dict[str, Any]:
    """Mint one signed envelope bound to this proof's request."""
    issued_at = now.replace(microsecond=0)
    signing_key = private_key or trusted_private_key()
    protected = {
        "typ": "application/vnd.verifiable-ai-governance.runtime-authorization+json",
        "alg": "Ed25519",
        "kid": key_id,
    }
    claims = {
        "schema_version": "1.0",
        "authorization_id": authorization_id,
        "issuer": ISSUER,
        # Both consumers check that their own name is present. A composed deployment therefore
        # needs an envelope addressed to both, which is the kind of fact that only shows up once
        # the two services actually run together.
        "audience": sorted([GATEWAY_AUDIENCE, ROUTER_AUDIENCE]),
        "issued_at": _utc_text(issued_at),
        "not_before": _utc_text(issued_at),
        "expires_at": _utc_text(issued_at + timedelta(seconds=AUTHORIZATION_LIFETIME_SECONDS)),
        "subject": {
            "initiative_id": INITIATIVE_ID,
            "ai_system_id": AI_SYSTEM_ID,
            "ai_system_version": 1,
            "agent_id": AGENT_ID,
            "agent_version": 1,
            "agent_review_digest": "3" * 64,
        },
        "request": {
            "workflow_id": WORKFLOW_ID,
            "task_id": TASK_ID,
            "workload": WORKLOAD,
            "context_tokens_estimated": CONTEXT_TOKENS_ESTIMATED,
            "max_output_tokens_estimated": MAX_OUTPUT_TOKENS_ESTIMATED,
            "structured_output_required": STRUCTURED_OUTPUT_REQUIRED,
            "max_latency_ms": MAX_LATENCY_MS,
            "max_cost_usd_micros": MAX_COST_USD_MICROS,
        },
        "scope": {
            "risk_tier": RISK_TIER,
            "data_classification": DATA_CLASSIFICATION,
            "autonomy_level": "a1_recommendation",
            "models": [
                {
                    "model_id": MODEL_ID,
                    "entity_version": 1,
                    "model_version": "2026-09-01",
                    "routing_group": MODEL_GROUP,
                    "review_digest": "4" * 64,
                    "allowed_data_classes": ["confidential", "internal", "public"],
                }
            ],
            "allowed_tools": [],
            "permissions": [],
            "max_runtime_seconds": 120,
            "human_approval_points": [],
            "kill_switch_enabled": True,
        },
        "scope_digest": "5" * 64,
        "policy": {
            "policy_id": POLICY_ID,
            "policy_version": POLICY_VERSION,
            "policy_digest": POLICY_DIGEST,
            "control_catalog_id": CONTROL_CATALOG_ID,
            "control_catalog_version": CONTROL_CATALOG_VERSION,
            "control_catalog_digest": CONTROL_CATALOG_DIGEST,
        },
    }
    signature = signing_key.sign(_canonical_bytes({"protected": protected, "claims": claims}))
    return {
        "protected": protected,
        "claims": claims,
        "signature": _b64url(signature),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-key-set",
        type=Path,
        required=True,
        help="path to write the Router's trusted key set to",
    )
    arguments = parser.parse_args()
    destination = Path(arguments.write_key_set)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(trusted_key_set(now=datetime.now(UTC)), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote trusted key set to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
