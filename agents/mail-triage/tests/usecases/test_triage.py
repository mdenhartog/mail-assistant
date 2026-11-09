"""U-10: the triage pipeline (spec AC-1, AC-2, AC-3, AC-4, AC-12, AC-26, AC-27, AC-32)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, time

import pytest

from app.adapters.gmail_read import FetchedMail, HistoryExpiredError
from app.adapters.judge_anthropic import ModelUnavailable, TrimmedMail
from app.core.alert_state import AlertState
from app.core.alert_text import AuthResults
from app.core.judgement import Judgement, NeedsAttention
from app.usecases.triage import MAX_ATTEMPTS, Claim, MailContent, Outcome, TriagePipeline, decide_outcome
from schedule_policy.policy import DEFAULT_POLICY
from tests.usecases.fakes_policy import FakePolicySource

DAYTIME = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)  # 13:00 in Amsterdam
NIGHT = datetime(2026, 11, 9, 22, 30, tzinfo=UTC)  # 23:30 in Amsterdam


def fetched(message_id: str, text: str = "hello") -> FetchedMail:
    return FetchedMail(
        message_id=message_id,
        thread_id=f"t-{message_id}",
        sender="a@example.com",
        reply_to=None,
        subject="Subject",
        text=text,
        has_attachment=False,
        headers={},
    )


def judgement(category: str = "Finance", *, urgent: bool = False, confidence: float = 0.9) -> Judgement:
    return Judgement(category=category, urgent=urgent, reason="r", summary="s", confidence=confidence)


class FakeMailbox:
    def __init__(self, ids: list[str], *, list_error: Exception | None = None) -> None:
        self.ids = ids
        self.list_error = list_error
        self.mails = {i: fetched(i) for i in ids}
        self.fetch_errors: dict[str, Exception] = {}
        self.filed: list[tuple[str, str]] = []
        self.calls: list[str] = []

    def list_new(self, history_id: str | None) -> tuple[list[str], str]:
        self.calls.append("list_new")
        if self.list_error is not None:
            raise self.list_error
        if history_id is None:
            return [], "100"
        return list(self.ids), "200"

    def fetch(self, message_id: str) -> FetchedMail:
        self.calls.append("fetch")
        if message_id in self.fetch_errors:
            raise self.fetch_errors[message_id]
        return self.mails[message_id]

    def ensure_label(self, name: str) -> str:
        self.calls.append("ensure_label")
        return f"id:{name}"

    def file(self, message_id: str, label_id: str) -> None:
        self.calls.append("file")
        self.filed.append((message_id, label_id))


class FakeJudge:
    def __init__(self, *answers: Judgement | NeedsAttention | Exception) -> None:
        self.answers = list(answers)
        self.seen: list[TrimmedMail] = []

    async def judge(self, mail: TrimmedMail) -> Judgement | NeedsAttention:
        self.seen.append(mail)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer


@dataclass
class Completed:
    label: str
    urgent: bool
    alert: AlertState | None
    note: str


@dataclass
class FakeStore:
    history: str | None = "100"
    labels: list[str] = field(default_factory=lambda: ["Assistant/Finance", "Assistant/Other"])
    claimed: set[str] = field(default_factory=set)
    done: dict[str, Completed] = field(default_factory=dict)
    outcomes: dict[str, Outcome] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    abandoned: set[str] = field(default_factory=set)

    async def history_id(self) -> str | None:
        return self.history

    async def save_history_id(self, value: str) -> None:
        self.history = value

    async def claim(self, message_id: str, thread_id: str) -> Claim:
        del thread_id
        if message_id in self.done or message_id in self.abandoned:
            return Claim.DONE
        if message_id in self.claimed:
            return Claim.PENDING
        self.claimed.add(message_id)
        return Claim.NEW

    async def known_labels(self) -> list[str]:
        return list(self.labels)

    async def complete(self, message_id: str, outcome: Outcome) -> None:
        self.done[message_id] = Completed(outcome.label, outcome.urgent, outcome.alert, outcome.note)
        self.outcomes[message_id] = outcome
        if outcome.label not in self.labels:
            self.labels.append(outcome.label)

    async def record_failure(self, message_id: str) -> int:
        self.failures[message_id] = self.failures.get(message_id, 0) + 1
        return self.failures[message_id]

    async def abandon(self, message_id: str) -> None:
        self.abandoned.add(message_id)


class FakeNotifier:
    def __init__(self) -> None:
        self.notices: list[str] = []

    async def notify_failure(self, message_id: str) -> None:
        self.notices.append(message_id)


def pipeline(  # noqa: PLR0913, PLR0917 - a test helper that takes every part
    mailbox: FakeMailbox,
    judge: FakeJudge,
    store: FakeStore,
    notifier: FakeNotifier | None = None,
    now: datetime = DAYTIME,
    source: FakePolicySource | None = None,
) -> TriagePipeline:
    return TriagePipeline(
        mailbox, judge, store, notifier or FakeNotifier(), now=lambda: now, policy=source or FakePolicySource()
    )


async def test_given_a_new_non_urgent_mail_when_run_then_it_is_filed_without_alert_or_deletion() -> None:
    mailbox, store = FakeMailbox(["m1"]), FakeStore()

    summary = await pipeline(mailbox, FakeJudge(judgement()), store).run_once()

    assert mailbox.filed == [("m1", "id:Assistant/Finance")]
    assert store.done["m1"] == Completed("Assistant/Finance", False, None, "")
    assert summary.filed == 1
    assert summary.alerts == 0
    assert set(mailbox.calls) <= {"list_new", "fetch", "ensure_label", "file"}  # nothing that could delete


async def test_given_a_new_urgent_mail_outside_quiet_hours_when_run_then_the_alert_is_open() -> None:
    store = FakeStore()

    summary = await pipeline(FakeMailbox(["m1"]), FakeJudge(judgement(urgent=True)), store).run_once()

    assert store.done["m1"].alert is AlertState.OPEN
    assert summary.alerts == 1


async def test_given_a_new_urgent_mail_inside_quiet_hours_when_run_then_it_is_filed_and_held() -> None:
    mailbox, store = FakeMailbox(["m1"]), FakeStore()

    await pipeline(mailbox, FakeJudge(judgement(urgent=True)), store, now=NIGHT).run_once()

    assert mailbox.filed == [("m1", "id:Assistant/Finance")]
    assert store.done["m1"].alert is AlertState.HELD


async def test_given_the_same_mail_seen_twice_when_run_twice_then_it_is_processed_once() -> None:
    mailbox, judge, store = FakeMailbox(["m1"]), FakeJudge(judgement()), FakeStore()
    run = pipeline(mailbox, judge, store)

    await run.run_once()
    await run.run_once()

    assert len(judge.seen) == 1
    assert len(mailbox.filed) == 1


async def test_given_the_model_is_down_when_run_then_nothing_is_lost_and_the_next_run_resumes() -> None:
    mailbox, store = FakeMailbox(["m1", "m2"]), FakeStore()
    down = FakeJudge(ModelUnavailable("down"))

    first = await pipeline(mailbox, down, store).run_once()

    assert first.model_down is True
    assert store.history == "100"  # not advanced: the mails are listed again
    assert mailbox.filed == []
    assert store.failures == {}  # an outage is not the mail's fault

    second = await pipeline(mailbox, FakeJudge(judgement()), store).run_once()

    assert [m for m, _ in mailbox.filed] == ["m1", "m2"]
    assert store.history == "200"
    assert second.filed == 2


async def test_given_gmail_is_down_when_run_then_the_position_is_kept() -> None:
    mailbox = FakeMailbox(["m1"], list_error=ConnectionError("down"))
    store = FakeStore()

    summary = await pipeline(mailbox, FakeJudge(judgement()), store).run_once()

    assert summary.listing_failed is True
    assert store.history == "100"


async def test_given_no_stored_position_when_run_then_it_starts_from_now_and_processes_nothing_old() -> None:
    mailbox, judge, store = FakeMailbox(["old"]), FakeJudge(judgement()), FakeStore(history=None)

    await pipeline(mailbox, judge, store).run_once()

    assert store.history == "100"
    assert judge.seen == []


async def test_given_the_stored_position_expired_when_run_then_it_starts_again_from_now() -> None:
    mailbox = FakeMailbox(["m1"])
    original = mailbox.list_new
    calls = {"n": 0}

    def flaky(history_id: str | None) -> tuple[list[str], str]:
        calls["n"] += 1
        if history_id is not None:
            raise HistoryExpiredError
        return original(None)

    mailbox.list_new = flaky  # type: ignore[method-assign]
    store = FakeStore(history="1")

    summary = await pipeline(mailbox, FakeJudge(judgement()), store).run_once()

    assert store.history == "100"
    assert summary.filed == 0


async def test_given_a_mail_that_keeps_failing_when_run_then_others_continue_and_one_notice_is_requested() -> None:
    mailbox, store, notifier = FakeMailbox(["bad", "good"]), FakeStore(), FakeNotifier()
    mailbox.fetch_errors["bad"] = ValueError("boom")
    run = pipeline(mailbox, FakeJudge(judgement()), store, notifier)

    for _ in range(MAX_ATTEMPTS + 2):
        await run.run_once()

    assert "good" in store.done
    assert "bad" not in store.done
    assert "bad" in store.abandoned
    assert notifier.notices == ["bad"]  # exactly one notice, however many runs follow
    assert store.history == "200"  # given up on, so the position moves on


async def test_given_a_failing_mail_before_the_limit_when_run_then_the_position_is_kept_for_a_retry() -> None:
    mailbox, store = FakeMailbox(["bad"]), FakeStore()
    mailbox.fetch_errors["bad"] = ValueError("boom")

    summary = await pipeline(mailbox, FakeJudge(judgement()), store).run_once()

    assert summary.retry_later == 1
    assert store.history == "100"
    assert store.failures == {"bad": 1}


async def test_given_the_budget_is_used_up_when_a_mail_arrives_then_it_is_still_filed_and_needs_attention() -> None:
    mailbox, store = FakeMailbox(["m1"]), FakeStore()

    await pipeline(mailbox, FakeJudge(NeedsAttention("budget")), store).run_once()

    assert mailbox.filed == [("m1", "id:Assistant/Other")]
    assert store.done["m1"] == Completed("Assistant/Other", True, AlertState.OPEN, "needs_attention:budget")


async def test_given_unusable_model_output_when_run_then_the_mail_needs_attention_not_silence() -> None:
    store = FakeStore()

    await pipeline(FakeMailbox(["m1"]), FakeJudge(NeedsAttention("invalid_output")), store, now=NIGHT).run_once()

    assert store.done["m1"].urgent is True
    assert store.done["m1"].alert is AlertState.HELD


async def test_given_low_confidence_when_run_then_the_mail_needs_attention() -> None:
    store = FakeStore()

    await pipeline(FakeMailbox(["m1"]), FakeJudge(judgement(confidence=0.2)), store).run_once()

    assert store.done["m1"].alert is AlertState.OPEN
    assert store.done["m1"].note == "needs_attention:low_confidence"


async def test_given_a_new_category_when_run_then_the_label_is_created_and_remembered() -> None:
    mailbox, store = FakeMailbox(["m1", "m2"]), FakeStore()

    await pipeline(mailbox, FakeJudge(judgement("Travel")), store).run_once()

    assert [label for _, label in mailbox.filed] == ["id:Assistant/Travel", "id:Assistant/Travel"]
    assert "Assistant/Travel" in store.labels


async def test_given_a_mail_claimed_but_never_completed_when_run_then_it_is_processed_again() -> None:
    mailbox, store = FakeMailbox(["m1"]), FakeStore()
    store.claimed.add("m1")  # a crash happened after the claim

    await pipeline(mailbox, FakeJudge(judgement()), store).run_once()

    assert "m1" in store.done


async def test_given_a_very_long_body_when_run_then_the_model_sees_only_the_trimmed_text() -> None:
    mailbox, judge = FakeMailbox(["m1"]), FakeJudge(judgement())
    mailbox.mails["m1"] = fetched("m1", text="x" * 100_000)

    await pipeline(mailbox, judge, FakeStore()).run_once()

    assert judge.seen[0].truncated is True
    assert len(judge.seen[0].text) < 100_000


@pytest.mark.parametrize("count", [0])
async def test_given_nothing_new_when_run_then_nothing_happens(count: int) -> None:
    mailbox = FakeMailbox([])
    store = FakeStore()

    summary = await pipeline(mailbox, FakeJudge(judgement()), store).run_once()

    assert summary.filed == count
    assert store.history == "200"


async def test_given_a_judged_mail_when_completed_then_the_store_gets_the_capped_content_for_alerts() -> None:
    mailbox, store = FakeMailbox(["m1"]), FakeStore()
    mailbox.mails["m1"] = FetchedMail(
        message_id="m1",
        thread_id="t-m1",
        sender="boss@example.com",
        reply_to="other@example.net",
        subject="Budget",
        text="body that must not be stored",
        has_attachment=True,
        headers={"Authentication-Results": "mx; spf=fail; dkim=pass; dmarc=pass"},
    )
    verdict = Judgement(category="Finance", urgent=True, reason="Due Friday", summary="Pay it", confidence=0.9)

    await pipeline(mailbox, FakeJudge(verdict), store).run_once()

    assert store.outcomes["m1"].content == MailContent(
        sender="boss@example.com",
        subject="Budget",
        reply_to="other@example.net",
        has_attachment=True,
        reason="Due Friday",
        summary="Pay it",
        auth=AuthResults(spf="fail", dkim="pass", dmarc="pass"),
    )
    assert "body that must not be stored" not in str(store.outcomes["m1"])


async def test_given_a_needs_attention_mail_when_completed_then_the_content_has_no_model_text() -> None:
    store = FakeStore()

    await pipeline(FakeMailbox(["m1"]), FakeJudge(NeedsAttention("budget")), store).run_once()

    content = store.outcomes["m1"].content
    assert content.reason == "Needs attention: budget"
    assert content.summary == ""


# ---- U-backlog-05: the decision step is shared with the catch-up (INT-003) ------------------------------------------


def test_given_an_urgent_judgement_when_decided_directly_then_it_is_filed_urgent_with_an_open_alert() -> None:
    verdict = judgement("Finance", urgent=True, confidence=0.9)

    outcome = decide_outcome(verdict, fetched("m1"), ["Assistant/Finance"], DAYTIME, DEFAULT_POLICY)

    assert outcome.label == "Assistant/Finance"
    assert outcome.urgent is True
    assert outcome.alert is AlertState.OPEN
    assert outcome.confidence == 0.9
    assert outcome.content.subject == "Subject"
    assert outcome.content.reason == "r"
    assert outcome.content.summary == "s"


def test_given_an_urgent_judgement_in_quiet_hours_when_decided_directly_then_the_alert_is_held() -> None:
    outcome = decide_outcome(judgement(urgent=True), fetched("m1"), [], NIGHT, DEFAULT_POLICY)

    assert outcome.alert is AlertState.HELD
    assert outcome.release_at == datetime(2026, 11, 10, 6, 0, tzinfo=UTC)  # 07:00 in Amsterdam


def test_given_a_needs_attention_verdict_when_decided_directly_then_it_is_other_urgent_with_a_note() -> None:
    outcome = decide_outcome(NeedsAttention("invalid_output"), fetched("m1"), [], DAYTIME, DEFAULT_POLICY)

    assert outcome.label == "Assistant/Other"
    assert outcome.urgent is True
    assert outcome.confidence is None
    assert outcome.note == "needs_attention:invalid_output"
    assert outcome.content.reason == "Needs attention: invalid_output"
    assert outcome.content.summary == ""
    assert outcome.release_at is None


# ---- U-quiet-hours-12: the alert is judged with the policy snapshot of that moment (AC-22, AC-23) -------------------

NEW_YORK = replace(DEFAULT_POLICY, zone="America/New_York")
NEW_YORK_NIGHT = datetime(2026, 11, 10, 4, 30, tzinfo=UTC)  # 23:30 on 9 November in New York (UTC-5)


def test_given_new_york_when_an_urgent_mail_arrives_at_2330_there_then_the_alert_is_held_until_0700() -> None:
    outcome = decide_outcome(judgement(urgent=True), fetched("m1"), [], NEW_YORK_NIGHT, NEW_YORK)

    assert outcome.alert is AlertState.HELD
    assert outcome.release_at == datetime(2026, 11, 10, 12, 0, tzinfo=UTC)  # 07:00 in New York


def test_given_a_needs_attention_verdict_in_quiet_hours_when_decided_then_it_is_held_with_a_release_moment() -> None:
    outcome = decide_outcome(NeedsAttention("budget"), fetched("m1"), [], NIGHT, DEFAULT_POLICY)

    assert outcome.alert is AlertState.HELD
    assert outcome.release_at == datetime(2026, 11, 10, 6, 0, tzinfo=UTC)


def test_given_a_non_urgent_mail_in_quiet_hours_when_decided_then_there_is_no_alert_and_no_release_moment() -> None:
    outcome = decide_outcome(judgement(urgent=False), fetched("m1"), [], NIGHT, DEFAULT_POLICY)

    assert (outcome.alert, outcome.release_at) == (None, None)


async def test_given_a_stored_change_when_the_next_alert_arises_then_it_is_judged_with_the_new_values() -> None:
    source = FakePolicySource(DEFAULT_POLICY)  # 13:00 in Amsterdam: not quiet
    first_store = FakeStore()
    await pipeline(FakeMailbox(["m1"]), FakeJudge(judgement(urgent=True)), first_store, source=source).run_once()
    source.set(replace(DEFAULT_POLICY, quiet_start=time(12, 0), quiet_end=time(14, 0)))  # 13:00 is now quiet
    second_store = FakeStore()

    await pipeline(FakeMailbox(["m2"]), FakeJudge(judgement(urgent=True)), second_store, source=source).run_once()

    assert first_store.outcomes["m1"].alert is AlertState.OPEN
    assert second_store.outcomes["m2"].alert is AlertState.HELD
    assert second_store.outcomes["m2"].release_at == datetime(2026, 11, 9, 13, 0, tzinfo=UTC)  # 14:00 Amsterdam


async def test_given_a_source_that_changes_on_its_second_call_when_one_mail_is_triaged_then_it_is_asked_once() -> None:
    always_quiet = replace(DEFAULT_POLICY, quiet_start=time(12, 0), quiet_end=time(14, 0))
    source = FakePolicySource(always_quiet, DEFAULT_POLICY)
    store = FakeStore()

    await pipeline(FakeMailbox(["m1"]), FakeJudge(judgement(urgent=True)), store, source=source).run_once()

    assert source.calls == 1
    assert store.outcomes["m1"].alert is AlertState.HELD
    assert store.outcomes["m1"].release_at == datetime(2026, 11, 9, 13, 0, tzinfo=UTC)
