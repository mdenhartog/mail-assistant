"""U-16: the daily overview (spec AC-31)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.core.alert_text import MAX_MESSAGE_CHARS
from app.core.time_policy import in_quiet_hours, overview_on
from app.usecases.overview import SUBJECT_CHARS, FiledMail, OverviewService, build_overview
from schedule_policy.policy import DEFAULT_POLICY, validate
from schedule_policy.testing import make_policy

if TYPE_CHECKING:
    from app.core.alert_text import AlertMessage
    from schedule_policy.policy import TimePolicy

BEFORE = datetime(2026, 11, 9, 16, 59, tzinfo=UTC)  # 17:59 in Amsterdam
AFTER = datetime(2026, 11, 9, 17, 1, tzinfo=UTC)  # 18:01 in Amsterdam
NEXT_MORNING = datetime(2026, 11, 10, 6, 30, tzinfo=UTC)  # 07:30 in Amsterdam
TODAY = date(2026, 11, 9)
FAR_FUTURE = datetime(9999, 1, 1, tzinfo=UTC)


def filed(label: str, confidence: float = 0.9, sender: str = "a@example.com", subject: str = "Hi") -> FiledMail:
    return FiledMail(label=label, confidence=confidence, sender=sender, subject=subject)


@dataclass
class FakeStore:
    """The filed mails and the overview log in one fake; ``timed`` holds mails with the moment they were filed."""

    mails: list[FiledMail] = field(default_factory=list)
    sent_days: dict[date, datetime] = field(default_factory=dict)
    asked_since: list[datetime] = field(default_factory=list)
    timed: list[tuple[datetime, FiledMail]] = field(default_factory=list)
    now: datetime = FAR_FUTURE  # a mail filed after this moment does not exist yet

    async def filed_without_alert_since(self, since: datetime) -> list[FiledMail]:
        self.asked_since.append(since)
        return [*self.mails, *(mail for filed_at, mail in self.timed if since <= filed_at <= self.now)]

    async def overview_sent(self, day: date) -> bool:
        return day in self.sent_days

    async def mark_overview_sent(self, day: date, settled_at: datetime) -> None:
        self.sent_days.setdefault(day, settled_at)

    async def last_settled_at(self) -> datetime | None:
        return max(self.sent_days.values(), default=None)


class FakePolicies:
    """A PolicySource that hands out the policy it holds now and counts the reads."""

    def __init__(self, policy: TimePolicy = DEFAULT_POLICY) -> None:
        self.policy = policy
        self.reads = 0

    async def current(self) -> TimePolicy:
        self.reads += 1
        return self.policy


class FakeOutbox:
    def __init__(self) -> None:
        self.messages: list[AlertMessage] = []

    async def send(self, message: AlertMessage) -> int:
        self.messages.append(message)
        return len(self.messages)


def service(
    store: FakeStore, outbox: FakeOutbox, now: datetime, policy: TimePolicy = DEFAULT_POLICY
) -> OverviewService:
    return OverviewService(store, store, outbox, now=lambda: now, policies=FakePolicies(policy))


async def test_given_mails_filed_today_when_the_time_arrives_then_one_message_has_counts_and_unsure_mails() -> None:
    store = FakeStore(
        [
            filed("Assistant/Newsletters"),
            filed("Assistant/Newsletters"),
            filed("Assistant/Finance"),
            filed("Assistant/Other", confidence=0.3, sender="odd@example.com", subject="Strange mail"),
        ]
    )
    outbox = FakeOutbox()

    await service(store, outbox, AFTER).send_overview()

    assert len(outbox.messages) == 1
    text = outbox.messages[0].text
    assert "Newsletters" in text
    assert "2" in text
    assert "Finance" in text
    assert "odd@example.com" in text
    assert "Strange mail" in text
    assert outbox.messages[0].buttons == ()
    assert "Assistant/" not in text  # the prefix is noise for Marco


async def test_given_nothing_was_filed_when_the_time_arrives_then_no_message_is_sent() -> None:
    store, outbox = FakeStore(), FakeOutbox()

    await service(store, outbox, AFTER).send_overview()

    assert outbox.messages == []


async def test_given_the_overview_was_already_sent_today_when_run_again_then_nothing_is_sent() -> None:
    store, outbox = FakeStore([filed("Assistant/Finance")]), FakeOutbox()
    run = service(store, outbox, AFTER)

    await run.send_overview()
    await run.send_overview()

    assert len(outbox.messages) == 1
    assert TODAY in store.sent_days


async def test_given_it_is_before_the_overview_time_when_run_then_nothing_is_sent_yet() -> None:
    store, outbox = FakeStore([filed("Assistant/Finance")]), FakeOutbox()

    await service(store, outbox, BEFORE).send_overview()

    assert outbox.messages == []


async def test_given_the_overview_time_skipped_by_a_clock_change_into_quiet_hours_when_it_arrives_then_it_waits() -> (
    None
):
    # 02:30 does not exist on 29 March 2026 in Amsterdam: the overview resolves to 03:00, the start of quiet hours.
    policy = make_policy(quiet_start=time(3, 0), quiet_end=time(8, 0), overview_at=time(2, 30))
    store, outbox = FakeStore([filed("Assistant/Finance")]), FakeOutbox()

    await service(store, outbox, datetime(2026, 3, 29, 1, 30, tzinfo=UTC), policy).send_overview()  # 03:30 local
    assert outbox.messages == []

    await service(store, outbox, datetime(2026, 3, 29, 6, 30, tzinfo=UTC), policy).send_overview()  # 08:30 local

    assert len(outbox.messages) == 1
    assert date(2026, 3, 29) in store.sent_days


async def test_given_another_zone_when_the_time_arrives_there_then_the_overview_follows_that_zone() -> None:
    new_york = make_policy(zone="America/New_York")
    store, outbox = FakeStore([filed("Assistant/Finance")]), FakeOutbox()

    await service(store, outbox, datetime(2026, 11, 9, 22, 59, tzinfo=UTC), new_york).send_overview()  # 17:59 there
    assert outbox.messages == []

    await service(store, outbox, datetime(2026, 11, 9, 23, 1, tzinfo=UTC), new_york).send_overview()  # 18:01 there

    assert len(outbox.messages) == 1
    assert TODAY in store.sent_days


async def test_given_a_day_whose_midnight_is_skipped_when_the_overview_runs_then_the_day_starts_at_01_00() -> None:
    santiago = make_policy(zone="America/Santiago")
    store, outbox = FakeStore([filed("Assistant/Finance")]), FakeOutbox()

    await service(store, outbox, datetime(2026, 9, 6, 22, 30, tzinfo=UTC), santiago).send_overview()  # 19:30 there

    assert store.asked_since == [datetime(2026, 9, 6, 4, 0, tzinfo=UTC)]  # 01:00 local, the first valid moment


async def test_given_a_quiet_day_when_the_time_arrives_then_it_is_remembered_so_a_late_mail_does_not_trigger_one() -> (
    None
):
    store, outbox = FakeStore(), FakeOutbox()
    await service(store, outbox, AFTER).send_overview()

    store.mails.append(filed("Assistant/Finance"))
    await service(store, outbox, AFTER).send_overview()

    assert outbox.messages == []


async def test_given_many_unsure_mails_with_growing_text_when_built_then_the_list_is_shortened_to_fit() -> None:
    mails = [filed("Assistant/Other", 0.1, sender="&" * 60, subject="&" * 80) for _ in range(30)]

    store, outbox = FakeStore(mails), FakeOutbox()
    await service(store, outbox, AFTER).send_overview()

    text = outbox.messages[0].text
    assert len(text) <= 4096
    assert "more" in text
    assert "&amp" not in text.replace("&amp;", "")


async def test_given_hostile_text_and_many_mails_when_built_then_it_is_escaped_and_fits_one_message() -> None:
    mails = [filed("Assistant/Other", 0.1, sender="<b>x</b>@example.com", subject="<a href='x'>y</a>" * 20)] * 300

    store, outbox = FakeStore(mails), FakeOutbox()
    await service(store, outbox, AFTER).send_overview()

    text = outbox.messages[0].text
    assert len(text) <= 4096
    assert "<a href" not in text
    assert "<b>x</b>" not in text


# ---- U-backlog-06: old mail that looked urgent but got no alert (INT-003, AC-B10) -----------------------------------


def old_urgent(sender: str = "boss@example.com", subject: str = "Pay the invoice") -> FiledMail:
    return FiledMail(label="Assistant/Finance", confidence=0.9, sender=sender, subject=subject, urgent=True)


def test_given_urgent_mail_filed_without_an_alert_when_the_overview_is_built_then_it_gets_its_own_section() -> None:
    text = build_overview([filed("Assistant/Newsletter"), old_urgent()]).text

    assert "Old mail that looked urgent (1)" in text
    assert "boss@example.com: Pay the invoice" in text
    assert "Today I filed 2 mails" in text  # the counts per category stay as they were


def test_given_no_urgent_mail_without_an_alert_when_the_overview_is_built_then_the_text_is_unchanged() -> None:
    mails = [filed("Assistant/Newsletter"), filed("Assistant/Shipping", confidence=0.5)]

    text = build_overview(mails).text

    assert "Old mail" not in text
    assert (
        text
        == build_overview([FiledMail(m.label, m.confidence, m.sender, m.subject, urgent=False) for m in mails]).text
    )


def test_given_markup_in_an_urgent_subject_when_the_overview_is_built_then_it_is_escaped_and_capped() -> None:
    text = build_overview([old_urgent(subject="<a href='https://evil.example'>click</a>" + "x" * 500)]).text

    assert "<a href" not in text
    assert "&lt;a href" in text
    assert "x" * (SUBJECT_CHARS + 1) not in text


def test_given_more_than_ten_urgent_mails_when_the_overview_is_built_then_ten_are_listed_and_the_rest_counted() -> None:
    mails = [old_urgent(subject=f"Urgent number {n}") for n in range(13)]

    text = build_overview(mails).text

    assert "Old mail that looked urgent (13)" in text
    assert text.count("Urgent number") == 10
    assert "…and 3 more" in text
    assert len(text) <= MAX_MESSAGE_CHARS


def test_given_an_urgent_mail_that_is_also_unsure_when_the_overview_is_built_then_it_is_listed_in_both_sections() -> (
    None
):
    text = build_overview([FiledMail("Assistant/Other", 0.4, "x@example.com", "Odd one", urgent=True)]).text

    assert "I was unsure about 1" in text
    assert "Old mail that looked urgent (1)" in text


# ---- U-quiet-hours-13: the window runs from the last settled instant, across zone changes (AC-27) ------------------

AMSTERDAM = DEFAULT_POLICY
NEW_YORK = make_policy(zone="America/New_York")
AUCKLAND = make_policy(zone="Pacific/Auckland")


class Rig:
    """One store, outbox and policy source; the clock and the policy are moved from the test."""

    def __init__(self, policy: TimePolicy = AMSTERDAM) -> None:
        self.store, self.outbox, self.policies = FakeStore(), FakeOutbox(), FakePolicies(policy)
        self.now = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
        self.service = OverviewService(
            self.store, self.store, self.outbox, now=lambda: self.now, policies=self.policies
        )

    def file(self, at: datetime, subject: str = "Hi") -> None:
        self.store.timed.append((at, filed("Assistant/Finance", subject=subject)))

    async def run(self, at: datetime) -> None:
        self.now = self.store.now = at
        await self.service.send_overview()


def test_given_valid_policies_when_the_overview_falls_in_quiet_hours_then_only_because_a_clock_change_skipped_it() -> (
    None
):
    # Why the "yesterday" branch of the old _pending_day is unreachable: validation puts the overview time outside
    # quiet hours, so the overview moment is inside them only when the wall time does not exist that day.
    policies = [
        DEFAULT_POLICY,
        make_policy(quiet_start=time(3, 0), quiet_end=time(8, 0), overview_at=time(2, 30)),
        make_policy(zone="America/New_York", quiet_start=time(1, 0), quiet_end=time(7, 0), overview_at=time(0, 30)),
        make_policy(zone="America/Santiago", quiet_start=time(1, 30), quiet_end=time(9, 0), overview_at=time(0, 30)),
    ]
    inside = []
    for policy in policies:
        assert validate(policy) == []
        for offset in range(366):
            day = date(2026, 1, 1) + timedelta(days=offset)
            moment = overview_on(day, policy)
            if in_quiet_hours(moment, policy):
                inside.append((policy.zone, day))
                assert (
                    moment.astimezone(ZoneInfo(policy.zone)).time() != policy.overview_at
                )  # the wall time was skipped
    assert inside  # the clock-change case does exist, so the quiet check in send_overview stays


async def test_given_the_overview_sent_in_amsterdam_when_the_zone_becomes_new_york_then_no_second_one_that_date() -> (
    None
):
    rig = Rig()
    rig.file(datetime(2026, 11, 9, 16, 0, tzinfo=UTC), "before")
    await rig.run(datetime(2026, 11, 9, 17, 1, tzinfo=UTC))  # 18:01 Amsterdam
    rig.file(datetime(2026, 11, 9, 17, 20, tzinfo=UTC), "after")
    rig.policies.policy = NEW_YORK

    await rig.run(datetime(2026, 11, 9, 23, 5, tzinfo=UTC))  # 18:05 New York, still 9 November there

    assert len(rig.outbox.messages) == 1


async def test_given_the_zone_changed_same_evening_when_the_next_overview_comes_then_it_is_at_18_00_new_york_time() -> (
    None
):
    rig = Rig()
    rig.file(datetime(2026, 11, 9, 16, 0, tzinfo=UTC), "before")
    await rig.run(datetime(2026, 11, 9, 17, 1, tzinfo=UTC))
    rig.file(datetime(2026, 11, 9, 17, 20, tzinfo=UTC), "after")
    rig.policies.policy = NEW_YORK

    await rig.run(datetime(2026, 11, 10, 22, 59, tzinfo=UTC))  # 17:59 New York on 10 November
    assert len(rig.outbox.messages) == 1
    await rig.run(datetime(2026, 11, 10, 23, 1, tzinfo=UTC))  # 18:01 New York

    assert len(rig.outbox.messages) == 2
    assert "Today I filed 1 mails" in rig.outbox.messages[1].text  # the mail filed after the first one, not dropped


async def test_given_a_previous_overview_when_the_next_runs_then_the_window_starts_at_its_settled_instant() -> None:
    rig = Rig()
    settled = datetime(2026, 11, 9, 17, 1, tzinfo=UTC)
    rig.file(datetime(2026, 11, 9, 16, 0, tzinfo=UTC))
    await rig.run(settled)

    await rig.run(datetime(2026, 11, 10, 17, 1, tzinfo=UTC))

    assert rig.store.asked_since[-1] == settled


async def test_given_zone_changes_back_and_forth_when_mail_is_filed_every_hour_then_each_mail_is_in_one_overview() -> (
    None
):
    rig = Rig()
    changes = {
        datetime(2026, 11, 9, 20, 0, tzinfo=UTC): NEW_YORK,  # the evening of an overview already sent
        datetime(2026, 11, 11, 3, 0, tzinfo=UTC): AMSTERDAM,  # New York back to Amsterdam: the local date moves on
        datetime(2026, 11, 12, 0, 0, tzinfo=UTC): AUCKLAND,  # a jump of 12 hours ahead: a local day is skipped
        datetime(2026, 11, 12, 12, 0, tzinfo=UTC): NEW_YORK,  # back behind: the local date is repeated
        datetime(2026, 11, 13, 10, 0, tzinfo=UTC): AUCKLAND,
    }
    first = datetime(2026, 11, 9, 0, 15, tzinfo=UTC)
    hours = 24 * 6
    filed_at = [first + timedelta(hours=hour) for hour in range(hours)]
    for moment in filed_at:
        rig.file(moment)
    for hour in range(hours):
        run_at = first + timedelta(hours=hour, minutes=30)  # a quarter past: after the mail of that hour
        rig.policies.policy = changes.get(run_at.replace(minute=0), rig.policies.policy)
        await rig.run(run_at)

    counts = [int(m.text.split("filed ")[1].split(" ")[0]) for m in rig.outbox.messages]
    settled = max(rig.store.sent_days.values())
    assert len(counts) >= 4
    assert sum(counts) == len([moment for moment in filed_at if moment < settled])  # none dropped, none twice


async def test_given_a_changed_overview_time_when_the_next_overview_comes_then_it_is_used_for_that_one_only() -> None:
    rig = Rig()
    rig.file(datetime(2026, 11, 9, 16, 0, tzinfo=UTC))
    await rig.run(datetime(2026, 11, 9, 17, 1, tzinfo=UTC))  # sent at the old time, 18:01
    rig.policies.policy = replace(AMSTERDAM, overview_at=time(20, 0))
    rig.file(datetime(2026, 11, 9, 17, 30, tzinfo=UTC))

    await rig.run(datetime(2026, 11, 9, 19, 30, tzinfo=UTC))  # 20:30 the same evening: today's is already settled
    assert len(rig.outbox.messages) == 1
    await rig.run(datetime(2026, 11, 10, 17, 30, tzinfo=UTC))  # 18:30 next day: before the new time
    assert len(rig.outbox.messages) == 1
    await rig.run(datetime(2026, 11, 10, 19, 1, tzinfo=UTC))  # 20:01 next day

    assert len(rig.outbox.messages) == 2


async def test_given_one_run_when_the_overview_is_sent_then_the_policy_is_read_once() -> None:
    rig = Rig()
    rig.file(datetime(2026, 11, 9, 16, 0, tzinfo=UTC))

    await rig.run(datetime(2026, 11, 9, 17, 1, tzinfo=UTC))

    assert rig.policies.reads == 1
