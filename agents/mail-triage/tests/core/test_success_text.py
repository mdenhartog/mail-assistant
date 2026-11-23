"""U-label-structure-14, criterion 2 (AC-63, D22): the success numbers and their fixed wording."""

from __future__ import annotations

import pytest

from app.usecases.report import SuccessCounts, success_text


def test_given_counts_when_worded_then_the_five_numbers_read_in_fixed_wording() -> None:
    counts = SuccessCounts(
        days=14,
        filed=200,
        by_rule=50,
        by_model=140,
        in_other=20,
        always_notify_alerts=7,
        system_applied=40,
        system_moved_back=3,
    )

    assert success_text(counts).splitlines() == [
        "Success numbers (last 14 days):",
        "Filed by a sender rule: 25.0% of 200 new mails",
        "At least 10.0 model calls per day (filing calls only)",
        "Always-notify alerts per day: 0.5",
        "Filed under Other: 10.0% of 200 new mails",
        "Moved back after system approval: at least 7.5% of 40 system-approved items",
    ]


def test_given_no_filed_mail_when_worded_then_the_shares_say_no_mail_and_nothing_divides_by_zero() -> None:
    text = success_text(
        SuccessCounts(
            days=14,
            filed=0,
            by_rule=0,
            by_model=0,
            in_other=0,
            always_notify_alerts=0,
            system_applied=0,
            system_moved_back=0,
        )
    )

    assert "Filed by a sender rule: no new mail" in text
    assert "Filed under Other: no new mail" in text
    assert "At least 0.0 model calls per day (filing calls only)" in text


def test_given_no_system_approved_items_when_worded_then_the_move_back_line_says_so_plainly() -> None:
    text = success_text(
        SuccessCounts(
            days=14,
            filed=1,
            by_rule=0,
            by_model=1,
            in_other=0,
            always_notify_alerts=0,
            system_applied=0,
            system_moved_back=0,
        )
    )

    assert text.splitlines()[-1] == "Moved back after system approval: no system-approved items"


def test_given_every_system_approved_item_moved_back_when_worded_then_the_share_is_one_hundred_percent() -> None:
    text = success_text(
        SuccessCounts(
            days=14,
            filed=1,
            by_rule=0,
            by_model=1,
            in_other=0,
            always_notify_alerts=0,
            system_applied=4,
            system_moved_back=4,
        )
    )

    assert text.splitlines()[-1] == "Moved back after system approval: at least 100.0% of 4 system-approved items"


def test_given_more_moved_back_than_applied_when_counts_are_built_then_it_is_refused() -> None:
    with pytest.raises(ValueError, match="moved back"):
        SuccessCounts(
            days=14,
            filed=0,
            by_rule=0,
            by_model=0,
            in_other=0,
            always_notify_alerts=0,
            system_applied=1,
            system_moved_back=2,
        )


@pytest.mark.parametrize("days", [0, -1])
def test_given_a_period_without_days_when_counts_are_built_then_it_is_refused(days: int) -> None:
    with pytest.raises(ValueError, match="days"):
        SuccessCounts(
            days=days,
            filed=0,
            by_rule=0,
            by_model=0,
            in_other=0,
            always_notify_alerts=0,
            system_applied=0,
            system_moved_back=0,
        )
