"""U-label-structure-14, criterion 2 (AC-63, D22): the success numbers and their fixed wording."""

from __future__ import annotations

import pytest

from app.usecases.report import SuccessCounts, success_text


def test_given_counts_when_worded_then_the_four_numbers_read_in_fixed_wording() -> None:
    counts = SuccessCounts(days=14, filed=200, by_rule=50, by_model=140, in_other=20, always_notify_alerts=7)

    assert success_text(counts).splitlines() == [
        "Success numbers (last 14 days):",
        "Filed by a sender rule: 25.0% of 200 new mails",
        "At least 10.0 model calls per day (filing calls only)",
        "Always-notify alerts per day: 0.5",
        "Filed under Other: 10.0% of 200 new mails",
    ]


def test_given_no_filed_mail_when_worded_then_the_shares_say_no_mail_and_nothing_divides_by_zero() -> None:
    text = success_text(SuccessCounts(days=14, filed=0, by_rule=0, by_model=0, in_other=0, always_notify_alerts=0))

    assert "Filed by a sender rule: no new mail" in text
    assert "Filed under Other: no new mail" in text
    assert "At least 0.0 model calls per day (filing calls only)" in text


def test_given_the_system_approval_number_when_worded_then_it_is_not_shown_before_release_two() -> None:
    text = success_text(SuccessCounts(days=14, filed=1, by_rule=0, by_model=1, in_other=0, always_notify_alerts=0))

    assert "Move back" not in text
    assert "approved" not in text


@pytest.mark.parametrize("days", [0, -1])
def test_given_a_period_without_days_when_counts_are_built_then_it_is_refused(days: int) -> None:
    with pytest.raises(ValueError, match="days"):
        SuccessCounts(days=days, filed=0, by_rule=0, by_model=0, in_other=0, always_notify_alerts=0)
