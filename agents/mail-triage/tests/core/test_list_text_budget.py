"""List notice words: exact budget, tier and wording boundaries (mutation gate, U-mail-categories-34)."""
# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.core import list_text
from app.core.alert_text import MAX_MESSAGE_CHARS
from app.core.list_text import ListCategory

AT = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
NONCE = "A" * 22
NL = chr(10)
HEADER = "Your category list was changed ({count}, last at 2026-11-14 09:00 UTC)."


def _copy(value: str) -> str:
    """An equal string that is a different object (kills identity-comparison mutants)."""
    return "".join(list(value))


def _cat(ident: str, name: str, description: str = "") -> ListCategory:
    return ListCategory(_copy(ident), _copy(name), _copy(description))


def test_given_a_list_category_when_changed_then_it_is_frozen_and_slotted() -> None:
    category = _cat("1", "A")
    assert not hasattr(category, "__dict__")
    with pytest.raises(FrozenInstanceError):
        category.__setattr__("name", "B")


def test_given_the_caps_when_text_is_longer_then_names_and_descriptions_are_cut() -> None:
    assert list_text.plain("n" * 100, list_text.NAME_CHARS) == "n" * 40
    assert list_text._line(_cat("1", "n" * 100, "d" * 100)) == f"- {'n' * 40}: {'d' * 60}"
    assert list_text._line(_cat("1", "Name")) == "- Name"
    assert (list_text.NAME_CHARS, list_text.DESCRIPTION_CHARS, list_text.CHANGED_DESCRIPTION_CHARS) == (40, 60, 500)


def test_given_no_categories_when_a_section_is_made_then_it_says_so() -> None:
    assert list_text._section("T", [], 100) == "T\n(no categories)"


def test_given_a_budget_when_lines_fit_exactly_then_all_are_shown_and_one_less_drops_the_last() -> None:
    cats = [_cat(str(n), "Name") for n in range(3)]  # each line "- Name" is 6 characters, 7 with the line break
    assert list_text._section("T", cats, 21) == "T\n- Name\n- Name\n- Name"
    assert list_text._section("T", cats, 20) == "T\n- Name\n- Name\n...and 1 more"


def test_given_many_categories_when_only_some_fit_then_the_rest_is_counted_and_later_lines_are_not_added() -> None:
    cats = [_cat(str(n), "Name" if n < 2 else "N") for n in range(5)]  # a short line after the cut must not slip in
    assert list_text._section("T", cats, 14) == "T\n- Name\n- Name\n...and 3 more"


def test_given_a_description_when_a_line_is_made_then_it_follows_the_name() -> None:
    assert list_text._line(_cat("1", "A", "about")) == "- A: about"


def test_given_the_changes_when_the_count_is_one_or_not_then_the_header_says_change_or_changes() -> None:
    def header(changes: int) -> str:
        message = list_text.change_notice(
            (_cat("1", "A"),), (_cat("1", "A"),), changes=changes, at=AT, undo_data="u", lock_data="l"
        )
        return message.text.split("\n")[0]

    assert header(1) == HEADER.format(count="1 change")
    assert header(0) == HEADER.format(count="0 changes")
    assert header(2) == HEADER.format(count="2 changes")


def test_given_a_notice_when_it_is_built_then_the_budgets_come_from_the_limit_minus_the_fixed_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, int] = {}
    blocks = iter(["X", "XY", "XYZ", "XYZW"])
    header = HEADER.format(count="1 change")
    expected = MAX_MESSAGE_CHARS - len(header) - len(list_text.UNDO_NOTE) - 400

    def block(_old: object, _new: object, budget: int) -> str:
        seen["block"] = budget
        return next(blocks)

    def unchanged(_old: object, _new: object, room: int) -> str:
        seen["room"] = room
        return ""

    monkeypatch.setattr(list_text, "_changes_block", block)
    monkeypatch.setattr(list_text, "_unchanged", unchanged)

    for length in (1, 2, 3, 4):
        list_text.change_notice((), (_cat("1", "A"),), changes=1, at=AT, undo_data="u", lock_data="l")
        assert seen["block"] == expected
        assert seen["room"] == expected - length


def test_given_only_the_order_changed_when_a_notice_is_built_then_it_says_so() -> None:
    a, b = _cat("1", "A"), _cat("2", "B")
    message = list_text.change_notice((a, b), (b, a), changes=1, at=AT, undo_data="u", lock_data="l")
    assert "No category was added, removed or changed; only the order differs." in message.text
    assert "Unchanged (2): B, A" in message.text


def test_given_notice_arguments_when_given_by_position_then_they_are_refused() -> None:
    with pytest.raises(TypeError):
        list_text.change_notice((), (), 1, AT, "u", "l")  # type: ignore[misc]
    with pytest.raises(TypeError):
        list_text.undone((), True)  # type: ignore[misc]


def test_given_the_restored_list_when_undone_then_the_section_gets_half_the_room(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[int] = []

    def section(title: str, _categories: object, budget: int) -> str:
        seen.append(budget)
        return title

    monkeypatch.setattr(list_text, "_section", section)

    assert list_text.undone(()) == "Undone. The list from before is back:"
    assert seen == [(4096 - 400) // 2]
    assert isinstance(seen[0], int)  # a float budget would be a different, lossy calculation


def test_given_the_lock_button_when_undone_then_the_lock_note_follows_only_then() -> None:
    cats = (_cat("1", "A"),)
    assert list_text.undone(cats) == "Undone. The list from before is back:\n- A"
    assert list_text.undone(cats, locked=True) == (
        "Undone. The list from before is back:\n- A\n\nWeb sign-in is locked. Send /web_unlock to allow it again."
    )


def test_given_an_outcome_when_locked_then_the_note_is_appended() -> None:
    assert list_text.locked("Done.") == "Done. Web sign-in is locked. Send /web_unlock to allow it again."


def test_given_button_parts_when_checked_then_only_a_valid_action_and_nonce_pass() -> None:
    assert list_text.button_data("catundo", NONCE) == f"catundo:{NONCE}"
    assert list_text.button_data("catlock", NONCE) == f"catlock:{NONCE}"
    for action, nonce in (("other", NONCE), ("catundo", "short"), ("other", "short")):
        with pytest.raises(ValueError, match="not a valid list button"):
            list_text.button_data(action, nonce)
    assert list_text.split_button(f"catundo:{NONCE}") == ("catundo", NONCE)
    assert list_text.split_button(f"catlock:{NONCE}") == ("catlock", NONCE)
    for data in (f"other:{NONCE}", "catundo:short", "other:short", "catundo"):
        assert list_text.split_button(data) is None


def test_given_a_changed_category_when_its_name_or_text_differs_then_the_entry_names_the_difference() -> None:
    old = [_cat("1", "Bb", "one"), _cat("2", "Same", "same"), _cat("3", "Cc", "x")]
    new = [_cat("1", "Aa", "two"), _cat("2", "Same", "same"), _cat("3", "Dd", "x")]
    assert list_text._changed_entries(old, new, 500) == [
        "~ Renamed: Bb -> Aa\n  Before: one\n  Now: two",
        "~ Renamed: Cc -> Dd",
    ]


def test_given_a_description_change_when_the_name_is_the_same_then_it_is_changed_not_renamed() -> None:
    for before, after in (("a", "b"), ("b", "a")):
        entries = list_text._changed_entries([_cat("1", "Nn", before)], [_cat("1", "Nn", after)], 500)
        assert entries == [f"~ Changed: Nn\n  Before: {before}\n  Now: {after}"]


def test_given_the_same_text_after_the_cut_when_changed_then_it_says_only_that_the_description_changed() -> None:
    was, now = _cat("1", "Nn", "abcdefX"), _cat("1", "Nn", "abcdefY")
    assert list_text._changed_entry(was, now, 6) == "~ Changed: Nn\n  The description changed."
    assert list_text._changed_entry(was, now, 0) == "~ Changed: Nn\n  The description changed."
    assert list_text._changed_entry(was, now, 7) == "~ Changed: Nn\n  Before: abcdefX\n  Now: abcdefY"
    assert list_text._changed_entry(now, was, 7) == "~ Changed: Nn\n  Before: abcdefY\n  Now: abcdefX"


def test_given_a_rename_only_when_the_description_is_equal_then_only_the_head_is_shown() -> None:
    assert list_text._changed_entry(_cat("1", "Aa", "desc"), _cat("1", "Bb", "desc"), 500) == "~ Renamed: Aa -> Bb"
    assert list_text._changed_entry(_cat("1", "Bb", "desc"), _cat("1", "Aa", "desc"), 500) == "~ Renamed: Bb -> Aa"


def test_given_added_and_removed_categories_when_listed_then_text_is_shown_only_with_room() -> None:
    old, new = [_cat("1", "Gone", "bye")], [_cat("2", "New", "hi")]
    assert list_text._changed_entries(old, new, 500) == ["+ Added: New: hi", "- Removed: Gone: bye"]
    assert list_text._changed_entries(old, new, 0) == ["+ Added: New", "- Removed: Gone"]
    assert list_text._changed_entries([_cat("1", "G", "")], [_cat("2", "N", "")], 500) == [
        "+ Added: N: (no description)",
        "- Removed: G: (no description)",
    ]


def test_given_unchanged_categories_when_listed_then_names_fit_exactly_or_only_the_count_is_given() -> None:
    old = [_cat("1", "Aa", "x"), _cat("2", "Bb", "y"), _cat("3", "Cc", "z")]
    new = [_cat("1", "Aa", "x"), _cat("2", "Bb", "y"), _cat("3", "Cc", "changed")]
    line = "Unchanged (2): Aa, Bb"
    assert list_text._unchanged(old, new, len(line)) == line
    assert list_text._unchanged(old, new, len(line) + 5) == line
    assert list_text._unchanged(old, new, len(line) - 1) == "Unchanged (2): not listed here"
    assert list_text._unchanged(old, [_cat("3", "Cc", "changed")], 100) == ""
    swapped = [_cat("1", "Bb", "x"), _cat("2", "Bb", "z")]  # greater and lesser texts are changed, not unchanged
    assert list_text._unchanged(old[:2], swapped, 100) == ""


def test_given_a_long_description_when_the_budget_shrinks_then_the_tiers_cut_it_at_500_200_80_and_none() -> None:
    new = [_cat("1", "N", "a" * 600)]
    expected = {
        500: "+ Added: N: " + "a" * 500,
        200: "+ Added: N: " + "a" * 200,
        80: "+ Added: N: " + "a" * 80,
        0: "+ Added: N",
    }
    tiers = [500, 200, 80, 0]
    for index, cap in enumerate(tiers):
        assert list_text._changes_block([], new, len(expected[cap]) + 2) == expected[cap]
        if index + 1 < len(tiers):
            assert list_text._changes_block([], new, len(expected[cap]) + 1) == expected[tiers[index + 1]]


def test_given_no_change_when_the_block_is_made_then_it_is_empty() -> None:
    assert list_text._changes_block([_cat("1", "A")], [_cat("1", "A")], 1000) == ""


def test_given_entries_that_do_not_fit_when_the_block_is_made_then_whole_entries_up_to_the_budget_are_shown() -> None:
    new = [_cat(str(n), str(n) * 4 + "x" * 36) for n in range(10)]  # "+ Added: " and 40 characters: 49, 51 with the gap
    base = len(list_text._NOT_FIT.format(shown=10, total=10))
    entries = [f"+ Added: {category.name}" for category in new]

    two = list_text._changes_block([], new, base + 102)
    one = list_text._changes_block([], new, base + 101)

    assert two == "\n\n".join([*entries[:2], list_text._NOT_FIT.format(shown=2, total=10)])
    assert one == "\n\n".join([*entries[:1], list_text._NOT_FIT.format(shown=1, total=10)])
    assert list_text._changes_block([], new, 0) == list_text._NOT_FIT.format(shown=0, total=10)


def test_given_odd_and_even_line_lengths_when_the_budget_is_tight_then_the_count_is_exact() -> None:
    odd = [_cat(str(n), "Nam") for n in range(3)]  # "- Nam" is 5 characters, 6 with the line break
    assert list_text._section("T", odd, 18) == NL.join(["T", "- Nam", "- Nam", "- Nam"])
    assert list_text._section("T", odd, 17) == NL.join(["T", "- Nam", "- Nam", "...and 1 more"])


def test_given_a_long_line_after_a_short_one_when_it_does_not_fit_then_later_short_lines_are_not_squeezed_in() -> None:
    cats = [_cat("1", "A"), _cat("2", "L" * 30), _cat("3", "B")]
    assert list_text._section("T", cats, 10) == NL.join(["T", "- A", "...and 2 more"])


def test_given_entries_of_every_length_residue_when_they_just_fit_then_the_sum_is_exact() -> None:
    for name in ("N", "Na", "Nam", "Name", "Names"):  # entry lengths 10 to 14 cover every bit pattern
        new = [_cat("1", name)]
        entry = f"+ Added: {name}"
        assert list_text._changes_block([], new, len(entry) + 2) == entry
        assert list_text._changes_block([], new, len(entry) + 1) == list_text._NOT_FIT.format(shown=0, total=1)


def test_given_a_long_entry_between_short_ones_when_it_does_not_fit_then_short_ones_after_it_are_left_out() -> None:
    new = [_cat(str(n), name) for n, name in enumerate(["a" * 40, "b" * 40, "c"])]
    base = len(list_text._NOT_FIT.format(shown=3, total=3))
    budget = base + 51 + 20  # the first long entry fits, the second does not, the short last one would
    text = list_text._changes_block([], [*new, *[_cat(str(n), "x" * 40) for n in range(10, 17)]], budget)
    assert text.startswith("+ Added: " + "a" * 40 + NL * 2 + list_text._NOT_FIT.format(shown=1, total=10)[:10])
    assert text.endswith(list_text._NOT_FIT.format(shown=1, total=10))
    assert "+ Added: c" not in text


def test_given_short_entries_when_the_budget_ends_between_them_then_the_gap_of_two_is_counted() -> None:
    new = [_cat(str(n), f"n{n}xyz"[:5]) for n in range(10)]  # entries of 14 characters, 16 with the gap
    base = len(list_text._NOT_FIT.format(shown=10, total=10))
    entries = [f"+ Added: {c.name}" for c in new]
    text = list_text._changes_block([], new, base + 44)
    assert text == (NL * 2).join([*entries[:2], list_text._NOT_FIT.format(shown=2, total=10)])
