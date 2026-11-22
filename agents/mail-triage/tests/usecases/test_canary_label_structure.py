"""U-label-structure-14, criterion 3 (AC-60): canary strings in the list and in a From that matches no rule stay out of
the log, the Telegram stub, the Sentry stub and the filing record.

The list itself holds its descriptions, senders and instructions by design (ADR-0043); what must not hold them are the
sinks. The access log belongs to the api (unit 12's canary suite); the audit rows of the list are in the database suite.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.core.judgement import JudgingList, ListedCategory
from app.core.sender_rules import FilingSource
from app.obs.redaction import Redactor, sentry_before_send
from category_policy.senders import SenderEntry
from tests.fakes.fake_telegram import FakeTelegram
from tests.usecases.test_triage import (
    FINANCE_ID,
    MAX_ATTEMPTS,
    FakeJudge,
    FakeMailbox,
    FakeStore,
    fetched,
    judgement,
    pipeline,
)

if TYPE_CHECKING:
    from types import TracebackType

    import pytest

DESCRIPTION = "canary-description-41c7"
LISTED_SENDER = "canary-listed-sender-8d02.nl"
INSTRUCTIONS = "canary-instructions-5be9"
FROM = "canary-from-a3f1@unmatched-canary.nl"
CANARIES = (DESCRIPTION, LISTED_SENDER, INSTRUCTIONS, FROM, "canary-subject-77aa", "canary-body-90bc")
LIST = JudgingList(
    4,
    (ListedCategory(FINANCE_ID, "Finance", DESCRIPTION, senders=(SenderEntry(LISTED_SENDER),)),),
    INSTRUCTIONS,
)


class TelegramNotifier:
    """The failure notice of the runner, on the Telegram stub (``FailureNotice`` words it the same way)."""

    def __init__(self, chat: FakeTelegram) -> None:
        self._chat = chat

    async def notify_failure(self, message_id: str) -> None:
        await self._chat.say(f"I could not process the mail with id {message_id} after several tries.")


class LeakyFailure(Exception):  # noqa: N818 - a stand-in for any error a dependency raises
    """Raised by the judge; its frames hold the mail, the list and the instructions as local variables."""


class FailingJudge(FakeJudge):
    async def judge(self, mail: Any, categories: Any, instructions: str) -> Any:
        held = (mail.text, mail.subject, mail.sender, categories, instructions)  # locals a tracker would capture
        raise LeakyFailure(f"model failed ({len(held)})")


def _sentry_event(error: BaseException, traceback: TracebackType | None) -> dict[str, Any]:
    """What the error tracker builds before ``before_send``: the message and every frame with its local variables."""
    frames = []
    while traceback is not None:
        frames.append({"function": traceback.tb_frame.f_code.co_name, "vars": repr(traceback.tb_frame.f_locals)})
        traceback = traceback.tb_next
    return {
        "exception": {"values": [{"type": type(error).__name__, "value": str(error), "stacktrace": {"frames": frames}}]}
    }


async def test_given_canaries_in_the_list_and_an_unmatched_from_when_mail_is_processed_then_no_sink_holds_them(
    caplog: pytest.LogCaptureFixture,
) -> None:
    mailbox, store, chat = FakeMailbox(["ok"]), FakeStore(current=LIST), FakeTelegram(CANARIES)
    mailbox.mails["bad"] = fetched("bad")
    for message_id in ("ok", "bad"):
        mailbox.mails[message_id] = replace(
            fetched(message_id, text="canary-body-90bc"), sender=FROM, subject="canary-subject-77aa"
        )
    caught: list[dict[str, Any]] = []

    with caplog.at_level(logging.DEBUG):
        await pipeline(mailbox, FakeJudge(judgement()), store).run_once()  # "ok" is filed by the model
        failing = pipeline(mailbox, FailingJudge(), store, notifier=TelegramNotifier(chat))
        for _ in range(MAX_ATTEMPTS):  # "bad" fails until the one notice goes out
            mailbox.ids = ["bad"]
            await failing.run_once()  # the pipeline absorbs the failure
        try:
            await FailingJudge().judge(fetched("bad", "canary-body-90bc"), LIST.categories, INSTRUCTIONS)
        except LeakyFailure as error:
            event = _sentry_event(error, sys.exc_info()[2])
            assert "canary-body-90bc" in json.dumps(event)  # the stub really carries the locals before the hook
            cleaned = sentry_before_send(Redactor([]))(event, {})
            caught.append(cleaned or {})

    sinks = {
        "log": caplog.text,
        "telegram": "\n".join(chat.texts),
        "sentry": json.dumps(caught),
        "filing": repr([outcome.filing for outcome in store.outcomes.values()]),
    }
    assert [(name, c) for name, text in sinks.items() for c in CANARIES if c in text] == []
    assert chat.texts  # the notice was sent, and it holds only the message id
    assert store.outcomes["ok"].filing is not None
    assert store.outcomes["ok"].filing.source is FilingSource.MODEL  # the unmatched From left no entry behind
    assert store.outcomes["ok"].filing.source_ref is None
