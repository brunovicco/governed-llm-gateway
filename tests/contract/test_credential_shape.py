import pytest
from governed_llm_gateway_api.credential_shape import (
    MAX_GATEWAY_API_KEY_LENGTH,
    is_valid_gateway_api_key,
)


@pytest.mark.parametrize(
    "value",
    [
        "a",
        "x" * MAX_GATEWAY_API_KEY_LENGTH,
        "token-with-normalized-ascii",
    ],
)
def test_gateway_credential_shape_accepts_normalized_ascii_within_bound(value: str) -> None:
    assert is_valid_gateway_api_key(value)


@pytest.mark.parametrize(
    "value",
    [
        None,
        b"bytes-are-not-the-runtime-contract",
        "",
        " leading-space",
        "trailing-space ",
        "não-ascii",
        "x" * (MAX_GATEWAY_API_KEY_LENGTH + 1),
    ],
)
def test_gateway_credential_shape_rejects_malformed_values(value: object) -> None:
    assert not is_valid_gateway_api_key(value)
