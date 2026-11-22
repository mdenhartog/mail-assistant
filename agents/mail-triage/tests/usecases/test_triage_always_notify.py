"""U-label-structure-10 on the pipeline: the always-notify alert decision (ADR-0057; AC-20 to AC-28)."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from app.core.alert_decision import AlertCause, CauseKind
from app.core.alert_state import AlertState
from app.core.judgement import Judgement, JudgingList, ListedCategory
from app.usecases.triage import decide_outcome
from category_policy.senders import SenderEntry
from schedule_policy.policy import DEFAULT_POLICY
from tests.fakes.scripted_model import ScriptedModel
from tests.usecases.test_triage import DAYTIME, FINANCE_ID, NIGHT, FakeJudge, FakeMailbox, FakeStore, pipeline
from tests.usecases.test_triage_sender_rules import (
    GOOD,
    HOUSE,
    IMPORTANT,
    ScriptedJudge,
    ScriptedUrgency,
    mail,
)

if TYPE_CHECKING:
    from datetime import datetime

    from app.adapters.gmail_read import FetchedMail

FINANCE_TICKED = ListedCategory(FINANCE_ID, "Finance", "Bills and invoices", notify=True)
FINANCE_PLAIN = replace(FINANCE_TICKED, notify=False)


def judged(*, urgent: bool = False) -> Judgement:
    return Judgement(topic_id=FINANCE_ID, urgent=urgent, reason="r", summary="s", confidence=0.9)


async def run_model(
    fetched: FetchedMail, current: JudgingList, verdict: Judgement, now: datetime = DAYTIME
) -> tuple[FakeMailbox, FakeStore]:
    mailbox, store = FakeMailbox(["m1"]), FakeStore(current=current)
    mailbox.mails["m1"] = fetched
    await pipeline(mailbox, FakeJudge(verdict), store, now=now).run_once()
    return mailbox, store


def causes(store: FakeStore) -> tuple[AlertCause, ...]:
    return store.outcomes["m1"].causes


async def test_given_a_non_urgent_mail_filed_by_the_model_in_a_ticked_category_then_one_always_notify_alert() -> None:
    _, store = await run_model(mail("a@example.com", auth=()), JudgingList(3, (FINANCE_TICKED,)), judged())

    outcome = store.outcomes["m1"]
    assert (outcome.urgent, outcome.alert) == (False, AlertState.OPEN)
    assert causes(store) == (AlertCause(CauseKind.ALWAYS_NOTIFY, "Finance"),)
    assert outcome.content.verified_domain is None  # the sender is not authenticated: the alert will say so


async def test_given_a_ticked_category_in_quiet_hours_then_the_alert_is_held_until_the_quiet_end() -> None:
    _, store = await run_model(mail("a@example.com", auth=()), JudgingList(3, (FINANCE_TICKED,)), judged(), NIGHT)

    outcome = store.outcomes["m1"]
    assert outcome.alert is AlertState.HELD
    assert outcome.release_at is not None
    assert outcome.release_at > NIGHT


async def test_given_a_sender_rule_mail_in_a_ticked_category_then_the_alert_carries_the_verified_domain() -> None:
    model = ScriptedModel({"category": 0.9, "urgency": 0.9})
    ticked = JudgingList(3, (replace(HOUSE, notify=True), FINANCE_PLAIN))
    mailbox, store = FakeMailbox(["m1"]), FakeStore(current=ticked)
    mailbox.mails["m1"] = mail()
    await pipeline(mailbox, ScriptedJudge(model), store, urgency=ScriptedUrgency(model)).run_once()

    outcome = store.outcomes["m1"]
    assert outcome.alert is AlertState.OPEN
    assert causes(store) == (AlertCause(CauseKind.ALWAYS_NOTIFY, "Huis"),)
    assert outcome.content.verified_domain == "julianahoeve.nl"
    assert outcome.filing is not None
    assert outcome.filing.source.value == "sender_rule"
    assert outcome.content.summary == ""  # the model never read it


async def test_given_an_urgent_mail_in_a_ticked_category_then_exactly_one_alert_names_both_causes() -> None:
    _, store = await run_model(mail("a@example.com", auth=()), JudgingList(3, (FINANCE_TICKED,)), judged(urgent=True))

    assert store.outcomes["m1"].alert is AlertState.OPEN
    assert causes(store) == (AlertCause(CauseKind.URGENT), AlertCause(CauseKind.ALWAYS_NOTIFY, "Finance"))
    assert len(store.outcomes) == 1


async def test_given_a_topic_and_an_extra_label_that_are_both_ticked_then_one_alert_names_both() -> None:
    important = replace(IMPORTANT, notify=True, senders=(SenderEntry("info@julianahoeve.nl"),))
    current = JudgingList(3, (replace(HOUSE, senders=()), FINANCE_TICKED, important))

    _, store = await run_model(mail(), current, judged())

    assert store.outcomes["m1"].filing is not None
    assert store.outcomes["m1"].filing.extra_id == important.category_id  # type: ignore[union-attr]
    assert causes(store) == (
        AlertCause(CauseKind.ALWAYS_NOTIFY, "Finance"),
        AlertCause(CauseKind.ALWAYS_NOTIFY, "Belangrijk"),
    )
    assert store.outcomes["m1"].content.verified_domain == "julianahoeve.nl"


async def test_given_only_the_extra_label_is_ticked_then_the_alert_names_the_extra_label() -> None:
    important = replace(IMPORTANT, notify=True, senders=(SenderEntry("info@julianahoeve.nl"),))
    current = JudgingList(3, (replace(HOUSE, senders=()), FINANCE_PLAIN, important))

    _, store = await run_model(mail(), current, judged())

    assert causes(store) == (AlertCause(CauseKind.ALWAYS_NOTIFY, "Belangrijk"),)


async def test_given_an_unticked_category_then_only_an_urgent_mail_has_an_alert() -> None:
    current = JudgingList(3, (FINANCE_PLAIN,))

    _, quiet = await run_model(mail("a@example.com", auth=()), current, judged())
    _, urgent = await run_model(mail("a@example.com", auth=()), current, judged(urgent=True))

    assert (quiet.outcomes["m1"].alert, causes(quiet)) == (None, ())
    assert urgent.outcomes["m1"].alert is AlertState.OPEN
    assert causes(urgent) == (AlertCause(CauseKind.URGENT),)


async def test_given_an_unticked_rule_mail_the_urgency_verdict_is_the_only_cause() -> None:
    model = ScriptedModel({"category": 0.9, "urgency": 0.9})
    mailbox, store = FakeMailbox(["m1"]), FakeStore(current=JudgingList(3, (HOUSE, FINANCE_PLAIN)))
    mailbox.mails["m1"] = mail()
    await pipeline(mailbox, ScriptedJudge(model), store, urgency=ScriptedUrgency(model)).run_once()

    assert causes(store) == (AlertCause(CauseKind.URGENT),)


async def test_given_a_mail_of_the_backlog_in_a_ticked_category_then_decide_outcome_raises_no_alert() -> None:
    """The catch-up decides with ``decide_outcome`` alone: a tick never creates an alert there (ADR-0057 d5)."""
    fetched = mail("a@example.com", auth=())
    current = JudgingList(3, (FINANCE_TICKED,))

    outcome = decide_outcome(judged(), fetched, current, DAYTIME, DEFAULT_POLICY)

    assert (outcome.alert, outcome.causes) == (None, ())


async def test_given_a_missing_from_then_the_content_is_not_verified() -> None:
    _, store = await run_model(mail("", auth=(GOOD,)), JudgingList(3, (FINANCE_TICKED,)), judged())

    assert store.outcomes["m1"].content.verified_domain is None
    assert store.outcomes["m1"].alert is AlertState.OPEN


async def test_given_the_pipeline_is_run_twice_over_the_same_mail_then_it_is_filed_once() -> None:
    mailbox, store = FakeMailbox(["m1"]), FakeStore(current=JudgingList(3, (FINANCE_TICKED,)))
    mailbox.mails["m1"] = mail("a@example.com", auth=())

    await pipeline(mailbox, FakeJudge(judged()), store).run_once()
    await pipeline(mailbox, FakeJudge(judged()), store).run_once()

    assert len(mailbox.filed) == 1
