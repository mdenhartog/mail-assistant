"""U-label-prefix-removal-17: triage and catch-up file by id under the list label or the Other setting (AC 1-3, 12)."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from app.core.judgement import Judgement, JudgingList, ListedCategory
from app.core.managed import Role
from tests.usecases.fakes_labels import FakeLabelBook
from tests.usecases.test_catchup import FakeJudge as CatchUpJudge
from tests.usecases.test_catchup import FakeMailbox as CatchUpMailbox
from tests.usecases.test_catchup import FakeStore as CatchUpStore
from tests.usecases.test_catchup import catchup
from tests.usecases.test_catchup import fetched as old_mail
from tests.usecases.test_triage import FINANCE_ID, FakeJudge, FakeMailbox, FakeStore, fetched, pipeline

HOUSE_ID = "00000000-0000-0000-0000-00000000000b"
TWO_TOPICS = JudgingList(
    version=3,
    categories=(
        ListedCategory(FINANCE_ID, "Finance", "Bills"),
        ListedCategory(HOUSE_ID, "House", "House"),
    ),
)
APP = Path(__file__).resolve().parents[2] / "app" / "usecases"


def judged(topic: str) -> Judgement:
    return Judgement(topic_id=topic, urgent=False, reason="r", summary="s", confidence=0.9)


async def test_given_no_fitting_category_when_triaged_then_it_is_filed_under_the_other_setting_by_id() -> None:
    mailbox, store = FakeMailbox(["m1"]), FakeStore()
    book = FakeLabelBook(lambda: store.current, other_name="Misc")

    await pipeline(mailbox, FakeJudge(judged("cat-unknown")), store, labels=book).run_once()

    assert mailbox.filed == [("m1", "id:Misc")]
    assert store.outcomes["m1"].label == "Misc"


async def test_given_the_stored_other_id_differs_from_the_one_used_when_triaged_then_the_new_id_is_stored() -> None:
    mailbox, store = FakeMailbox(["m1"]), FakeStore()
    book = FakeLabelBook(lambda: store.current, other_name="Misc", other_id="Label_77")

    await pipeline(mailbox, FakeJudge(judged("cat-unknown")), store, labels=book).run_once()

    assert [(label.role, label_id) for label, label_id in book.remembered] == [(Role.OTHER, "id:Misc")]


async def test_given_a_managed_category_when_triaged_then_only_the_list_label_without_prefix_is_added() -> None:
    mailbox, store = FakeMailbox(["m1"]), FakeStore()

    await pipeline(mailbox, FakeJudge(judged(FINANCE_ID)), store).run_once()

    assert mailbox.filed == [("m1", "id:Finance")]
    assert mailbox.extra == []
    assert set(mailbox.calls) == {"list_new", "fetch", "ensure_label", "file"}


async def test_given_a_label_that_is_refused_when_triaged_then_the_mail_goes_to_other_by_id() -> None:
    mailbox, store = FakeMailbox(["m1"]), FakeStore(current=JudgingList(3, (ListedCategory(FINANCE_ID, "A..B", "x"),)))

    await pipeline(mailbox, FakeJudge(judged(FINANCE_ID)), store).run_once()

    assert mailbox.filed == [("m1", "id:Other")]
    assert store.outcomes["m1"].label == "Other"


async def test_given_the_file_call_returns_another_id_when_triaged_then_that_id_is_stored() -> None:
    class Recreated(FakeMailbox):
        def file(self, message_id: str, label_id: str) -> str:
            super().file(message_id, label_id)
            return "Label_new"

    mailbox, store = Recreated(["m1"]), FakeStore()
    book = FakeLabelBook(lambda: store.current)

    await pipeline(mailbox, FakeJudge(judged(FINANCE_ID)), store, labels=book).run_once()

    assert [(label.name, label_id) for label, label_id in book.remembered] == [("Finance", "Label_new")]


async def test_given_a_mail_with_two_topic_labels_when_triaged_then_it_is_left_alone() -> None:
    mailbox, store = FakeMailbox(["m1"]), FakeStore(current=TWO_TOPICS)
    mailbox.mails["m1"] = replace(fetched("m1"), labels=frozenset({"INBOX", "id:Finance", "id:House"}))

    summary = await pipeline(mailbox, FakeJudge(judged(FINANCE_ID)), store).run_once()

    assert (mailbox.filed, store.claimed, summary.filed) == ([], set(), 0)


async def test_given_a_mail_in_the_archive_label_when_triaged_then_it_is_left_alone() -> None:
    mailbox, store = FakeMailbox(["m1"]), FakeStore()
    book = FakeLabelBook(lambda: store.current, archive_id="Label_arch")
    mailbox.mails["m1"] = replace(fetched("m1"), labels=frozenset({"INBOX", "Label_arch"}))

    await pipeline(mailbox, FakeJudge(judged(FINANCE_ID)), store, labels=book).run_once()

    assert (mailbox.filed, store.claimed) == ([], set())


async def test_given_a_mail_that_only_carries_amerika_when_the_catch_up_looks_at_it_then_it_is_left_alone() -> None:
    mailbox, store = CatchUpMailbox(["m1"]), CatchUpStore()
    mailbox.mails["m1"] = old_mail("m1", labels=frozenset({"UNREAD", "Label_9"}))
    book = FakeLabelBook(lambda: store.current, names={"Label_9": "Amerika"})

    summary = await catchup(mailbox, CatchUpJudge(), store, labels=book).run_once()

    assert (mailbox.filed, store.claimed, summary.filed) == ([], set(), 0)
    assert mailbox.ensured == []


async def test_given_an_inbox_mail_with_a_user_label_when_the_catch_up_files_it_then_the_list_label_is_used() -> None:
    mailbox, store = CatchUpMailbox(["m1"]), CatchUpStore()
    mailbox.mails["m1"] = old_mail("m1", labels=frozenset({"INBOX", "UNREAD", "Label_9"}))
    book = FakeLabelBook(lambda: store.current, names={"Label_9": "Amerika"})

    await catchup(mailbox, CatchUpJudge(), store, labels=book).run_once()

    assert (mailbox.ensured, mailbox.filed_under) == (["Finance"], ["id:Finance"])


async def test_given_no_fitting_category_when_the_catch_up_files_it_then_it_goes_under_the_other_setting() -> None:
    mailbox, store = CatchUpMailbox(["m1"]), CatchUpStore()
    book = FakeLabelBook(lambda: store.current, other_name="Misc")

    await catchup(mailbox, CatchUpJudge(judged("cat-unknown")), store, labels=book).run_once()

    assert (mailbox.ensured, mailbox.filed_under) == (["Misc"], ["id:Misc"])


async def test_given_a_stored_id_that_differs_when_the_catch_up_files_it_then_the_new_id_is_stored() -> None:
    mailbox, store = CatchUpMailbox(["m1"]), CatchUpStore()
    book = FakeLabelBook(lambda: store.current, other_id="Label_77")

    await catchup(mailbox, CatchUpJudge(judged("cat-unknown")), store, labels=book).run_once()

    assert [(label.role, label_id) for label, label_id in book.remembered] == [(Role.OTHER, "id:Other")]


async def test_given_a_mail_with_two_topic_labels_when_the_catch_up_looks_at_it_then_it_is_left_alone() -> None:
    mailbox, store = CatchUpMailbox(["m1"]), CatchUpStore(current=TWO_TOPICS)
    mailbox.mails["m1"] = old_mail("m1", labels=frozenset({"INBOX", "UNREAD", "id:Finance", "id:House"}))

    await catchup(mailbox, CatchUpJudge(), store).run_once()

    assert (mailbox.filed, store.claimed) == ([], set())


def test_given_the_source_when_searched_then_no_prefix_and_no_other_constant_appear() -> None:
    for name in ("triage.py", "catchup.py"):
        text = (APP / name).read_text(encoding="utf-8")
        assert not re.search(r"OTHER_LABEL|LABEL_PREFIX|Assistant/", text), name
