"""U-mail-categories-22, criterion 3: the Gmail side of the plan build, on the Gmail double.

Only mail of the inbox or under an ``Assistant/`` label is offered (spam, trash and archived mail are not), newest
first. A cursor is a message id: a new process (after a crash) continues just after it, with no mail twice and none
missed. A mail that was deleted after it was listed reads as ``None``.
"""

from __future__ import annotations

import pytest
from googleapiclient.errors import HttpError

from app.adapters.gmail_build import PAGE_SIZE, GmailBuild
from tests.fakes.fake_gmail import FakeGmail


def _build(gmail: FakeGmail, *, page_size: int = PAGE_SIZE) -> GmailBuild:
    return GmailBuild(gmail, sleep=lambda _seconds: None, page_size=page_size)


def _ids(found: list) -> list[str]:  # type: ignore[type-arg]
    return [c.message_id for c in found]


def test_only_mail_in_the_inbox_or_under_an_assistant_label_is_offered_newest_first() -> None:
    gmail = FakeGmail()
    finance = gmail.add_label("Assistant/Finance")
    archive = gmail.add_label("Archive")
    in_scope_old = gmail.add_mail(("INBOX",))
    labelled = gmail.add_mail((finance,))
    gmail.add_mail((archive,))  # archived: out of scope
    gmail.add_mail(("TRASH",))
    gmail.add_mail(("SPAM",))
    gmail.add_mail(())  # no label at all
    in_scope_new = gmail.add_mail(("INBOX", finance))

    found = _build(gmail).candidates(None, 100)

    assert _ids(found) == [in_scope_new, labelled, in_scope_old]


def test_the_estimate_counts_the_mail_in_scope_only() -> None:
    gmail = FakeGmail()
    for _ in range(3):
        gmail.add_mail(("INBOX",))
    gmail.add_mail(("TRASH",))

    assert _build(gmail).estimate_in_scope() == 3


def test_a_new_process_continues_after_the_cursor_without_a_gap_or_a_repeat() -> None:
    gmail = FakeGmail()
    mails = [gmail.add_mail(("INBOX",)) for _ in range(7)]
    newest_first = list(reversed(mails))
    first_run = _build(gmail, page_size=2)

    page = first_run.candidates(None, 3)
    assert _ids(page) == newest_first[:3]

    restarted = _build(gmail, page_size=2)  # the old process crashed: nothing is remembered but the stored cursor
    rest = restarted.candidates(page[-1].resume_after, 100)

    assert _ids(rest) == newest_first[3:]
    assert _build(gmail, page_size=2).candidates(rest[-1].resume_after, 100) == []  # the end


def test_pages_are_walked_in_order_across_the_page_size_and_the_limit() -> None:
    gmail = FakeGmail()
    mails = [gmail.add_mail(("INBOX",)) for _ in range(5)]
    build = _build(gmail, page_size=2)
    seen: list[str] = []
    cursor: str | None = None
    while page := build.candidates(cursor, 2):
        seen += _ids(page)
        cursor = page[-1].resume_after

    assert seen == list(reversed(mails))


def test_a_cursor_whose_mail_was_deleted_starts_again_from_the_top_instead_of_getting_stuck() -> None:
    gmail = FakeGmail()
    mails = [gmail.add_mail(("INBOX",)) for _ in range(4)]
    cursor = _build(gmail).candidates(None, 2)[-1].resume_after
    gmail.delete_mail(cursor)

    found = _build(gmail).candidates(cursor, 100)

    assert _ids(found) == [m for m in reversed(mails) if m != cursor]


def test_a_deleted_mail_reads_as_none_and_an_existing_one_has_its_headers_text_and_labels() -> None:
    gmail = FakeGmail()
    finance = gmail.add_label("Assistant/Finance")
    kept = gmail.add_mail(("INBOX", finance), sender="Ann <ann@example.test>", subject="Invoice", text="Pay me")
    ghost = gmail.add_mail(("INBOX",))
    build = _build(gmail)
    assert _ids(build.candidates(None, 10)) == [ghost, kept]
    gmail.delete_mail(ghost)

    assert build.fetch(ghost) is None
    mail = build.fetch(kept)
    assert mail is not None
    assert (mail.subject, mail.text, mail.sender) == ("Invoice", "Pay me", "ann@example.test")
    assert mail.labels == {"INBOX", finance}


def test_the_label_names_map_ids_to_names() -> None:
    gmail = FakeGmail()
    finance = gmail.add_label("Assistant/Finance")

    names = _build(gmail).label_names()

    assert names[finance] == "Assistant/Finance"
    assert names["INBOX"] == "INBOX"


def test_another_failure_of_gmail_is_not_hidden_as_a_missing_mail() -> None:
    gmail = FakeGmail()
    mid = gmail.add_mail(("INBOX",))
    gmail.fail_next(403)

    with pytest.raises(HttpError):
        _build(gmail).fetch(mid)
