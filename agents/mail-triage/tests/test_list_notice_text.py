"""U-mail-categories-07 criterion 4 (AC-29, MC-5): a list notice is escaped plain text within Telegram's limit."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime

from app.core import list_text
from app.core.alert_text import MAX_MESSAGE_CHARS
from app.core.list_text import ListCategory
from tests.fakes.seeds import BIDI_CONTROLS

AT = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
UNDO, LOCK = "catundo:AAAAAAAAAAAAAAAAAAAAAA", "catlock:BBBBBBBBBBBBBBBBBBBBBB"
BELL = chr(7)
NUL = chr(0)
ENTITY = re.compile(r"&(?!(?:amp|lt|gt);)")
TAG = re.compile(r"<[^>]*>")


def _notice(old: list[ListCategory], new: list[ListCategory], changes: int = 1) -> list_text.AlertMessage:
    return list_text.change_notice(tuple(old), tuple(new), changes=changes, at=AT, undo_data=UNDO, lock_data=LOCK)


def test_given_markup_and_control_characters_in_a_category_then_the_notice_is_escaped_plain_text() -> None:
    hostile = ListCategory(
        "1", '<b>Bills</b> & "more"', f'<a href="http://evil.test">click</a>{NUL}{BELL}\nsecond line'
    )
    bidi = ListCategory("2", f"Work{BIDI_CONTROLS[0]}gnp", f"x{BIDI_CONTROLS[1]}y")

    message = _notice([ListCategory("3", "Old", "")], [hostile, bidi])

    assert not TAG.search(message.text)  # no tag at all, so no hidden link and no fake button
    assert "&lt;b&gt;Bills&lt;/b&gt; &amp;" in message.text
    assert not ENTITY.search(message.text)
    forbidden = {"Cc", "Cf"}
    assert not [c for c in message.text if unicodedata.category(c) in forbidden and c != "\n"]


def test_given_the_biggest_possible_lists_then_the_notice_stays_within_the_limit_and_says_it_does_not_fit() -> None:
    big = [ListCategory(str(n), "&" * 40, "<" * 500) for n in range(50)]
    changed = [ListCategory(c.id, c.name, ">" * 500) for c in big]

    message = _notice(big, changed)

    assert len(message.text) <= MAX_MESSAGE_CHARS
    assert not ENTITY.search(message.text)
    assert not TAG.search(message.text)
    assert "do not fit in one message" in message.text  # said out loud, not hidden
    assert "and 3 more" not in message.text
    assert [button.label for button in message.buttons] == ["Undo", "Undo and lock web sign-in"]


def test_given_only_category_45_of_50_changed_then_it_is_shown_first_with_old_and_new_description() -> None:
    old = [ListCategory(str(n), f"Category {n}", f"About number {n}") for n in range(50)]
    new = [ListCategory(c.id, c.name, "Now about receipts" if c.id == "45" else c.description) for c in old]

    text = _notice(old, new).text

    assert "Category 45" in text
    assert "Before: About number 45" in text
    assert "Now: Now about receipts" in text
    assert text.index("Category 45") < text.index("Unchanged")
    assert "Unchanged (49)" in text
    assert "Category 3:" not in text  # unchanged ones are summarised, not listed with descriptions


def test_given_only_text_after_character_60_changed_then_the_difference_is_visible() -> None:
    start = "x" * 70
    old = [ListCategory("1", "Bills", start + " invoices")]
    new = [ListCategory("1", "Bills", start + " receipts")]

    text = _notice(old, new).text

    assert "Before: " + start + " invoices" in text
    assert "Now: " + start + " receipts" in text


def test_given_added_removed_and_renamed_categories_then_each_is_shown_with_its_text() -> None:
    old = [ListCategory("1", "Bills", "Invoices"), ListCategory("2", "Trips", "Flights"), ListCategory("3", "Keep", "")]
    new = [ListCategory("1", "Invoices", "Invoices"), ListCategory("4", "Receipts", "Shop receipts"), old[2]]

    text = _notice(old, new, changes=3).text

    assert "Renamed: Bills -> Invoices" in text
    assert "Added: Receipts: Shop receipts" in text
    assert "Removed: Trips: Flights" in text
    assert "Unchanged (1): Keep" in text
    assert "Undo restores the list. Mail already filed stays where it is." in text


def test_given_an_empty_list_then_the_notice_says_so() -> None:
    message = _notice([ListCategory("1", "Bills", "")], [])

    assert "Removed: Bills" in message.text
    assert "no categories" in message.text
