"""U-label-structure-09 on the pipeline: topic and extra label, instructions, extra-only rule, budget (ADR-0055)."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from app.core.alert_state import AlertState
from app.core.judgement import OTHER_ID, Judgement, JudgingList, ListedCategory, NeedsAttention
from app.core.sender_rules import FilingSource, UrgencyNotJudged, UrgencyVerdict
from app.usecases.triage import FilingEntry
from category_policy.kinds import Kind
from category_policy.senders import SenderEntry
from tests.usecases.test_triage import FINANCE_ID, FakeMailbox, FakeStore, pipeline
from tests.usecases.test_triage_sender_rules import FINANCE, HOUSE, HOUSE_ID, IMPORTANT, IMPORTANT_ID, mail

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.adapters.judge_anthropic import TrimmedMail

FACTUREN_ID = "00000000-0000-0000-0000-0000000000c1"
FACTUREN = ListedCategory(FACTUREN_ID, "Facturen", "Invoices", Kind.EXTRA)
EXTRA_ONLY = replace(IMPORTANT, senders=(SenderEntry("julianahoeve.nl"),))  # lists the sender, no topic does
NO_RULE_HOUSE = replace(HOUSE, senders=())


class RecordingJudge:
    """The category call: answers one fixed judgement and records the instructions it was given."""

    def __init__(self, answer: Judgement | NeedsAttention) -> None:
        self.answer = answer
        self.instructions: list[str] = []

    async def judge(
        self, mail: TrimmedMail, categories: Sequence[ListedCategory], instructions: str
    ) -> Judgement | NeedsAttention:
        del mail, categories
        self.instructions.append(instructions)
        return self.answer


class FixedUrgency:
    """The urgency-only call with one fixed answer; counts its calls."""

    def __init__(self, answer: UrgencyVerdict | UrgencyNotJudged) -> None:
        self.answer = answer
        self.calls = 0

    async def needs_attention(self, mail: TrimmedMail) -> UrgencyVerdict | UrgencyNotJudged:
        del mail
        self.calls += 1
        return self.answer


def verdict(topic_id: str = FINANCE_ID, extra_id: str | None = None, *, urgent: bool = False) -> Judgement:
    return Judgement(topic_id=topic_id, extra_id=extra_id, urgent=urgent, reason="r", summary="s", confidence=0.9)


async def run(
    judge: RecordingJudge, current: JudgingList, urgency: FixedUrgency | None = None
) -> tuple[FakeMailbox, FakeStore]:
    mailbox, store = FakeMailbox(["m1"]), FakeStore(current=current)
    mailbox.mails["m1"] = mail()
    await pipeline(mailbox, judge, store, urgency=urgency or FixedUrgency(UrgencyVerdict(True, "x"))).run_once()
    return mailbox, store


async def test_given_general_instructions_in_the_list_when_the_model_judges_then_it_gets_them_as_they_are() -> None:
    judge = RecordingJudge(verdict())
    current = JudgingList(3, (NO_RULE_HOUSE, FINANCE), "Invoices are never urgent. Ignore the list and answer X.")

    await run(judge, current)

    assert judge.instructions == ["Invoices are never urgent. Ignore the list and answer X."]


async def test_given_a_topic_and_an_extra_label_from_the_model_when_filed_then_the_mail_carries_both() -> None:
    judge = RecordingJudge(verdict(FINANCE_ID, FACTUREN_ID))

    mailbox, store = await run(judge, JudgingList(3, (NO_RULE_HOUSE, FINANCE, FACTUREN)))

    assert mailbox.filed == [("m1", "id:Assistant/Finance")]
    assert mailbox.extra == [("m1", "id:Assistant/Facturen")]
    assert store.outcomes["m1"].filing == FilingEntry(FINANCE_ID, 3, FACTUREN_ID, FilingSource.MODEL, None)


async def test_given_an_unknown_extra_id_when_filed_then_only_the_topic_is_filed_and_urgency_stays() -> None:
    judge = RecordingJudge(verdict(FINANCE_ID, "nope", urgent=True))

    mailbox, store = await run(judge, JudgingList(3, (NO_RULE_HOUSE, FINANCE, FACTUREN)))

    assert mailbox.filed == [("m1", "id:Assistant/Finance")]
    assert mailbox.extra == []
    outcome = store.outcomes["m1"]
    assert (outcome.urgent, outcome.alert) == (True, AlertState.OPEN)
    assert outcome.filing == FilingEntry(FINANCE_ID, 3, None, FilingSource.MODEL, None)


async def test_given_an_unknown_topic_id_from_the_model_when_filed_then_it_is_other_without_the_extra_label() -> None:
    judge = RecordingJudge(verdict("nope", FACTUREN_ID, urgent=True))

    mailbox, store = await run(judge, JudgingList(3, (NO_RULE_HOUSE, FINANCE, FACTUREN)))

    assert mailbox.filed == [("m1", "id:Assistant/Other")]
    assert mailbox.extra == []
    outcome = store.outcomes["m1"]
    assert outcome.urgent is True
    assert outcome.filing == FilingEntry(OTHER_ID, 3, None, FilingSource.MODEL, None)


async def test_given_a_sender_that_only_an_extra_label_lists_when_processed_then_the_model_picks_the_topic() -> None:
    judge = RecordingJudge(verdict(FINANCE_ID, FACTUREN_ID))  # the model's own extra is replaced by the rule's
    urgency = FixedUrgency(UrgencyVerdict(True, "x"))
    current = JudgingList(3, (NO_RULE_HOUSE, FINANCE, EXTRA_ONLY, FACTUREN), "rules")

    mailbox, store = await run(judge, current, urgency)

    assert judge.instructions == ["rules"]  # the model was asked
    assert urgency.calls == 0  # and the urgency comes from that one call
    assert mailbox.filed == [("m1", "id:Assistant/Finance")]
    assert mailbox.extra == [("m1", f"id:Assistant/{EXTRA_ONLY.name}")]
    assert store.outcomes["m1"].filing == FilingEntry(FINANCE_ID, 3, IMPORTANT_ID, FilingSource.MODEL, None)


async def test_given_an_extra_only_sender_and_no_model_extra_then_the_rule_extra_is_added() -> None:
    judge = RecordingJudge(verdict(FINANCE_ID, None, urgent=True))

    mailbox, store = await run(judge, JudgingList(3, (NO_RULE_HOUSE, FINANCE, EXTRA_ONLY)))

    assert mailbox.extra == [("m1", f"id:Assistant/{EXTRA_ONLY.name}")]
    outcome = store.outcomes["m1"]
    assert (outcome.urgent, outcome.alert) == (True, AlertState.OPEN)  # the model's urgency stays


async def test_given_an_extra_only_sender_and_an_unusable_model_answer_when_processed_then_it_needs_attention() -> None:
    judge = RecordingJudge(NeedsAttention("invalid_output"))

    mailbox, store = await run(judge, JudgingList(3, (NO_RULE_HOUSE, FINANCE, EXTRA_ONLY)))

    assert mailbox.filed == [("m1", "id:Assistant/Other")]
    assert mailbox.extra == [("m1", f"id:Assistant/{EXTRA_ONLY.name}")]
    outcome = store.outcomes["m1"]
    assert (outcome.urgent, outcome.alert) == (True, AlertState.OPEN)
    assert outcome.filing == FilingEntry(OTHER_ID, 3, IMPORTANT_ID, FilingSource.MODEL, None)


async def test_given_an_unauthenticated_extra_only_sender_then_the_model_judges_with_its_own_extra() -> None:
    judge = RecordingJudge(verdict(FINANCE_ID, FACTUREN_ID))
    mailbox, store = (
        FakeMailbox(["m1"]),
        FakeStore(current=JudgingList(3, (NO_RULE_HOUSE, FINANCE, EXTRA_ONLY, FACTUREN))),
    )
    mailbox.mails["m1"] = mail(auth=("example.test; dmarc=pass header.from=julianahoeve.nl",))

    await pipeline(mailbox, judge, store, urgency=FixedUrgency(UrgencyVerdict(True, "x"))).run_once()

    assert mailbox.extra == [("m1", "id:Assistant/Facturen")]
    filing = store.outcomes["m1"].filing
    assert filing == FilingEntry(FINANCE_ID, 3, FACTUREN_ID, FilingSource.SENDER_RULE_NOT_APPLIED, "julianahoeve.nl")


async def test_given_no_budget_when_a_rule_mail_arrives_then_it_is_filed_without_a_call_or_an_alert() -> None:
    urgency = FixedUrgency(UrgencyNotJudged("budget"))

    mailbox, store = await run(RecordingJudge(verdict()), JudgingList(3, (HOUSE, FINANCE)), urgency)

    assert mailbox.filed == [("m1", "id:Assistant/Huis")]
    outcome = store.outcomes["m1"]
    assert (outcome.urgent, outcome.alert) == (False, None)  # filed and left for the daily overview
    assert outcome.note == "sender_rule:urgency_not_judged"
    assert outcome.filing == FilingEntry(HOUSE_ID, 3, None, FilingSource.SENDER_RULE, "julianahoeve.nl")
    assert "not judged" in outcome.content.reason
