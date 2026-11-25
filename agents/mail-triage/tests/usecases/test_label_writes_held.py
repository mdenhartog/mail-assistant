"""RED-002: triage and catch-up never create, adopt or rename a label while the rename plan is not done (R4).

The mailbox here is the real ``GmailReader`` on ``FakeGmail`` and the label book hands its managed set (with the
hold) to it, as ``PgLabelBook`` does. A mail whose label has no stored id is left alone and counted; nothing is
written to Gmail for it. A label with a stored id is still used, so mail keeps being filed under the old labels.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.gmail_read import GmailReader
from app.core.judgement import Judgement, JudgingList, ListedCategory
from tests.fakes.fake_gmail import FakeGmail
from tests.usecases.fakes_labels import FakeLabelBook
from tests.usecases.test_catchup import FakeJudge as CatchUpJudge
from tests.usecases.test_catchup import FakeStore as CatchUpStore
from tests.usecases.test_catchup import catchup
from tests.usecases.test_triage_judging_v2 import FACTUREN, FACTUREN_ID, RecordingJudge, verdict
from tests.usecases.test_triage import FINANCE_ID, FakeJudge, FakeStore, pipeline

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

_WRITES = {"labels.create", "labels.patch", "labels.delete", "messages.modify"}
OTHER_VERDICT = Judgement(topic_id="cat-unknown", urgent=False, reason="r", summary="s", confidence=0.9)


class RealMailbox(GmailReader):
    """The real adapter; only the listing is fixed, as the history position is not what is tested here."""

    def __init__(self, gmail: FakeGmail, ids: list[str]) -> None:
        super().__init__(gmail, sleep=lambda _s: None)
        self.ids = ids

    def list_new(self, history_id: str | None) -> tuple[list[str], str]:
        return ([] if history_id is None else list(self.ids)), "200"

    def list_unread_before(self, cutoff: datetime) -> list[str]:
        del cutoff
        return list(self.ids)


def writes(gmail: FakeGmail) -> list[str]:
    return [call for call in gmail.calls if call in _WRITES]


def rig(
    labels: Callable[[], FakeLabelBook] | None = None, *, held: bool = True, stored: dict[str, str] | None = None
) -> tuple[FakeGmail, str, RealMailbox, FakeLabelBook]:
    gmail = FakeGmail()
    gmail.add_label("Assistant/Other")  # the old Other label: its id is not stored anywhere
    mail = gmail.add_mail(("INBOX", "UNREAD"))
    mailbox = RealMailbox(gmail, [mail])
    book = FakeLabelBook(lambda: FakeStore().current, writes_held=held, stored=stored or {}, followers=[mailbox])
    return gmail, mail, mailbox, book


async def test_given_the_plan_is_pending_when_a_mail_belongs_in_other_then_it_is_left_alone_and_counted() -> None:
    gmail, mail, mailbox, book = rig()
    store = FakeStore()
    names = dict(gmail.label_table)

    summary = await pipeline(mailbox, FakeJudge(OTHER_VERDICT), store, labels=book).run_once()

    assert gmail.label_table == names  # no "Other" label made, none adopted
    assert writes(gmail) == []
    assert "INBOX" in gmail.mail_table[mail].labels
    assert (summary.filed, summary.held, summary.retry_later, summary.given_up) == (0, 1, 1, 0)
    assert store.done == {}  # not completed
    assert store.failures == {}  # and not a failed attempt
    assert store.history == "100"  # the position stays: the mail is listed again once the plan is done


async def test_given_a_user_label_called_other_when_the_plan_is_pending_then_triage_does_not_adopt_it() -> None:
    gmail, mail, mailbox, book = rig()
    users = gmail.add_label("Other")

    await pipeline(mailbox, FakeJudge(OTHER_VERDICT), FakeStore(), labels=book).run_once()

    assert users not in gmail.mail_table[mail].labels
    assert writes(gmail) == []


async def test_given_the_plan_is_pending_when_the_category_label_has_a_stored_id_then_the_mail_is_filed_by_id() -> None:
    gmail, mail, mailbox, book = rig()
    old = gmail.add_label("Assistant/Finance")
    book = FakeLabelBook(lambda: FakeStore().current, writes_held=True, stored={"Finance": old}, followers=[mailbox])
    judged = Judgement(topic_id=FINANCE_ID, urgent=False, reason="r", summary="s", confidence=0.9)

    summary = await pipeline(mailbox, FakeJudge(judged), FakeStore(), labels=book).run_once()

    assert gmail.mail_table[mail].labels == {"UNREAD", old}
    assert (summary.filed, summary.held) == (1, 0)
    assert "labels.create" not in gmail.calls


async def test_given_the_plan_is_done_when_a_mail_belongs_in_other_then_the_label_is_made_as_before() -> None:
    gmail, mail, mailbox, book = rig(held=False)

    summary = await pipeline(mailbox, FakeJudge(OTHER_VERDICT), FakeStore(), labels=book).run_once()

    assert "Other" in gmail.label_table.values()
    assert (summary.filed, summary.held) == (1, 0)
    assert "INBOX" not in gmail.mail_table[mail].labels


async def test_given_the_plan_is_pending_when_the_catch_up_files_into_other_then_it_is_left_alone() -> None:
    gmail, mail, mailbox, book = rig()
    store = CatchUpStore()
    names = dict(gmail.label_table)

    summary = await catchup(mailbox, CatchUpJudge(OTHER_VERDICT), store, labels=book).run_once()

    assert gmail.label_table == names
    assert writes(gmail) == []
    assert "INBOX" in gmail.mail_table[mail].labels
    assert (summary.filed, summary.held, summary.given_up) == (0, 1, 0)
    assert store.done == {}
    assert store.failures == {}
    assert "finish_catchup" not in store.events  # the old mail is still to do


FINANCE = ListedCategory(FINANCE_ID, "Finance", "Bills and invoices")
EXTRA_LIST = JudgingList(3, (FINANCE, FACTUREN))


async def test_given_the_plan_is_pending_when_the_extra_label_has_no_stored_id_then_the_mail_is_left_alone_whole() -> None:
    gmail, mail, mailbox, _ = rig()
    topic_id = gmail.add_label("Assistant/Finance")
    book = FakeLabelBook(
        lambda: EXTRA_LIST, writes_held=True, stored={"Finance": topic_id, "Other": "x"}, followers=[mailbox]
    )
    store = FakeStore(current=EXTRA_LIST)
    names = dict(gmail.label_table)

    summary = await pipeline(mailbox, RecordingJudge(verdict(FINANCE_ID, FACTUREN_ID)), store, labels=book).run_once()

    assert gmail.label_table == names  # the extra label is not made, not adopted
    assert writes(gmail) == []  # and the topic label is not added either: a mail is filed whole or not at all
    assert "INBOX" in gmail.mail_table[mail].labels
    assert (summary.filed, summary.held, summary.given_up) == (0, 1, 0)
    assert store.done == {}


async def test_given_the_plan_is_pending_when_the_extra_label_has_a_stored_id_then_both_labels_are_added_by_id() -> None:
    gmail, mail, mailbox, _ = rig()
    topic_id = gmail.add_label("Assistant/Finance")
    extra_id = gmail.add_label("Assistant/Facturen")
    book = FakeLabelBook(
        lambda: EXTRA_LIST,
        writes_held=True,
        stored={"Finance": topic_id, "Facturen": extra_id, "Other": "x"},
        followers=[mailbox],
    )
    store = FakeStore(current=EXTRA_LIST)

    summary = await pipeline(mailbox, RecordingJudge(verdict(FINANCE_ID, FACTUREN_ID)), store, labels=book).run_once()

    assert gmail.mail_table[mail].labels == {"UNREAD", topic_id, extra_id}
    assert (summary.filed, summary.held) == (1, 0)
    assert "labels.create" not in gmail.calls
