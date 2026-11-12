"""U-web-settings-50, unit level: the hash stored for a decoy login request can never be matched by a code."""

import pytest

from app.auth.code_hash import CODE_PATTERN, DECOY_INPUT, decoy_hash, hash_code, verify_code

KEY = b"k" * 32
REQUEST_ID = "r" * 32


def test_given_a_decoy_when_hashed_then_it_is_a_32_byte_digest() -> None:
    assert isinstance(decoy_hash(KEY, REQUEST_ID), bytes)
    assert len(decoy_hash(KEY, REQUEST_ID)) == 32


def test_given_the_decoy_input_when_matched_against_the_code_shape_then_no_code_can_be_it() -> None:
    assert CODE_PATTERN.fullmatch(DECOY_INPUT) is None


def test_given_a_decoy_hash_when_every_sampled_code_is_checked_then_none_matches() -> None:
    stored = decoy_hash(KEY, REQUEST_ID)

    assert not any(verify_code(KEY, REQUEST_ID, f"{n:06d}", stored) for n in range(0, 1_000_000, 997))
    assert not verify_code(KEY, REQUEST_ID, "000000", stored)
    assert not verify_code(KEY, REQUEST_ID, "999999", stored)


def test_given_the_same_inputs_when_hashed_twice_then_the_decoy_hash_is_the_keyed_hash_of_the_marker() -> None:
    assert decoy_hash(KEY, REQUEST_ID) == hash_code(KEY, REQUEST_ID, DECOY_INPUT)
    assert decoy_hash(KEY, REQUEST_ID) == decoy_hash(KEY, REQUEST_ID)


@pytest.mark.parametrize(("key", "request_id"), [(b"x" * 32, REQUEST_ID), (KEY, "s" * 32)])
def test_given_another_key_or_request_when_hashed_then_the_decoy_hash_differs(key: bytes, request_id: str) -> None:
    assert decoy_hash(key, request_id) != decoy_hash(KEY, REQUEST_ID)
