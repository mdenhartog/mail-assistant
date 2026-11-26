"""U-mail-categories-22, criterion 3: the Gmail side of the plan build, on the Gmail double.

Only mail of the inbox or under a managed label is offered (spam, trash and archived mail are not), newest
first. A cursor is a message id: a new process (after a crash) continues just after it, with no mail twice and none
missed. A mail that was deleted after it was listed reads as ``None``.
"""

from __future__ import annotations

import pytest
from googleapiclient.errors import HttpError

from app.adapters.gmail_build import IN_SCOPE_QUERY, PAGE_SIZE, GmailBuild, scope_query
from app.core.managed import ManagedLabel, ManagedSet, Role
from tests.fakes.query_gmail import QueryGmail as FakeGmail


def _build(gmail: FakeGmail, *, page_size: int = PAGE_SIZE, managed: list[ManagedLabel] | None = None) -> GmailBuild:
    build = GmailBuild(gmail, sleep=lambda _seconds: None, page_size=page_size)
    build.set_managed(ManagedSet(managed or []))
    return build


def _topic(gmail: FakeGmail, name: str) -> tuple[str, ManagedLabel]:
    label_id = gmail.add_label(name)
    return label_id, ManagedLabel(name, label_id, Role.TOPIC)


def _ids(found: list) -> list[str]:  # type: ignore[type-arg]
    return [c.message_id for c in found]


def test_only_mail_in_the_inbox_or_under_a_managed_label_is_offered_newest_first() -> None:
    gmail = FakeGmail()
    finance, label = _topic(gmail, "Finance")
    archive = gmail.add_label("Archive")
    folder = gmail.add_label("Work")  # a label of the user: never searched
    in_scope_old = gmail.add_mail(("INBOX",))
    labelled = gmail.add_mail((finance,))
    gmail.add_mail((archive,))  # archived: out of scope
    gmail.add_mail((folder,))
    gmail.add_mail(("TRASH",))
    gmail.add_mail(("SPAM",))
    gmail.add_mail(())  # no label at all
    in_scope_new = gmail.add_mail(("INBOX", finance))

    found = _build(gmail, managed=[label]).candidates(None, 100)

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
    finance = gmail.add_label("Finance")
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
    finance = gmail.add_label("Finance")

    names = _build(gmail).label_names()

    assert names[finance] == "Finance"
    assert names["INBOX"] == "INBOX"


def test_another_failure_of_gmail_is_not_hidden_as_a_missing_mail() -> None:
    gmail = FakeGmail()
    mid = gmail.add_mail(("INBOX",))
    gmail.fail_next(403)

    with pytest.raises(HttpError):
        _build(gmail).fetch(mid)


def test_the_search_leaves_out_sent_mail_even_with_an_inbox_or_managed_label() -> None:
    gmail = FakeGmail()
    work, label = _topic(gmail, "Work")
    kept = gmail.add_mail(("INBOX",))
    gmail.add_mail(("INBOX", "SENT"))  # a reply the user sent to themselves
    gmail.add_mail((work, "SENT"))

    assert _ids(_build(gmail, managed=[label]).candidates(None, 100)) == [kept]
    assert _build(gmail, managed=[label]).estimate_in_scope() == 1


def test_given_no_managed_labels_when_listed_then_only_the_inbox_is_searched_and_no_old_prefix_is_in_the_query() -> (
    None
):
    gmail = FakeGmail()
    gmail.add_mail(("INBOX",))

    _build(gmail).candidates(None, 10)

    assert set(gmail.queries) == {IN_SCOPE_QUERY}
    assert "assistant" not in IN_SCOPE_QUERY.casefold()


def test_given_managed_labels_when_listed_then_the_query_names_the_gmail_label_of_each_id_and_not_the_archive() -> None:
    gmail = FakeGmail()
    finance = gmail.add_label("Money/Old name")  # the list renamed it; Gmail still has the old name until the sync
    gmail.add_label("Archive")
    gmail.add_mail(("INBOX",))  # the double only sees the query when a mail is tested against it
    managed = [
        ManagedLabel("Money/New name", finance, Role.TOPIC),
        ManagedLabel("Travel", None, Role.TOPIC),  # no id yet: the list name stands in
        ManagedLabel("Other", None, Role.OTHER),
        ManagedLabel("Archive", "Label_9", Role.ARCHIVE),
    ]

    _build(gmail, managed=managed).candidates(None, 10)

    assert gmail.queries[-1] == '(in:inbox OR label:"Money/Old name" OR label:"Travel" OR label:"Other") -in:sent'


def test_given_a_new_managed_set_when_listed_again_then_the_query_follows_it() -> None:
    gmail = FakeGmail()
    first, label = _topic(gmail, "Bills")
    second = gmail.add_label("Travel")
    mail = gmail.add_mail((second,))
    build = _build(gmail, managed=[label])
    assert build.candidates(None, 10) == []

    build.set_managed(ManagedSet([label, ManagedLabel("Travel", second, Role.TOPIC)]))

    assert _ids(build.candidates(None, 10)) == [mail]
    assert first != second


@pytest.mark.parametrize("name", ['Say "hi"', r"back\slash"])
def test_given_a_name_that_cannot_be_quoted_when_the_query_is_built_then_the_whole_mailbox_is_searched(
    name: str,
) -> None:
    assert scope_query(["Bills", name]) == "-in:sent"  # the use case decides scope again by id


def test_given_very_many_labels_when_the_query_is_built_then_it_stays_short_by_searching_the_whole_mailbox() -> None:
    assert scope_query([f"Category number {number:03d}/" + "x" * 20 for number in range(100)]) == "-in:sent"
