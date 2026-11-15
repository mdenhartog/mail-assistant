"""U-mail-categories-05, criteria 2 to 6 on the pipeline (AC-6, AC-7, AC-38, AC-39, MC-1, MC-19)."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import TYPE_CHECKING

import pytest

from app.core.alert_state import AlertState
from app.core.judgement import (
    OTHER_ID,
    OTHER_LABEL,
    Judgement,
    JudgementError,
    JudgingList,
    ListedCategory,
    NeedsAttention,
    parse_judgement,
)
from app.usecases.triage import FilingEntry, Outcome
from tests.fakes.stub_model import HOSTILE_CORPUS, StubModel
from tests.usecases.test_triage import (
    CURRENT,
    FINANCE_ID,
    FakeJudge,
    FakeMailbox,
    FakeStore,
    fetched,
    pipeline,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.adapters.judge_anthropic import TrimmedMail

GOOD_AUTH = "mx.google.com; spf=pass; dmarc=pass (p=REJECT) header.from=accounts.google.com"
FORGED_AUTH = "mx.google.com; dmarc=pass header.from=accounts.google.com"
FAILED_AUTH = "mx.google.com; dmarc=fail header.from=accounts.google.com"


class RecordingMailbox(FakeMailbox):
    def __init__(self, ids: list[str]) -> None:
        super().__init__(ids)
        self.ensured: list[str] = []

    def ensure_label(self, name: str) -> str:
        self.ensured.append(name)
        return super().ensure_label(name)


@dataclass
class RecordingStore(FakeStore):
    """Remembers which store methods the pipeline used, to prove nothing but the filing is written."""

    used: list[str] = field(default_factory=list)

    async def complete(self, message_id: str, outcome: Outcome) -> None:
        self.used.append("complete")
        await super().complete(message_id, outcome)

    async def record_failure(self, message_id: str) -> int:
        self.used.append("record_failure")
        return await super().record_failure(message_id)

    async def abandon(self, message_id: str) -> None:
        self.used.append("abandon")
        await super().abandon(message_id)


class StubModelJudge:
    """Wraps the stub model: every answer is put in the category-id slot of an otherwise valid answer."""

    def __init__(self, model: StubModel, *, urgent: bool = False) -> None:
        self._model = model
        self._urgent = urgent
        self.calls = 0

    async def judge(self, mail: TrimmedMail, categories: Sequence[ListedCategory]) -> Judgement | NeedsAttention:
        del categories
        self.calls += 1
        answer = self._model.answer(mail.text)
        try:
            return parse_judgement(
                {"category_id": answer, "urgent": self._urgent, "reason": "r", "summary": "s", "confidence": 0.9}
            )
        except JudgementError:
            return NeedsAttention("invalid_output")


def inbox_mail(
    mailbox: FakeMailbox, message_id: str, *, sender: str = "a@example.com", auth: tuple[str, ...] = ()
) -> None:
    mailbox.mails[message_id] = replace(fetched(message_id), sender=sender, auth_results=auth)


async def test_given_the_hostile_corpus_when_processed_then_every_mail_goes_to_other_with_no_extra_call_or_write() -> (
    None
):
    ids = [f"m{n}" for n in range(len(HOSTILE_CORPUS))]
    mailbox, store = RecordingMailbox(ids), RecordingStore()

    summary = await pipeline(mailbox, StubModelJudge(StubModel.hostile()), store).run_once()  # type: ignore[arg-type]

    assert summary.filed == len(ids)
    assert mailbox.ensured == [OTHER_LABEL] * len(ids)  # no label of any other name is ever created
    assert [label for _, label in mailbox.filed] == [f"id:{OTHER_LABEL}"] * len(ids)
    assert set(mailbox.calls) == {"list_new", "fetch", "ensure_label", "file"}
    assert mailbox.calls.count("file") == len(ids)  # exactly one Gmail change per mail
    assert store.used == ["complete"] * len(ids)  # nothing is written but the outcome with its filing
    assert all(o.filing == FilingEntry(OTHER_ID, 3) for o in store.outcomes.values())


async def test_given_an_urgent_mail_with_an_unknown_id_when_processed_then_it_goes_to_other_and_still_alerts() -> None:
    store = FakeStore()
    judge = StubModelJudge(StubModel(["cat-9999"]), urgent=True)

    await pipeline(FakeMailbox(["m1"]), judge, store).run_once()  # type: ignore[arg-type]

    assert store.outcomes["m1"].label == OTHER_LABEL
    assert store.outcomes["m1"].urgent is True
    assert store.outcomes["m1"].alert is AlertState.OPEN


async def test_given_a_list_with_other_everything_when_an_urgent_mail_arrives_then_it_still_alerts() -> None:
    everything = JudgingList(4, (ListedCategory(FINANCE_ID, "Misc", "Other: everything, never urgent"),))
    store = FakeStore(current=everything)

    await pipeline(
        FakeMailbox(["m1"]),
        FakeJudge(Judgement(category_id=FINANCE_ID, urgent=True, reason="r", summary="s", confidence=0.9)),
        store,
    ).run_once()

    assert store.outcomes["m1"].alert is AlertState.OPEN


async def test_given_pinned_google_security_mail_when_processed_then_it_stays_and_raises_an_urgent_alert() -> None:
    mailbox, store = RecordingMailbox(["m1"]), FakeStore()
    inbox_mail(mailbox, "m1", sender="no-reply@accounts.google.com", auth=(GOOD_AUTH,))
    judge = FakeJudge(Judgement(category_id=FINANCE_ID, urgent=False, reason="r", summary="s", confidence=0.9))

    summary = await pipeline(mailbox, judge, store).run_once()

    assert mailbox.filed == []
    assert mailbox.ensured == []  # not even a label is looked up
    assert judge.seen == []  # the model never decides about pinned mail
    outcome = store.outcomes["m1"]
    assert (outcome.label, outcome.filing, outcome.urgent, outcome.alert) == (None, None, True, AlertState.OPEN)
    assert outcome.note == "pinned:google_security"
    assert outcome.content.sender == "no-reply@accounts.google.com"
    assert outcome.content.auth.dmarc == "pass"
    assert "m1" in store.done  # settled, so it is not read again
    assert (summary.filed, summary.alerts) == (0, 1)


async def test_given_pinned_google_security_mail_in_quiet_hours_when_processed_then_the_alert_is_held() -> None:
    mailbox, store = RecordingMailbox(["m1"]), FakeStore()
    inbox_mail(mailbox, "m1", sender="no-reply@accounts.google.com", auth=(GOOD_AUTH,))

    await pipeline(mailbox, FakeJudge(None), store, now=NIGHT).run_once()  # type: ignore[arg-type]

    assert store.outcomes["m1"].alert is AlertState.HELD
    assert store.outcomes["m1"].release_at is not None


async def test_given_pinned_google_security_mail_with_a_forged_lower_header_when_processed_then_the_text_uses_the_top() -> (
    None
):
    mailbox, store = RecordingMailbox(["m1"]), FakeStore()
    lower = "mx.google.com; spf=fail; dkim=fail; dmarc=fail header.from=accounts.google.com"
    inbox_mail(mailbox, "m1", sender="no-reply@accounts.google.com", auth=(GOOD_AUTH, lower))

    await pipeline(mailbox, FakeJudge(None), store).run_once()  # type: ignore[arg-type]

    auth = store.outcomes["m1"].content.auth
    assert (auth.spf, auth.dmarc) == ("pass", "pass")


async def test_given_pinned_sign_in_code_mail_when_processed_then_it_stays_with_no_alert_and_no_text_kept() -> None:
    mailbox, store = RecordingMailbox(["m1"]), FakeStore()
    inbox_mail(mailbox, "m1", sender="login@mail.example.test", auth=("mx.google.com; dmarc=pass header.from=mail.example.test",))
    mailbox.mails["m1"] = replace(mailbox.mails["m1"], subject="Your code is 123456", text="123456")
    judge = FakeJudge(Judgement(category_id=FINANCE_ID, urgent=True, reason="r", summary="s", confidence=0.9))

    summary = await pipeline(mailbox, judge, store).run_once()

    assert mailbox.filed == []
    assert judge.seen == []
    outcome = store.outcomes["m1"]
    assert (outcome.label, outcome.filing, outcome.urgent, outcome.alert) == (None, None, False, None)
    assert outcome.note == "pinned:sign_in_code"
    assert "123456" not in repr(outcome)  # the one-time code never reaches the store, so never Telegram
    assert (summary.filed, summary.alerts) == (0, 0)


@pytest.mark.parametrize(
    ("sender", "auth"),
    [
        ("no-reply@accounts.google.com", (FAILED_AUTH, FORGED_AUTH)),  # a forged header lower in the mail
        ("no-reply@accounts.google.com", ()),
        ("no-reply@evil.example", (GOOD_AUTH,)),  # header.from differs from the From domain
    ],
)
async def test_given_mail_that_is_not_proven_when_processed_then_it_is_judged_and_filed_as_usual(
    sender: str, auth: tuple[str, ...]
) -> None:
    mailbox, store = RecordingMailbox(["m1"]), FakeStore()
    inbox_mail(mailbox, "m1", sender=sender, auth=auth)
    judge = FakeJudge(Judgement(category_id=FINANCE_ID, urgent=False, reason="r", summary="s", confidence=0.9))

    await pipeline(mailbox, judge, store).run_once()

    assert len(judge.seen) == 1
    assert mailbox.filed == [("m1", "id:Assistant/Finance")]
    assert store.outcomes["m1"].filing == FilingEntry(FINANCE_ID, 3)


async def test_given_a_filed_mail_then_the_list_version_is_recorded_without_sender_or_subject() -> None:
    store, judge, mailbox = (
        FakeStore(),
        FakeJudge(Judgement(category_id=FINANCE_ID, urgent=False, reason="r", summary="s", confidence=0.9)),
        FakeMailbox(["m1"]),
    )

    await pipeline(mailbox, judge, store).run_once()

    entry = store.outcomes["m1"].filing
    assert entry == FilingEntry(category_id=FINANCE_ID, list_version=CURRENT.version)
    assert {f.name for f in fields(FilingEntry)} == {"category_id", "list_version"}


async def test_given_no_list_version_yet_when_processed_then_the_mail_goes_to_other_without_a_filing_row() -> None:
    store = FakeStore(current=JudgingList(0, ()))

    await pipeline(
        FakeMailbox(["m1"]),
        FakeJudge(Judgement(category_id=FINANCE_ID, urgent=False, reason="r", summary="s", confidence=0.9)),
        store,
    ).run_once()

    assert store.outcomes["m1"].label == OTHER_LABEL
    assert store.outcomes["m1"].filing is None


async def test_given_several_mails_when_processed_then_each_gets_its_own_call_with_the_same_list_snapshot() -> None:
    mailbox, store = FakeMailbox(["m1", "m2", "m3"]), FakeStore()
    judge = FakeJudge(Judgement(category_id=FINANCE_ID, urgent=False, reason="r", summary="s", confidence=0.9))

    await pipeline(mailbox, judge, store).run_once()

    assert len(judge.seen) == 3
    assert judge.lists == [CURRENT.categories] * 3
