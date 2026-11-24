"""U-mail-categories-10: the daily AC-46 report on how much the user re-filed by hand and how much sits in "Other"."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.gmail_read import FetchedMail
from app.core.judgement import OTHER_ID
from app.core.managed import ManagedLabel, ManagedSet, Role
from app.usecases.refile_report import Filed, RefileReport, RefileReportService
from app.usecases.report import SuccessCounts
from app.usecases.resort_apply import ResortLabels

NOW = datetime(2026, 12, 1, 6, 0, tzinfo=UTC)
CAP = 1000
FINANCE_ID = "11111111-1111-1111-1111-111111111111"
TRAVEL_ID = "22222222-2222-2222-2222-222222222222"
CANARY_SENDER = "canary-sender@example.invalid"
CANARY_SUBJECT = "canary-subject-4711"
NAMES = {"L_FIN": "Finance", "L_TRV": "Travel", "L_OTH": "Other", "L_X": "Amerika", "INBOX": "INBOX"}
COUNTS = SuccessCounts(
    days=14,
    filed=40,
    by_rule=10,
    by_model=28,
    in_other=4,
    always_notify_alerts=14,
    system_applied=0,
    system_moved_back=0,
)


def _labels(other: ManagedLabel | None = None) -> ResortLabels:
    """The managed labels of the list: Finance, Travel, "Other" (by the Other setting) and the archive label."""
    by_category = {
        FINANCE_ID: ManagedLabel("Finance", "L_FIN", Role.TOPIC),
        TRAVEL_ID: ManagedLabel("Travel", "L_TRV", Role.EXTRA),
        OTHER_ID: other or ManagedLabel("Other", "L_OTH", Role.OTHER),
    }
    archive = ManagedLabel("Archive", "L_ARC", Role.ARCHIVE)
    return ResortLabels(ManagedSet([*by_category.values(), archive]), by_category)


def _mail(message_id: str, labels: set[str]) -> FetchedMail:
    return FetchedMail(
        message_id=message_id,
        thread_id="t",
        sender=CANARY_SENDER,
        reply_to=None,
        subject=CANARY_SUBJECT,
        text="body",
        has_attachment=False,
        headers={},
        labels=frozenset(labels),
    )


@dataclass
class FakeStore:
    filed: list[Filed] = field(default_factory=list)
    reports: list[RefileReport] = field(default_factory=list)
    asked_since: list[datetime] = field(default_factory=list)
    counts: SuccessCounts = COUNTS
    labels: ResortLabels = field(default_factory=_labels)

    async def success_counts(self, since: datetime) -> SuccessCounts:
        assert since == NOW - timedelta(days=14)
        return self.counts

    async def filings_since(self, since: datetime) -> list[Filed]:
        self.asked_since.append(since)
        return list(self.filed)

    async def managed_labels(self) -> ResortLabels:
        return self.labels

    async def record_report(self, report: RefileReport) -> None:
        self.reports.append(report)


@dataclass
class FakeGmail:
    mails: dict[str, set[str]] = field(default_factory=dict)

    def label_names(self) -> dict[str, str]:
        return dict(NAMES)

    def fetch(self, message_id: str) -> FetchedMail | None:
        labels = self.mails.get(message_id)
        return None if labels is None else _mail(message_id, labels)


def _rig(*, kept: int, moved: int, other: int = 0, gone: int = 0) -> tuple[RefileReportService, FakeStore]:
    """``kept`` mails still under Finance, ``moved`` re-filed to Travel, ``other`` filed (and left) under Other."""
    store, gmail = FakeStore(), FakeGmail()
    n = 0
    for count, filed_as, now_labels in (
        (kept, FINANCE_ID, {"INBOX", "L_FIN"}),
        (moved, FINANCE_ID, {"INBOX", "L_TRV"}),
        (other, OTHER_ID, {"INBOX", "L_OTH"}),
        (gone, FINANCE_ID, None),
    ):
        for _ in range(count):
            n += 1
            store.filed.append(Filed(f"m{n}", filed_as, None))
            if now_labels is not None:
                gmail.mails[f"m{n}"] = set(now_labels)
    return RefileReportService(store, gmail, now=lambda: NOW, max_checked=CAP), store


async def test_three_of_one_hundred_mails_changed_label_reports_three_percent() -> None:
    service, store = _rig(kept=97, moved=3)

    report = await service.run_once()

    assert (report.filed, report.refiled) == (100, 3)
    assert report.refiled_percent == pytest.approx(3.0)
    assert store.reports == [report]


async def test_the_share_of_mail_now_in_other_is_reported() -> None:
    service, _ = _rig(kept=70, moved=0, other=30)

    report = await service.run_once()

    assert report.in_other == 30
    assert report.other_percent == pytest.approx(30.0)


async def test_a_mail_moved_by_hand_into_other_counts_as_refiled_and_as_other() -> None:
    store, gmail = FakeStore(filed=[Filed("a", FINANCE_ID, None)]), FakeGmail({"a": {"INBOX", "L_OTH"}})
    service = RefileReportService(store, gmail, now=lambda: NOW, max_checked=CAP)

    report = await service.run_once()

    assert (report.refiled, report.in_other) == (1, 1)


async def test_a_mail_filed_with_an_extra_label_is_not_refiled_while_both_labels_stay() -> None:
    store = FakeStore(filed=[Filed("a", FINANCE_ID, TRAVEL_ID), Filed("b", FINANCE_ID, TRAVEL_ID)])
    gmail = FakeGmail({"a": {"INBOX", "L_FIN", "L_TRV"}, "b": {"INBOX", "L_FIN"}})
    service = RefileReportService(store, gmail, now=lambda: NOW, max_checked=CAP)

    report = await service.run_once()

    assert report.refiled == 1  # only "b", where the user took the extra label off


async def test_a_mail_filed_with_an_extra_label_is_refiled_when_the_topic_changes() -> None:
    store = FakeStore(filed=[Filed("a", FINANCE_ID, TRAVEL_ID)])
    gmail = FakeGmail({"a": {"INBOX", "L_OTH", "L_TRV"}})
    service = RefileReportService(store, gmail, now=lambda: NOW, max_checked=CAP)

    assert (await service.run_once()).refiled == 1


async def test_a_deleted_mail_is_not_counted_as_refiled() -> None:
    service, _ = _rig(kept=9, moved=0, gone=1)

    report = await service.run_once()

    assert report.refiled == 0
    assert report.gone == 1
    assert report.filed == 10


async def test_an_empty_period_reports_zero_percent_without_dividing_by_zero() -> None:
    service, _ = _rig(kept=0, moved=0)

    report = await service.run_once()

    assert (report.refiled_percent, report.other_percent) == (0.0, 0.0)


async def test_the_period_is_the_last_fourteen_days() -> None:
    service, store = _rig(kept=1, moved=0)

    await service.run_once()

    assert store.asked_since == [NOW - timedelta(days=14)]


async def test_the_report_and_the_log_hold_no_sender_or_subject(caplog: pytest.LogCaptureFixture) -> None:
    service, store = _rig(kept=5, moved=2, other=1)

    with caplog.at_level(logging.DEBUG):
        report = await service.run_once()

    seen = repr(report) + repr(store.reports) + caplog.text
    assert CANARY_SENDER not in seen
    assert CANARY_SUBJECT not in seen
    assert "refiled=2" in caplog.text


@dataclass
class CountingGmail(FakeGmail):
    fetched: list[str] = field(default_factory=list)

    def fetch(self, message_id: str) -> FetchedMail | None:
        self.fetched.append(message_id)
        return super().fetch(message_id)


def _capped(filings: int, cap: int) -> tuple[RefileReportService, FakeStore, CountingGmail]:
    store, gmail = FakeStore(), CountingGmail()
    for n in range(filings):  # newest first, as the store hands them out; every third was re-filed
        store.filed.append(Filed(f"m{n}", FINANCE_ID, None))
        gmail.mails[f"m{n}"] = {"INBOX", "L_TRV" if n % 3 == 0 else "L_FIN"}
    return RefileReportService(store, gmail, now=lambda: NOW, max_checked=cap), store, gmail


async def test_more_filings_than_the_cap_fetches_at_most_the_cap_and_reports_how_many_were_checked() -> None:
    service, store, gmail = _capped(filings=50, cap=12)

    report = await service.run_once()

    assert len(gmail.fetched) == 12
    assert gmail.fetched == [f"m{n}" for n in range(12)]  # the newest first
    assert (report.filed, report.checked) == (50, 12)
    assert report.refiled == 4
    assert report.refiled_percent == pytest.approx(100 * 4 / 12)  # a share of the mails that were checked
    assert store.reports == [report]


async def test_fewer_filings_than_the_cap_checks_them_all() -> None:
    service, _, gmail = _capped(filings=5, cap=12)

    report = await service.run_once()

    assert len(gmail.fetched) == 5
    assert (report.filed, report.checked) == (5, 5)


async def test_the_log_says_how_many_were_checked(caplog: pytest.LogCaptureFixture) -> None:
    service, _, _ = _capped(filings=50, cap=12)

    with caplog.at_level(logging.INFO):
        await service.run_once()

    assert "checked=12" in caplog.text
    assert "filed=50" in caplog.text


async def test_the_log_carries_the_success_numbers_of_the_period(caplog: pytest.LogCaptureFixture) -> None:
    service, _ = _rig(kept=1, moved=0)

    with caplog.at_level(logging.INFO):
        await service.run_once()

    assert "Filed by a sender rule: 25.0% of 40 new mails" in caplog.text
    assert "At least 2.0 model calls per day (filing calls only)" in caplog.text
    assert "Always-notify alerts per day: 1.0" in caplog.text
    assert "Filed under Other: 10.0% of 40 new mails" in caplog.text


async def test_other_is_counted_by_the_other_setting_and_not_by_the_old_name() -> None:
    renamed = ManagedLabel("Everything else", "L_OTH", Role.OTHER)  # the setting changed; the label kept its id
    store = FakeStore(filed=[Filed("a", FINANCE_ID, None), Filed("b", FINANCE_ID, None)], labels=_labels(renamed))
    gmail = FakeGmail({"a": {"INBOX", "L_OTH"}, "b": {"INBOX", "L_FIN"}})
    service = RefileReportService(store, gmail, now=lambda: NOW, max_checked=CAP)

    report = await service.run_once()

    assert report.in_other == 1


async def test_a_label_that_is_not_the_other_label_is_not_counted_as_other_even_with_its_name() -> None:
    lookalike = ManagedLabel("Misc", "L_MISC", Role.OTHER)  # "Other" is now Misc; a label named Other is only a label
    store = FakeStore(filed=[Filed("a", FINANCE_ID, None)], labels=_labels(lookalike))
    gmail = FakeGmail({"a": {"INBOX", "L_OTH"}})  # L_OTH is named Other in Gmail but is not managed any more
    service = RefileReportService(store, gmail, now=lambda: NOW, max_checked=CAP)

    report = await service.run_once()

    assert report.in_other == 0


async def test_a_label_of_the_user_on_the_mail_does_not_make_it_refiled() -> None:
    store = FakeStore(filed=[Filed("a", FINANCE_ID, None)])
    gmail = FakeGmail({"a": {"INBOX", "L_FIN", "L_X"}})  # the user's own label next to the filed one
    service = RefileReportService(store, gmail, now=lambda: NOW, max_checked=CAP)

    report = await service.run_once()

    assert report.refiled == 0


async def test_archiving_a_mail_is_not_refiling_it() -> None:
    store = FakeStore(filed=[Filed("a", FINANCE_ID, None)])
    gmail = FakeGmail({"a": {"L_FIN", "L_ARC"}})  # the user archived it; the filed label is still there
    gmail_names = {**NAMES, "L_ARC": "Archive"}
    gmail.label_names = lambda: dict(gmail_names)  # type: ignore[method-assign]
    service = RefileReportService(store, gmail, now=lambda: NOW, max_checked=CAP)

    report = await service.run_once()

    assert report.refiled == 0
