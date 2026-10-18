import pytest

from scripts.pdp_real_https_exercise import (
    _fresh_authorization,
    validate_bounds,
)


@pytest.mark.parametrize("requests", [True, 1, 17, 1.5])
def test_exercise_rejects_invalid_request_bounds(requests: object) -> None:
    with pytest.raises(ValueError, match="requests"):
        validate_bounds(requests, 1)  # type: ignore[arg-type]


@pytest.mark.parametrize("rounds", [True, 0, 4, 1.5])
def test_exercise_rejects_invalid_round_bounds(rounds: object) -> None:
    with pytest.raises(ValueError, match="rounds"):
        validate_bounds(2, rounds)  # type: ignore[arg-type]


def test_each_real_router_call_gets_a_fresh_single_use_envelope() -> None:
    authorization_ids = {_fresh_authorization().authorization.authorization_id for _ in range(4)}

    assert len(authorization_ids) == 4
