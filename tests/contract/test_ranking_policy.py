from decimal import Decimal

import pytest
from governed_llm_gateway_core.adapters.ranking_policy_yaml import load_ranking_policy_text
from governed_llm_gateway_core.domain.ranking import (
    DuplicateRankingKeyError,
    RankingPolicyError,
)

VALID = """
schema_version: "1.0"
policy_version: "ranking-v1"
score_snapshot_id: "static-v1"
source_date: "2026-08-31"
workloads:
  agent.orchestration:
    weights:
      quality: "0.40"
      reliability: "0.20"
      latency: "0.15"
      cost: "0.15"
      availability: "0.10"
    deployments:
      candidate-a:
        quality: "0.90"
        reliability: "0.80"
        latency: "0.70"
        cost: "0.60"
        availability: "0.95"
        expected_latency_ms: 1200
"""


def test_ranking_policy_digest_is_deterministic_for_semantically_equal_yaml() -> None:
    first = load_ranking_policy_text(VALID)
    second = load_ranking_policy_text(VALID.replace('"0.40"', '"0.400"'))

    assert first.digest == second.digest
    workload = first.for_workload("agent.orchestration")
    assert workload.weights.quality == Decimal("0.40")


def test_duplicate_yaml_key_is_rejected() -> None:
    duplicate = VALID.replace(
        '      quality: "0.40"\n',
        '      quality: "0.40"\n      quality: "0.50"\n',
        1,
    )

    with pytest.raises(DuplicateRankingKeyError):
        load_ranking_policy_text(duplicate)


def test_unknown_field_is_rejected() -> None:
    unknown = VALID.replace(
        'score_snapshot_id: "static-v1"\n',
        'score_snapshot_id: "static-v1"\nunknown: true\n',
    )

    with pytest.raises(RankingPolicyError, match="unknown ranking policy fields"):
        load_ranking_policy_text(unknown)


def test_weights_must_sum_exactly_to_one() -> None:
    invalid = VALID.replace('      availability: "0.10"', '      availability: "0.11"')

    with pytest.raises(RankingPolicyError, match="sum exactly to 1"):
        load_ranking_policy_text(invalid)


def test_unknown_workload_fails_closed() -> None:
    policy = load_ranking_policy_text(VALID)

    with pytest.raises(RankingPolicyError, match="no workload entry"):
        policy.for_workload("rag.answer")
