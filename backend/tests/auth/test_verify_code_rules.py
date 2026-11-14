"""U-web-settings-18, unit level: the shape rules of the verify-code endpoint."""

import json

import pytest

from app.auth.verify_code_rules import code_well_formed, login_id_well_formed, refusal_body
from app.errors import problem_response


@pytest.mark.parametrize("value", ["000000", "123456", "999999"])
def test_given_six_ascii_digits_when_checked_then_well_formed(value: str) -> None:
    assert code_well_formed(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "",
        "12345",
        "1234567",
        "abcdef",
        "12345a",
        " 12345",
        "123456\n",
        "\n123456",
        "12 456",
        "١٢٣٤٥٦",  # Arabic-Indic digits are digits for ``\d`` but not for the code
        "\uff11\uff12\uff13\uff14\uff15\uff16",  # full-width digits
        123456,
        None,
        {"code": "123456"},
        ["123456"],
    ],
)
def test_given_anything_else_when_checked_then_not_well_formed(value: object) -> None:
    assert code_well_formed(value) is False


@pytest.mark.parametrize("value", ["a" * 32, "A" * 32, "0" * 32, "-" * 32, "_" * 32, "aB3-_" + "x" * 27])
def test_given_32_url_safe_characters_when_checked_then_a_login_id(value: str) -> None:
    assert login_id_well_formed(value) is True


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "a" * 31,
        "a" * 33,
        "a" * 31 + "=",
        "a" * 31 + "\x00",
        "a" * 31 + "\n",
        "a" * 31 + " ",
        "é" * 32,
        "a" * 31 + "%",
    ],
)
def test_given_anything_else_when_checked_then_not_a_login_id(value: str | None) -> None:
    assert login_id_well_formed(value) is False


def test_given_no_attempt_count_when_the_body_is_built_then_it_is_the_generic_problem_only() -> None:
    generic = json.loads(bytes(problem_response(400).body))

    assert refusal_body(None) == generic
    assert set(generic) == {"type", "title", "status"}


@pytest.mark.parametrize("left", [0, 1, 4, 5])
def test_given_an_attempt_count_when_the_body_is_built_then_it_adds_attempts_left_and_nothing_else(left: int) -> None:
    generic = json.loads(bytes(problem_response(400).body))

    assert refusal_body(left) == {**generic, "attemptsLeft": left}
