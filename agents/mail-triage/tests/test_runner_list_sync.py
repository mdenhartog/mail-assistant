"""U-mail-categories-21: the agent runs the list sync before judging and on a cadence (AC-3, AC-40; ADR-0046)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.adapters.gmail_resort import GmailResort
from app.settings import load_settings
from app.usecases.list_sync import ListSync, SyncResult
from tests.fakes.fake_gmail import FakeGmail
from tests.fakes.list_store import FakeListStore
from tests.test_runner import (
    NOW,
    CatchUpStep,
    CodeAlertStep,
    Delivery,
    Inbox,
    Overview,
    Router,
    Snooze,
    Steps,
    Store,
    WebNoticeStep,
)
from app.runner import Runner
from app.usecases.triage import RunSummary
from tests.test_settings import VALID

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

CADENCE = 60.0


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


class JudgingPipeline:
    """Notes which list version existed when mail was judged."""

    def __init__(self, store: FakeListStore) -> None:
        self.store = store
        self.versions: list[int] = []

    async def run_once(self) -> RunSummary:
        self.versions.append(self.store.version)
        return RunSummary()


class CountingSync:
    def __init__(self, *, fail_times: int = 0) -> None:
        self.runs = 0
        self.fail_times = fail_times

    async def run(self) -> SyncResult:
        self.runs += 1
        if self.runs <= self.fail_times:
            raise RuntimeError("gmail said: Subject: very private")
        return SyncResult(1, seeded=False, created=0, renamed=0, failed=0)


def make_runner(tmp_path: Path, clock: Clock, sync: object, pipeline: object | None = None) -> Runner:
    steps = Steps()
    return Runner(
        pipeline=pipeline or JudgingPipeline(FakeListStore()),  # type: ignore[arg-type]
        catchup=CatchUpStep(steps),
        delivery=Delivery(steps),
        snooze=Snooze(steps),
        overview=Overview(steps),
        web_notice=WebNoticeStep(steps),
        code_alert=CodeAlertStep(steps),
        store=Store(steps),
        inbox=Inbox([]),
        router=Router(),
        list_sync=sync,  # type: ignore[arg-type]
        list_sync_seconds=CADENCE,
        heartbeat=tmp_path / "heartbeat",
        interval_seconds=0.01,
        now=clock,
    )


def real_sync(gmail: FakeGmail, store: FakeListStore) -> ListSync:
    return ListSync(GmailResort(gmail, sleep=lambda _s: None), store)


async def test_given_a_first_start_with_labels_and_no_list_when_the_first_cycle_runs_then_version_one_exists_before_judging(
    tmp_path: Path,
) -> None:
    gmail = FakeGmail()
    gmail.add_label("Assistant/Bills")
    store = FakeListStore()
    pipeline = JudgingPipeline(store)
    run = make_runner(tmp_path, Clock(), real_sync(gmail, store), pipeline)

    await run.mail_cycle()

    assert pipeline.versions == [1]
    assert [c.name for c in store.categories] == ["Bills"]


async def test_given_a_name_only_change_when_one_cadence_has_passed_then_the_gmail_label_is_renamed_by_id(
    tmp_path: Path,
) -> None:
    gmail = FakeGmail()
    store = FakeListStore()
    ids = store.save_list(["Bills"])
    clock = Clock()
    run = make_runner(tmp_path, clock, real_sync(gmail, store))
    await run.mail_cycle()
    label = store.labels[ids["Bills"]].label_id
    store.save_list(["Invoices"], keep={"Invoices": ids["Bills"]})

    clock.now += timedelta(seconds=CADENCE - 1)
    await run.mail_cycle()
    assert gmail.label_table[label] == "Assistant/Bills"  # not yet: the cadence has not passed
    clock.now += timedelta(seconds=1)
    await run.mail_cycle()

    assert gmail.label_table[label] == "Assistant/Invoices"


async def test_given_a_cycle_inside_the_cadence_when_it_runs_then_the_sync_is_not_run_again(tmp_path: Path) -> None:
    sync = CountingSync()
    clock = Clock()
    run = make_runner(tmp_path, clock, sync)

    await run.mail_cycle()
    await run.mail_cycle()

    assert sync.runs == 1


async def test_given_a_failing_sync_when_cycles_run_then_triage_continues_the_log_has_no_content_and_the_next_cadence_retries(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    sync = CountingSync(fail_times=1)
    clock = Clock()
    pipeline = JudgingPipeline(FakeListStore())
    run = make_runner(tmp_path, clock, sync, pipeline)

    await run.mail_cycle()
    clock.now += timedelta(seconds=CADENCE)
    await run.mail_cycle()

    assert pipeline.versions == [0, 0]  # triage ran in both cycles
    assert (tmp_path / "heartbeat").exists()
    assert "step list_sync failed kind=RuntimeError" in caplog.text
    assert "very private" not in caplog.text
    assert sync.runs == 2


async def test_given_two_agents_at_once_when_both_sync_then_the_result_is_the_same_as_one(tmp_path: Path) -> None:
    gmail = FakeGmail()
    gmail.add_label("Assistant/Bills")
    store = FakeListStore()
    first = make_runner(tmp_path, Clock(), real_sync(gmail, store))
    second = make_runner(tmp_path, Clock(), real_sync(gmail, store))

    await asyncio.gather(first.mail_cycle(), second.mail_cycle())

    assert store.version == 1
    assert [c.name for c in store.categories] == ["Bills"]
    assert gmail.label_names().count("Assistant/Bills") == 1
    assert gmail.label_names().count("Assistant/Other") == 1
    assert gmail.label_names().count("Archive") == 1


def test_given_the_configuration_when_loaded_then_the_mailbox_id_and_the_cadence_come_from_settings() -> None:
    defaults = load_settings(VALID)
    custom = load_settings({**VALID, "MAILBOX_ID": "mb7", "LIST_SYNC_INTERVAL_SECONDS": "15"})

    assert (defaults.mailbox_id, defaults.list_sync_interval_seconds) == ("primary", 60)
    assert (custom.mailbox_id, custom.list_sync_interval_seconds) == ("mb7", 15)
