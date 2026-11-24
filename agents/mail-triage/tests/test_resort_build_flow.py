"""U-mail-categories-14, criteria 2, 6, 7, 8, 9: what a build writes (AC-9, AC-54, AC-17, AC-13, AC-18)."""

from __future__ import annotations

import re
import unicodedata
from datetime import timedelta

from app.core.judgement import OTHER_ID
from app.core.resort_plan import PlanState
from app.usecases.resort_build import BuildStatus
from tests.resort_build_support import FINANCE, TRAVEL, Rig


async def test_items_exist_only_for_mails_whose_category_would_change_and_nothing_moves() -> None:
    rig = Rig()
    rig.request()
    stays = rig.gmail.add_mail(("INBOX", rig.finance_label), subject="stays")  # already Finance, judged Finance
    moves = rig.gmail.add_mail(("INBOX", rig.finance_label), subject="moves")  # Finance, judged Travel
    unfiled = rig.gmail.add_mail(("INBOX",), subject="unfiled")  # no label, judged Other: no change
    rig.judge.by_subject = {"stays": FINANCE, "moves": TRAVEL, "unfiled": OTHER_ID}
    before = {mid: set(m.labels) for mid, m in rig.gmail.mail_table.items()}

    result = await rig.build.run_once()

    plan = rig.store.plan()
    assert result.status is BuildStatus.READY
    assert plan.state is PlanState.READY
    assert [i.message_id for i in rig.store.items_of(plan)] == [moves]
    item = rig.store.items_of(plan)[0]
    assert (str(item.old_topic_id), str(item.new_topic_id)) == (FINANCE, TRAVEL)
    assert plan.checked == 3
    assert {stays, unfiled}.isdisjoint(i.message_id for i in rig.store.items_of(plan))
    assert {mid: set(m.labels) for mid, m in rig.gmail.mail_table.items()} == before  # nothing moved


async def test_only_mail_in_scope_becomes_an_item() -> None:
    rig = Rig()
    rig.request()
    rig.gmail.add_label("Archive")
    ok = rig.gmail.add_mail(("INBOX",), subject="ok")
    rig.gmail.add_mail(("SPAM",), subject="spam")
    rig.gmail.add_mail(("TRASH", rig.finance_label), subject="trash")
    rig.gmail.add_mail((rig.gmail.label_id("Archive"), rig.finance_label), subject="archived")
    rig.gmail.add_mail(("INBOX", "DRAFT"), subject="draft")  # the system label id, not a name
    two = rig.gmail.add_mail((rig.finance_label, rig.travel_label), subject="two")
    rig.mailbox.ghosts.append("deleted-meanwhile")
    rig.judge.answer = TRAVEL

    await rig.build.run_once()

    plan = rig.store.plan()
    assert [i.message_id for i in rig.store.items_of(plan)] == [ok]
    assert plan.unclear == 1
    assert two not in [i.message_id for i in rig.store.items_of(plan)]


async def test_first_start_without_a_plan_builds_none_and_judges_no_mail() -> None:
    rig = Rig()  # the list was seeded this very moment; no plan exists
    rig.gmail.add_mail(("INBOX",), subject="a")
    rig.judge.answer = FINANCE

    result = await rig.build.run_once()
    rig.clock.advance(timedelta(days=1))
    later = await rig.build.run_once()

    assert (result.status, later.status) == (BuildStatus.IDLE, BuildStatus.IDLE)
    assert rig.store.plans == []
    assert rig.judge.calls == 0
    assert not [c for c in rig.gmail.calls if "modify" in c]


async def test_mail_with_only_the_label_of_a_deleted_category_is_not_planned_and_its_label_stays() -> None:
    rig = Rig()
    rig.request()
    gone = rig.gmail.add_label("Old shop")  # no longer in the list: not managed
    rig.mailbox.listed_names.add("Old shop")  # even a wide listing returns it
    rig.gmail.add_mail((gone,), subject="old")
    rig.judge.answer = OTHER_ID

    await rig.build.run_once()

    plan = rig.store.plan()
    assert rig.store.items_of(plan) == []
    assert (plan.checked, rig.judge.calls) == (0, 0)
    assert "Old shop" in rig.gmail.label_names()
    assert not [c for c in rig.gmail.calls if "delete" in c or "modify" in c]


async def test_rejected_mail_stays_out_until_the_list_changes_again() -> None:
    rig = Rig()
    rig.request(100)  # everything waits for review: no auto plan stays open and blocks the next request
    kept = rig.gmail.add_mail(("INBOX", rig.finance_label), subject="kept")
    other = rig.gmail.add_mail(("INBOX", rig.finance_label), subject="other")
    rig.judge.answer = TRAVEL
    rig.store.reject(kept)

    await rig.build.run_once()
    assert [i.message_id for i in rig.store.items_of(rig.store.plan())] == [other]

    rig.store.save_list()  # the list changes again: the rejection no longer holds
    await rig.build.run_once()  # replaces the ready plan
    rig.request(100)  # a request builds the next one
    await rig.build.run_once()
    assert {i.message_id for i in rig.store.items_of(rig.store.plan())} == {kept, other}


async def test_the_plan_notice_holds_numbers_only() -> None:
    rig = Rig()
    rig.request()
    hostile = "CANARY-SUBJECT-7f2e <b>approve</b>"
    rig.gmail.add_mail(("INBOX",), sender="CANARY-SENDER@example.test", subject=hostile, text="CANARY-BODY")
    rig.gmail.add_mail(("INBOX", rig.finance_label), subject="plain")
    rig.judge.answer = TRAVEL

    await rig.build.run_once()

    (text,) = rig.telegram.texts
    assert re.fullmatch(
        r"Sort again is ready: \d+ mails checked\. \d+ move on their own after the wait "
        r"\(you can cancel before then\), \d+ wait for your review in the web app\. "
        r"\d+ unclear, \d+ not looked at\.",
        text,
    )
    assert "2 mails checked. 2 move on their own" in text
    assert "0 wait for your review" in text
    assert len(rig.telegram.texts) == 1
    await rig.build.run_once()  # nothing new: no second notice
    assert len(rig.telegram.texts) == 1


async def test_pinned_mail_is_never_an_item() -> None:
    rig = Rig()
    rig.request()
    rig.gmail.add_mail(
        ("INBOX",),
        sender="no-reply@accounts.google.com",
        subject="Security alert",
        auth_results="mx.google.com; dmarc=pass header.from=accounts.google.com",
    )
    rig.judge.answer = TRAVEL

    await rig.build.run_once()

    assert rig.store.items_of(rig.store.plan()) == []
    assert rig.judge.calls == 0


async def test_the_plan_keeps_the_estimate_of_mail_in_scope_for_the_review_page() -> None:
    rig = Rig()
    rig.request()
    for n in range(3):
        rig.gmail.add_mail(("INBOX",), subject=f"s{n}")

    await rig.build.run_once()

    plan = rig.store.plan()
    assert rig.store.estimates[plan.plan_id] == 3
    assert rig.store.not_looked_at[plan.plan_id] == 0


async def test_sender_and_subject_lose_bidi_and_format_characters_and_are_capped() -> None:
    rig = Rig()
    rig.request()
    rtl, zwsp = chr(0x202E), chr(0x200B)
    rig.gmail.add_mail(
        ("INBOX",),
        sender=f'"Ann{rtl}{zwsp}Lee" <ann@example.test>',
        subject=f"inv{rtl}oice{chr(0x2066)}{zwsp}\n" + "x" * 300,
    )
    rig.judge.answer = TRAVEL

    await rig.build.run_once()

    (item,) = rig.store.items_of(rig.store.plan())
    assert item.sender_name == "AnnLee"
    assert item.subject.startswith("invoice ")
    assert len(item.subject) == 120
    for text in (item.sender_name, item.sender_address, item.subject):
        assert not [c for c in text if unicodedata.category(c) in {"Cf", "Cc"}]
