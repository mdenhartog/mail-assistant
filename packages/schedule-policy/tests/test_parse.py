from datetime import time

import pytest

from schedule_policy.parse import MAX_TEXT_LENGTH, parse_time


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("7", time(7, 0)),
        ("7:00", time(7, 0)),
        ("07:00", time(7, 0)),
        ("0700", time(7, 0)),
        ("19.30", time(19, 30)),
        ("7am", time(7, 0)),
        ("7:30pm", time(19, 30)),
        ("24:00", time(0, 0)),
        ("00:00", time(0, 0)),
        ("0", time(0, 0)),
        ("23:59", time(23, 59)),
        ("12am", time(0, 0)),
        ("12pm", time(12, 0)),
        ("12:30am", time(0, 30)),
        ("12:30pm", time(12, 30)),
        ("11:59pm", time(23, 59)),
        ("1am", time(1, 0)),
        ("1pm", time(13, 0)),
        ("7 AM", time(7, 0)),
        ("7:30 PM", time(19, 30)),
        ("  7:00  ", time(7, 0)),
        ("2400", time(0, 0)),
        ("0930", time(9, 30)),
        ("9.05", time(9, 5)),
    ],
)
def test_given_a_typed_time_when_parsed_then_it_is_the_right_clock_time(text, expected):
    assert parse_time(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "abc",
        "25:00",
        "07:00:30",
        "０７:００",
        "",
        "   ",
        "7" * 65,
        "07:00\x00",
        "07:00\n",
        "\x077:00",
        "7:00 \U0001f550",
        "\U0001f55b",
        "٠٧:٠٠",
        "../etc",
        "'; DROP TABLE x;--",
        "24:30",
        "24:01",
        "7:60",
        "13pm",
        "0am",
        "0pm",
        "13am",
        "7:00 am pm",
        "700",
        "7:5",
        "7:0",
        "7.",
        ":30",
        "-1",
        "+7",
        "7:30:",
        "07-00",
        "1e1",
        "7a",
        "7 a m",
        "190",
        "123456",
        "2500",
        "7\t:00",
    ],
)
def test_given_text_that_is_not_a_time_when_parsed_then_none(text):
    assert parse_time(text) is None


def test_given_text_of_exactly_the_maximum_length_when_parsed_then_it_is_read():
    text = "7:00".rjust(MAX_TEXT_LENGTH)

    assert len(text) == 64
    assert parse_time(text) == time(7, 0)


def test_given_text_one_character_over_the_maximum_when_parsed_then_none():
    text = "7:00".rjust(MAX_TEXT_LENGTH + 1)

    assert len(text) == 65
    assert parse_time(text) is None


def test_given_a_parsed_time_when_inspected_then_it_has_no_zone_and_no_seconds():
    parsed = parse_time("7:30pm")

    assert parsed is not None
    assert parsed.tzinfo is None
    assert (parsed.second, parsed.microsecond) == (0, 0)
