"""U-mail-categories-01 criteria 5 to 7, plus the FakeClock and BudgetLedger: the supporting fakes and seed data."""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime, timedelta

import pytest

from app.core.alert_text import AlertMessage
from tests.fakes.budget_ledger import BudgetLedger
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_gmail import FakeGmail
from tests.fakes.fake_telegram import CanaryLeakError, FakeTelegram
from tests.fakes.seeds import (
    BIDI_CONTROLS,
    CANARIES,
    bidi_subjects,
    categories,
    lookalike_names,
    plan_items,
    seed_scope_mails,
)
from tests.fakes.stub_model import HOSTILE_CORPUS, StubModel

START = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)


# --- criterion 5: the stub model ----------------------------------------------------------------------------------


def test_given_the_stub_model_when_asked_for_the_hostile_corpus_then_all_six_bad_answers_come_back() -> None:
    model = StubModel.hostile()

    answers = [model.answer("pick a category") for _ in range(len(HOSTILE_CORPUS))]

    assert answers[0] not in {"cat-1", "cat-2"}  # an unknown id
    assert len(answers[1].split()) == 2  # two ids
    assert "<" in answers[2]  # markup
    assert answers[3] == "approve"
    assert answers[4] == ""
    assert len(answers[5]) == 1001
    assert len(model.prompts) == 6


def test_given_a_scripted_stub_model_when_asked_then_it_replays_in_order_and_fails_loudly_when_empty() -> None:
    model = StubModel(["cat-1", "cat-2"])

    assert [model.answer("a"), model.answer("b")] == ["cat-1", "cat-2"]
    with pytest.raises(AssertionError, match="no scripted answer"):
        model.answer("c")


# --- criterion 6: the Telegram fake and canary strings ------------------------------------------------------------


async def test_given_a_notice_without_a_canary_when_sent_then_the_fake_records_the_text() -> None:
    telegram = FakeTelegram()

    message_id = await telegram.send(AlertMessage(text="3 mails moved", buttons=()))
    await telegram.say("done")
    await telegram.edit_message(message_id, "4 mails moved")
    await telegram.offer("undo?", "Undo", "undo:1")
    await telegram.answer_callback("cb-1")

    assert telegram.texts == ["3 mails moved", "done", "4 mails moved", "undo?"]


@pytest.mark.parametrize("canary", CANARIES)
async def test_given_a_notice_with_a_canary_when_sent_then_the_fake_fails_the_test(canary: str) -> None:
    telegram = FakeTelegram()

    with pytest.raises(CanaryLeakError):
        await telegram.say(f"Moved a mail from {canary}")
    with pytest.raises(CanaryLeakError):
        await telegram.send(AlertMessage(text=f"subject {canary.upper()}", buttons=()))

    assert telegram.texts == []  # a leaking text is not recorded as delivered


# --- criterion 7: seed factories ----------------------------------------------------------------------------------


def test_given_the_plan_factory_when_called_then_it_makes_1000_items_in_20_groups() -> None:
    items = plan_items()

    assert len(items) == 1000
    assert len({item.group for item in items}) == 20
    assert len({item.item_id for item in items}) == 1000
    assert all(item.from_category != item.to_category for item in items)


@pytest.mark.parametrize("count", [50, 51])
def test_given_the_category_factory_when_asked_for_50_or_51_then_that_many_unique_names_come_back(count: int) -> None:
    result = categories(count)

    assert len(result) == count
    assert len({c.name.casefold() for c in result}) == count
    assert all(c.name and "/" not in c.name for c in result)


def test_given_the_scope_factory_when_called_then_5001_in_scope_mails_are_in_the_fake_mailbox() -> None:
    gmail = FakeGmail()

    ids = seed_scope_mails(gmail)

    assert len(ids) == 5001
    assert len(set(ids)) == 5001
    listed = gmail.users().messages().list(userId="me", labelIds=["INBOX"]).execute()["messages"]
    assert len(listed) == 5001


def test_given_the_lookalike_factory_when_called_then_names_differ_but_normalise_to_one() -> None:
    pairs = lookalike_names()

    assert len(pairs) >= 3
    for plain, lookalike in pairs:
        assert plain != lookalike
        assert unicodedata.normalize("NFKC", lookalike) == plain


def test_given_the_bidi_factory_when_called_then_every_subject_carries_a_bidi_control() -> None:
    subjects = bidi_subjects()

    assert len(subjects) >= 3
    assert all(any(c in subject for c in BIDI_CONTROLS) for subject in subjects)


def test_given_the_canaries_when_listed_then_they_are_recognisable_and_unique() -> None:
    assert len(set(CANARIES)) == len(CANARIES) >= 3
    assert all(c.startswith("test-canary-") for c in CANARIES)


# --- FakeClock and BudgetLedger -----------------------------------------------------------------------------------


def test_given_a_fake_clock_when_advanced_then_now_and_today_follow_without_sleeping() -> None:
    clock = FakeClock(START)

    clock.advance(timedelta(hours=16))

    assert clock() == clock.now() == START + timedelta(hours=16)
    assert clock.today() == "2026-11-15"


def test_given_a_budget_above_the_reserve_when_it_is_used_up_then_the_reserve_stays_and_the_next_day_refills() -> None:
    clock = FakeClock(START)
    ledger = BudgetLedger(clock, daily_total=100, reserve=30)

    assert ledger.available() == 70
    assert ledger.spend(70) is True
    assert ledger.spend(1) is False  # the reserve is never used by the plan
    assert ledger.available() == 0
    assert ledger.spend_reserve(30) is True

    clock.advance(timedelta(days=1))

    assert ledger.available() == 70


def test_given_a_zero_budget_above_the_reserve_when_spending_then_nothing_is_allowed() -> None:
    ledger = BudgetLedger(FakeClock(START), daily_total=30, reserve=30)

    assert ledger.available() == 0
    assert ledger.spend(1) is False
