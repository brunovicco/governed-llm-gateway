from decimal import Decimal

import pytest

from benchmarks import BenchmarkCase, BenchmarkWorkload, build_default_scorers
from benchmarks.contracts import JsonValue
from benchmarks.scoring import require_scorer


def _case(scorer: str, expected: JsonValue) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=f"scoring.{scorer}",
        workload=BenchmarkWorkload.STRUCTURED_EXTRACTION,
        scorer=scorer,
        prompt="public synthetic scorer test",
        expected=expected,
    )


def test_exact_json_scores_match_and_mismatch() -> None:
    scorer = require_scorer(build_default_scorers(), "exact_json")
    case = _case("exact_json", {"value": 1})

    assert scorer(case, {"value": 1}) == Decimal("1")
    assert scorer(case, {"value": 2}) == Decimal("0")


def test_contains_all_scores_partial_non_text_and_empty_requirements() -> None:
    scorer = require_scorer(build_default_scorers(), "contains_all")
    case = _case("contains_all", ["Alpha", "Beta", "Gamma"])

    assert scorer(case, "alpha and GAMMA") == Decimal(2) / Decimal(3)
    assert scorer(case, {"text": "alpha beta gamma"}) == Decimal("0")
    assert scorer(_case("contains_all", []), "anything") == Decimal("1")


def test_contains_all_rejects_malformed_expected_values() -> None:
    scorer = require_scorer(build_default_scorers(), "contains_all")

    with pytest.raises(ValueError, match="list of required strings"):
        scorer(_case("contains_all", "alpha"), "alpha")
    with pytest.raises(ValueError, match="list of required strings"):
        scorer(_case("contains_all", ["alpha", 2]), "alpha")


def test_mapping_fields_scores_partial_non_mapping_and_empty_mapping() -> None:
    scorer = require_scorer(build_default_scorers(), "mapping_fields")
    case = _case("mapping_fields", {"a": 1, "b": 2})

    assert scorer(case, {"a": 1, "b": 0}) == Decimal("0.5")
    assert scorer(case, "not-an-object") == Decimal("0")
    assert scorer(_case("mapping_fields", {}), {}) == Decimal("1")


def test_mapping_fields_rejects_non_mapping_expected_value() -> None:
    scorer = require_scorer(build_default_scorers(), "mapping_fields")

    with pytest.raises(ValueError, match="expects an object"):
        scorer(_case("mapping_fields", ["a"]), {"a": 1})


def test_ordered_sequence_scores_positionally_and_handles_non_list_output() -> None:
    scorer = require_scorer(build_default_scorers(), "ordered_sequence")
    case = _case("ordered_sequence", ["first", "second", "third"])

    assert scorer(case, ["first", "wrong", "third", "extra"]) == Decimal(2) / Decimal(3)
    assert scorer(case, "first second third") == Decimal("0")
    assert scorer(_case("ordered_sequence", []), []) == Decimal("1")


def test_ordered_sequence_rejects_non_list_expected_value() -> None:
    scorer = require_scorer(build_default_scorers(), "ordered_sequence")

    with pytest.raises(ValueError, match="expects a list"):
        scorer(_case("ordered_sequence", "first"), ["first"])


def test_require_scorer_rejects_unknown_identifier() -> None:
    with pytest.raises(ValueError, match="unknown deterministic scorer"):
        require_scorer(build_default_scorers(), "unknown")
