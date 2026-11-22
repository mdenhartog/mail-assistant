"""U-label-structure-08 on the pipeline: sender-rule filing after the pinned check, before the model (AC-8 to AC-19)."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from app.adapters.gmail_read import FetchedMail
from app.core.alert_state import AlertState
from app.core.judgement import Judgement, JudgingList, ListedCategory, NeedsAttention
from app.core.sender_rules import FilingSource, UrgencyVerdict
from app.usecases.triage import FilingEntry
from category_policy.kinds import Kind
from category_policy.senders import SenderEntry
from tests.fakes.scripted_model import ScriptedModel
from tests.usecases.test_triage import FINANCE_ID, FakeMailbox, FakeStore, NeedsAttentionUrgency, pipeline

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.adapters.judge_anthropic import TrimmedMail

HOUSE_ID = "00000000-0000-0000-0000-0000000000a1"
IMPORTANT_ID = "00000000-0000-0000-0000-0000000000b1"
GOOD = "mx.google.com; spf=pass; dmarc=pass header.from=julianahoeve.nl"
HOUSE = ListedCategory(HOUSE_ID, "Huis", "House", senders=(SenderEntry("julianahoeve.nl"),))
FINANCE = ListedCategory(FINANCE_ID, "Finance", "Bills and invoices")  # no senders
IMPORTANT = ListedCategory(
    IMPORTANT_ID, "Belangrijk", "Important", Kind.EXTRA, senders=(SenderEntry("info@julianahoeve.nl"),)
)
LIST = JudgingList(3, (HOUSE, FINANCE))
WITH_EXTRA = JudgingList(3, (HOUSE, FINANCE, IMPORTANT))
RULE_FILING = FilingEntry(HOUSE_ID, 3, None, FilingSource.SENDER_RULE, "julianahoeve.nl")


class ScriptedJudge:
    """The category call, answered by the scripted model; it always picks Finance."""

    def __init__(self, model: ScriptedModel) -> None:
        self.model = model

    async def judge(
        self, mail: TrimmedMail, categories: Sequence[ListedCategory], instructions: str
    ) -> Judgement | NeedsAttention:
        del categories
        answer = self.model.judge("category", mail.text)
        return Judgement(topic_id=FINANCE_ID, urgent=False, reason="r", summary="s", confidence=answer.confidence)


class ScriptedUrgency:
    """The urgency-only call, answered by the scripted model: confidence 0.5 or more means needs attention."""

    def __init__(self, model: ScriptedModel) -> None:
        self.model = model

    async def needs_attention(self, mail: TrimmedMail) -> UrgencyVerdict:
        answer = self.model.judge("urgency", mail.text)
        return UrgencyVerdict(answer.confidence >= 0.5, "scripted")


def mail(sender: str = "info@julianahoeve.nl", auth: tuple[str, ...] = (GOOD,), **overrides: object) -> FetchedMail:
    base = FetchedMail(
        message_id="m1",
        thread_id="t-m1",
        sender=sender,
        reply_to=None,
        subject="Subject",
        text="hello",
        has_attachment=False,
        headers={},
        auth_results=auth,
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


async def run(fetched: FetchedMail, model: ScriptedModel, current: JudgingList = LIST) -> tuple[FakeMailbox, FakeStore]:
    mailbox, store = FakeMailbox(["m1"]), FakeStore(current=current)
    mailbox.mails["m1"] = fetched
    await pipeline(mailbox, ScriptedJudge(model), store, urgency=ScriptedUrgency(model)).run_once()
    return mailbox, store


async def test_given_a_listed_authenticated_sender_in_an_unticked_category_then_one_urgency_call_only() -> None:
    model = ScriptedModel({"category": 0.9, "urgency": 0.1})

    mailbox, store = await run(mail(), model)

    assert [call.kind for call in model.calls] == ["urgency"]
    assert mailbox.filed == [("m1", "id:Assistant/Huis")]
    outcome = store.outcomes["m1"]
    assert (outcome.urgent, outcome.alert) == (False, None)
    assert outcome.filing == replace(RULE_FILING)


async def test_given_an_unticked_category_and_an_urgent_verdict_then_an_alert_is_raised() -> None:
    model = ScriptedModel({"category": 0.9, "urgency": 0.9})

    _, store = await run(mail(), model)

    assert (store.outcomes["m1"].urgent, store.outcomes["m1"].alert) == (True, AlertState.OPEN)


async def test_given_a_ticked_category_then_no_model_call_at_all() -> None:
    model = ScriptedModel({"category": 0.9, "urgency": 0.9})
    ticked = JudgingList(3, (replace(HOUSE, notify=True), FINANCE))

    mailbox, store = await run(mail(), model, ticked)

    assert model.calls == []
    assert mailbox.filed == [("m1", "id:Assistant/Huis")]
    assert store.outcomes["m1"].filing == RULE_FILING


async def test_given_an_always_attention_urgency_judge_then_a_rule_mail_needs_attention_and_is_not_dropped() -> None:
    mailbox, store = FakeMailbox(["m1"]), FakeStore(current=LIST)
    mailbox.mails["m1"] = mail()
    model = ScriptedModel(0.1)

    await pipeline(mailbox, ScriptedJudge(model), store, urgency=NeedsAttentionUrgency()).run_once()

    assert model.calls == []
    assert (store.outcomes["m1"].urgent, store.outcomes["m1"].alert) == (True, AlertState.OPEN)
    assert store.outcomes["m1"].content.reason.startswith("Needs attention")


async def test_given_a_category_without_senders_then_the_model_judges_the_mail_as_before() -> None:
    model = ScriptedModel(0.9)
    no_rules = JudgingList(3, (replace(HOUSE, senders=()), FINANCE))

    mailbox, store = await run(mail(), model, no_rules)

    assert [call.kind for call in model.calls] == ["category"]
    assert mailbox.filed == [("m1", "id:Assistant/Finance")]
    assert store.outcomes["m1"].filing == FilingEntry(FINANCE_ID, 3, None, FilingSource.MODEL, None)


async def test_given_a_topic_and_an_extra_label_listing_the_sender_then_both_are_filed_without_a_model_category() -> (
    None
):
    model = ScriptedModel({"category": 0.9, "urgency": 0.1})

    mailbox, store = await run(mail(), model, WITH_EXTRA)

    assert [call.kind for call in model.calls] == ["urgency"]
    assert mailbox.filed == [("m1", "id:Assistant/Huis")]
    assert mailbox.extra == [("m1", "id:Assistant/Belangrijk")]
    filing = store.outcomes["m1"].filing
    assert filing == FilingEntry(HOUSE_ID, 3, IMPORTANT_ID, FilingSource.SENDER_RULE, "julianahoeve.nl")


async def test_given_a_refused_extra_label_name_then_the_mail_is_still_filed_under_its_topic_only() -> None:
    model = ScriptedModel({"category": 0.9, "urgency": 0.1})
    odd = replace(IMPORTANT, name="Bad..name")

    mailbox, store = await run(mail(), model, JudgingList(3, (HOUSE, FINANCE, odd)))

    assert mailbox.filed == [("m1", "id:Assistant/Huis")]
    assert mailbox.extra == []
    assert store.outcomes["m1"].filing == RULE_FILING


async def test_given_a_listed_sender_that_is_not_authenticated_then_the_model_judges_and_the_filing_says_why() -> None:
    model = ScriptedModel(0.9)

    mailbox, store = await run(mail(auth=("example.test; dmarc=pass header.from=julianahoeve.nl",)), model)

    assert [call.kind for call in model.calls] == ["category"]
    assert mailbox.filed == [("m1", "id:Assistant/Finance")]
    filing = store.outcomes["m1"].filing
    assert filing == FilingEntry(FINANCE_ID, 3, None, FilingSource.SENDER_RULE_NOT_APPLIED, "julianahoeve.nl")


async def test_given_pinned_mail_from_a_listed_sender_then_pinned_handling_applies_and_no_rule_files_it() -> None:
    model = ScriptedModel(0.9)
    pinned_list = JudgingList(3, (replace(HOUSE, senders=(SenderEntry("mail.example.test"),)), FINANCE))
    auth = ("mx.google.com; spf=pass; dmarc=pass header.from=mail.example.test",)

    mailbox, store = await run(mail("noreply@mail.example.test", auth), model, pinned_list)

    assert model.calls == []
    assert mailbox.filed == []
    assert store.outcomes["m1"].note == "pinned:sign_in_code"
    assert store.outcomes["m1"].filing is None


async def test_given_the_listed_domain_only_in_display_name_reply_to_subject_and_body_then_no_rule_applies() -> None:
    model = ScriptedModel(0.9)
    other = "mx.google.com; spf=pass; dmarc=pass header.from=elsewhere.test"
    lookalike = mail(
        "someone@elsewhere.test",
        (other,),
        reply_to="info@julianahoeve.nl",
        subject="Mail from info@julianahoeve.nl",
        text="From: info@julianahoeve.nl julianahoeve.nl",
        headers={"From": '"info@julianahoeve.nl" <someone@elsewhere.test>', "Reply-To": "info@julianahoeve.nl"},
    )

    mailbox, store = await run(lookalike, model)

    assert [call.kind for call in model.calls] == ["category"]
    assert mailbox.filed == [("m1", "id:Assistant/Finance")]
    assert store.outcomes["m1"].filing == FilingEntry(FINANCE_ID, 3, None, FilingSource.MODEL, None)


async def test_given_no_list_version_then_the_model_path_runs_and_no_filing_is_written() -> None:
    model = ScriptedModel(0.9)

    _, store = await run(mail(), model, JudgingList(0, ()))

    assert store.outcomes["m1"].filing is None
