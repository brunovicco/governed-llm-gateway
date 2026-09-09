"""Strict JSON adapter for explicitly pinned approved ranking artifacts."""

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import cast

from governed_llm_gateway_core.domain.evidence_ranking import (
    EvidenceDrivenRankingPolicy,
    EvidenceRankingError,
    ScoreProvenanceMode,
)
from governed_llm_gateway_core.domain.ranking import RankingPolicyError, build_ranking_policy
from governed_llm_gateway_core.domain.ranking_override import ApprovedRankingArtifact

_ROOT_FIELDS = frozenset({"schema_version", "artifact_id", "approval", "policy"})
_APPROVAL_FIELDS = frozenset({"approval_version", "approval_date", "approved_by"})
_POLICY_REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "policy_version",
        "score_snapshot_id",
        "source_date",
        "workloads",
        "score_provenance_mode",
        "benchmark_snapshot_id",
        "promotion_evidence_id",
    }
)
_POLICY_OPTIONAL_FIELDS = frozenset({"manual_override_id"})


class ApprovedRankingArtifactDocumentError(ValueError):
    """Raised when an approved ranking artifact is malformed or not pinned exactly."""


class DuplicateApprovedRankingArtifactKeyError(ApprovedRankingArtifactDocumentError):
    """Raised when approved ranking artifact JSON repeats an object key."""


def load_approved_ranking_artifact(
    path: str | Path,
    *,
    expected_artifact_id: str,
) -> ApprovedRankingArtifact:
    """Load one approved evidence-driven policy and verify its exact pinned identity."""
    artifact_path = Path(path)
    return load_approved_ranking_artifact_text(
        artifact_path.read_text(encoding="utf-8"),
        expected_artifact_id=expected_artifact_id,
    )


def load_approved_ranking_artifact_text(
    text: str,
    *,
    expected_artifact_id: str,
) -> ApprovedRankingArtifact:
    """Strictly parse and verify one explicitly pinned approved ranking artifact."""
    _require_sha256(expected_artifact_id, "expected_artifact_id")
    try:
        payload = json.loads(text, object_pairs_hook=_unique_object)
    except ApprovedRankingArtifactDocumentError:
        raise
    except json.JSONDecodeError as exc:
        raise ApprovedRankingArtifactDocumentError(
            "approved ranking artifact is not valid JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ApprovedRankingArtifactDocumentError(
            "approved ranking artifact root must be a mapping"
        )

    root = cast(Mapping[str, object], payload)
    _require_fields(root, _ROOT_FIELDS, _ROOT_FIELDS, "approved ranking artifact")
    schema_version = _require_string(root["schema_version"], "schema_version")
    if schema_version != "1.0":
        raise ApprovedRankingArtifactDocumentError(
            "approved ranking artifact schema_version must be '1.0'"
        )
    declared_artifact_id = _require_string(root["artifact_id"], "artifact_id")
    _require_sha256(declared_artifact_id, "artifact_id")

    approval = _require_mapping(root["approval"], "approval")
    _require_fields(approval, _APPROVAL_FIELDS, _APPROVAL_FIELDS, "approval")
    artifact = ApprovedRankingArtifact(
        policy=_build_evidence_driven_policy(_require_mapping(root["policy"], "policy")),
        approval_version=_require_normalized_string(
            approval["approval_version"], "approval.approval_version"
        ),
        approval_date=_require_date(approval["approval_date"], "approval.approval_date"),
        approved_by=_require_normalized_string(approval["approved_by"], "approval.approved_by"),
    )

    if artifact.artifact_id != declared_artifact_id:
        raise ApprovedRankingArtifactDocumentError(
            "declared artifact_id does not match approved ranking artifact content"
        )
    if artifact.artifact_id != expected_artifact_id:
        raise ApprovedRankingArtifactDocumentError(
            "approved ranking artifact does not match expected_artifact_id"
        )
    return artifact


def dump_approved_ranking_artifact_text(artifact: ApprovedRankingArtifact) -> str:
    """Serialize one approved evidence-driven ranking artifact deterministically."""
    if not isinstance(artifact, ApprovedRankingArtifact):
        raise TypeError("artifact must use ApprovedRankingArtifact")
    if not isinstance(artifact.policy, EvidenceDrivenRankingPolicy):
        raise ApprovedRankingArtifactDocumentError(
            "approved runtime artifact requires EvidenceDrivenRankingPolicy"
        )
    payload = {
        "schema_version": "1.0",
        "artifact_id": artifact.artifact_id,
        "approval": {
            "approval_version": artifact.approval_version,
            "approval_date": artifact.approval_date.isoformat(),
            "approved_by": artifact.approved_by,
        },
        "policy": artifact.policy.canonical_payload(),
    }
    return (
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def _build_evidence_driven_policy(
    payload: Mapping[str, object],
) -> EvidenceDrivenRankingPolicy:
    allowed = _POLICY_REQUIRED_FIELDS | _POLICY_OPTIONAL_FIELDS
    _require_fields(payload, allowed, _POLICY_REQUIRED_FIELDS, "policy")
    schema_version = _require_string(payload["schema_version"], "policy.schema_version")
    if schema_version != "1.1":
        raise ApprovedRankingArtifactDocumentError(
            "approved runtime policy schema_version must be '1.1'"
        )

    base_payload: dict[object, object] = {
        "schema_version": "1.0",
        "policy_version": payload["policy_version"],
        "score_snapshot_id": payload["score_snapshot_id"],
        "source_date": payload["source_date"],
        "workloads": payload["workloads"],
    }
    try:
        base = build_ranking_policy(base_payload)
        mode_text = _require_string(
            payload["score_provenance_mode"], "policy.score_provenance_mode"
        )
        try:
            mode = ScoreProvenanceMode(mode_text)
        except ValueError as exc:
            raise ApprovedRankingArtifactDocumentError(
                "policy.score_provenance_mode is not supported"
            ) from exc
        return EvidenceDrivenRankingPolicy(
            schema_version="1.1",
            policy_version=base.policy_version,
            score_snapshot_id=base.score_snapshot_id,
            source_date=base.source_date,
            workloads=base.workloads,
            score_provenance_mode=mode,
            benchmark_snapshot_id=_require_string(
                payload["benchmark_snapshot_id"], "policy.benchmark_snapshot_id"
            ),
            promotion_evidence_id=_require_string(
                payload["promotion_evidence_id"], "policy.promotion_evidence_id"
            ),
            manual_override_id=(
                _require_string(payload["manual_override_id"], "policy.manual_override_id")
                if "manual_override_id" in payload
                else None
            ),
        )
    except ApprovedRankingArtifactDocumentError:
        raise
    except (RankingPolicyError, EvidenceRankingError) as exc:
        raise ApprovedRankingArtifactDocumentError(
            "approved ranking artifact policy is invalid"
        ) from exc


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise DuplicateApprovedRankingArtifactKeyError(
                f"duplicate approved ranking artifact key: {key!r}"
            )
        payload[key] = value
    return payload


def _require_fields(
    payload: Mapping[str, object],
    allowed: frozenset[str],
    required: frozenset[str],
    location: str,
) -> None:
    keys = set(payload)
    unknown = sorted(keys - allowed)
    if unknown:
        raise ApprovedRankingArtifactDocumentError(
            f"unknown {location} fields: {', '.join(unknown)}"
        )
    missing = sorted(required - keys)
    if missing:
        raise ApprovedRankingArtifactDocumentError(
            f"missing {location} fields: {', '.join(missing)}"
        )


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ApprovedRankingArtifactDocumentError(f"{field} must be a mapping")
    for key in value:
        if not isinstance(key, str):
            raise ApprovedRankingArtifactDocumentError(f"{field} field names must be strings")
    return cast(Mapping[str, object], value)


def _require_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ApprovedRankingArtifactDocumentError(f"{field} must be a string")
    return value


def _require_normalized_string(value: object, field: str) -> str:
    text = _require_string(value, field)
    if not text or text.strip() != text:
        raise ApprovedRankingArtifactDocumentError(f"{field} must be non-empty and normalized")
    return text


def _require_date(value: object, field: str) -> date:
    text = _require_string(value, field)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ApprovedRankingArtifactDocumentError(f"{field} must be an ISO date") from exc
    if parsed.isoformat() != text:
        raise ApprovedRankingArtifactDocumentError(f"{field} must use canonical ISO date format")
    return parsed


def _require_sha256(value: str, field: str) -> None:
    if not value.startswith("sha256:"):
        raise ApprovedRankingArtifactDocumentError(f"{field} must be a sha256: content identity")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64:
        raise ApprovedRankingArtifactDocumentError(
            f"{field} must contain a 64-character SHA-256 digest"
        )
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ApprovedRankingArtifactDocumentError(
            f"{field} must contain a hexadecimal SHA-256 digest"
        ) from exc
