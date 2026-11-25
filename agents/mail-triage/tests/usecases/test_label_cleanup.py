"""U-label-prefix-removal-09: the cleanup step of the mail cycle (ADR-0060 point 5, spec AC 7, 10, 23, 24, 28, 29, 30).

The real Gmail delete adapter runs on the in-memory mailbox, the store is the in-memory one. Criteria 1 to 9 of the
unit; the PostgreSQL side (lease, purge, record) is in ``tests/db``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.adapters.gmail_label_delete import GmailLabelDelete
from app.adapters.gmail_resort import GmailResort
from app.core.managed import ManagedSet, Role
from app.db.pg_label_cleanup import CleanupSettings, StoredTimer
from app.usecases.label_cleanup import LabelCleanup, label_id_hash
from app.usecases.resort_apply import ResortLabels
from app.usecases.list_sync import MigrationState
from tests.fakes.cleanup_store import FakeCleanupStore
from tests.fakes.fake_gmail import FakeGmail

if TYPE_CHECKING:
    from collections.abc import Callable

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
WAIT = timedelta(hours=12)
CYCLE = timedelta(minutes=15)
CANARY = "Canary-Label-Name-7731"


class Chat:
    def __init__(self, *, fail: bool = False) -> None:
        self.texts: list[str] = []
        self.fail = fail

    async def say(self, text: str) -> None:
        if self.fail:
            raise RuntimeError(f"send failed for {CANARY}")
        self.texts.append(text)


class Rig:
    """One mailbox: Gmail, the store, a clock and the step."""

    def __init__(self, state: MigrationState | None = MigrationState.DONE) -> None:
        self.gmail = FakeGmail()
        self.store = FakeCleanupStore(state)
        self.chat = Chat()
        self.now = NOW
        self.delete = GmailLabelDelete(self.gmail, sleep=lambda _s: None)
        self.step = self.make()

    def make(self, delete: GmailLabelDelete | None = None) -> LabelCleanup:
        return LabelCleanup(
            GmailResort(self.gmail, ManagedSet(()), sleep=lambda _s: None),
            delete or self.delete,
            self.store,
            self.chat,
            now=lambda: self.now,
            cycle=CYCLE,
        )

    def empty_label(self, name: str, *, ripe: bool = True, age: timedelta = WAIT + CYCLE) -> str:
        """A user label without mail, with a timer that is ``ripe`` (as old as ``age``) or not there at all."""
        label_id = self.gmail.add_label(name)
        if ripe:
            self.store.timer_rows[label_id] = StoredTimer(self.now - age, self.now - CYCLE, WAIT)
        return label_id

    def exists(self, label_id: str) -> bool:
        return label_id in self.gmail.label_table


# --- the delete is idempotent and checks the managed set under the lease ----------------------------------------


async def test_given_the_delete_call_answers_not_found_when_a_cycle_runs_then_the_label_counts_as_deleted() -> None:
    rig = Rig()
    label = rig.empty_label("A1")
    rig.gmail.fail_call("labels.delete", 404)

    result = await rig.step.run_once()

    assert (result.deleted, result.errors, result.refused) == (1, 0, 0)
    assert label_id_hash(label) in rig.store.deleted
    assert label not in rig.store.timer_rows


class ListEntersLate(FakeCleanupStore):
    """The first read of the managed set is the scan; the label enters the list before the second (the lease)."""

    def __init__(self, label: tuple[str, str, Role]) -> None:
        super().__init__(MigrationState.DONE)
        self._label = label
        self.reads = 0

    async def managed(self) -> ResortLabels:
        self.reads += 1
        if self.reads > 1:
            self.manage(self._label)
        return await super().managed()


async def test_given_a_label_that_entered_the_list_after_the_scan_when_the_lease_is_held_then_it_is_not_deleted() -> None:
    rig = Rig()
    label = rig.empty_label("A1")
    rig.store = ListEntersLate(("A1", label, Role.TOPIC))
    rig.store.timer_rows[label] = StoredTimer(NOW - WAIT - CYCLE, NOW - CYCLE, WAIT)
    step = rig.make()

    result = await step.run_once()

    assert rig.exists(label)
    assert "labels.delete" not in rig.gmail.calls
    assert result.deleted == 0
    assert rig.store.deleted == {}


# --- criterion 2: exactly one delete per cycle -------------------------------------------------------------------


async def test_given_three_empty_labels_past_their_wait_when_a_cycle_runs_then_exactly_one_is_deleted() -> None:
    rig = Rig()
    ids = [rig.empty_label(name, age=WAIT + CYCLE * (3 - n)) for n, name in enumerate(("A1", "B1", "C1"))]

    result = await rig.step.run_once()

    assert rig.gmail.calls.count("labels.delete") == 1
    assert [rig.exists(i) for i in ids] == [False, True, True]  # the one that waited longest goes first
    assert result.deleted == 1
    assert set(rig.store.timer_rows) == set(ids[1:])


async def test_given_the_next_cycle_when_two_are_left_then_one_more_goes() -> None:
    rig = Rig()
    ids = [rig.empty_label(name) for name in ("A1", "B1", "C1")]
    await rig.step.run_once()
    rig.now += CYCLE

    await rig.step.run_once()

    assert sum(rig.exists(i) for i in ids) == 1


async def test_given_an_empty_label_without_a_timer_when_a_cycle_runs_then_a_timer_starts_with_the_current_wait() -> (
    None
):
    rig = Rig()
    label = rig.empty_label("A1", ripe=False)

    result = await rig.step.run_once()

    assert rig.store.timer_rows[label] == StoredTimer(NOW, NOW, WAIT)
    assert rig.exists(label)
    assert result.started == 1


async def test_given_a_waiting_label_when_a_cycle_runs_then_it_is_seen_again_but_not_deleted() -> None:
    rig = Rig()
    label = rig.gmail.add_label("A1")
    rig.store.timer_rows[label] = StoredTimer(NOW - timedelta(hours=1), NOW - CYCLE, WAIT)

    await rig.step.run_once()

    assert rig.exists(label)
    assert rig.store.timer_rows[label].last_seen_empty == NOW


async def test_given_mail_on_a_label_with_a_timer_when_a_cycle_runs_then_the_timer_is_removed() -> None:
    rig = Rig()
    label = rig.empty_label("A1")
    rig.gmail.add_mail(labels=("INBOX", label))

    await rig.step.run_once()

    assert rig.exists(label)
    assert label not in rig.store.timer_rows


# --- what is never deleted ---------------------------------------------------------------------------------------


async def test_given_managed_system_filtered_and_protected_labels_when_ripe_then_none_is_deleted() -> None:
    rig = Rig()
    category = rig.empty_label("Bills")
    other = rig.empty_label("Other")
    archive = rig.empty_label("Archive")
    rig.store.manage(("Bills", category, Role.TOPIC), ("Other", other, Role.OTHER), ("Archive", archive, Role.ARCHIVE))
    filtered = rig.empty_label("Filtered")
    rig.gmail.add_filter([filtered])
    protected = rig.empty_label("Dropped")
    rig.store.left[protected] = NOW - timedelta(days=3)  # AC 28
    parent = rig.empty_label("Parent")
    rig.gmail.add_label("Parent/Child")
    system = rig.gmail.add_system_label("CATEGORY_PERSONAL")
    rig.store.timer_rows[system] = StoredTimer(NOW - WAIT - CYCLE, NOW - CYCLE, WAIT)

    result = await rig.step.run_once()

    assert "labels.delete" not in rig.gmail.calls
    assert all(rig.exists(i) for i in (category, other, archive, filtered, protected, parent, system))
    assert result.deleted == 0


async def test_given_a_label_that_never_was_in_the_list_when_ripe_then_it_is_deleted() -> None:
    rig = Rig()
    never = rig.empty_label("Amerika")  # a hand-made label (D6)

    await rig.step.run_once()

    assert not rig.exists(never)


async def test_given_a_label_that_left_the_list_long_ago_when_ripe_then_it_is_deleted() -> None:
    rig = Rig()
    dropped = rig.empty_label("Dropped")
    rig.store.left[dropped] = NOW - timedelta(days=8)

    await rig.step.run_once()

    assert not rig.exists(dropped)


async def test_given_a_stored_id_not_yet_known_by_name_when_it_matches_a_managed_name_then_it_is_not_deleted() -> None:
    rig = Rig()
    by_name = rig.empty_label("Bills")
    rig.store.manage(("bills", None, Role.TOPIC))  # the id is not stored yet: the name decides

    await rig.step.run_once()

    assert rig.exists(by_name)


async def test_given_a_timer_of_a_label_that_is_gone_when_a_cycle_runs_then_the_timer_is_removed() -> None:
    rig = Rig()
    rig.store.timer_rows["Label_gone"] = StoredTimer(NOW - WAIT, NOW - CYCLE, WAIT)

    await rig.step.run_once()

    assert rig.store.timer_rows == {}


async def test_given_the_filters_cannot_be_read_when_a_cycle_runs_then_nothing_is_deleted() -> None:
    rig = Rig()
    label = rig.empty_label("A1")
    rig.gmail.fail_call("settings.filters.list", 403)  # Gmail does not say which labels the filters use

    result = await rig.step.run_once()

    assert rig.exists(label)
    assert result.deleted == 0


# --- criterion 3: a re-sort that targets the label ----------------------------------------------------------------


async def test_given_a_resort_that_targets_a_label_when_ripe_then_it_is_not_deleted_and_the_next_one_is() -> None:
    rig = Rig()
    targeted = rig.empty_label("Targeted", age=WAIT + 4 * CYCLE)
    free = rig.empty_label("Free")
    rig.store.resort_ids = frozenset({targeted})

    result = await rig.step.run_once()

    assert rig.exists(targeted)
    assert not rig.exists(free)
    assert result.deleted == 1


# --- criterion 6: the rename plan gates the delete ----------------------------------------------------------------


@pytest.mark.parametrize("state", [None, MigrationState.PENDING, MigrationState.CONFIRMED])
async def test_given_a_migration_that_is_not_done_when_a_cycle_runs_then_nothing_is_deleted_or_started(
    state: MigrationState | None,
) -> None:
    rig = Rig(state)
    ripe = rig.empty_label("A1")
    fresh = rig.empty_label("B1", ripe=False)

    result = await rig.step.run_once()

    assert "labels.delete" not in rig.gmail.calls
    assert rig.exists(ripe)
    assert fresh not in rig.store.timer_rows
    assert result.deleted == 0
    assert result.blocked is True


# --- criterion 4: the record --------------------------------------------------------------------------------------


async def test_given_a_delete_when_recorded_then_the_name_and_the_hash_of_the_id_are_stored_and_the_timer_goes() -> (
    None
):
    rig = Rig()
    label = rig.empty_label(CANARY)

    await rig.step.run_once()

    expected = hashlib.sha256(label.encode()).hexdigest()
    assert label_id_hash(label) == expected
    assert rig.store.deleted == {expected: (CANARY, NOW)}
    assert label not in rig.store.timer_rows


# --- criterion 5: counts only, once a day; the canary stays out ---------------------------------------------------


async def test_given_deletes_over_two_days_when_cycles_run_then_one_notice_per_day_with_counts_only() -> None:
    rig = Rig()
    rig.empty_label(CANARY)
    rig.empty_label("Second")
    await rig.step.run_once()
    assert len(rig.chat.texts) == 1  # the first delete is announced at once
    rig.now += CYCLE
    await rig.step.run_once()
    assert len(rig.chat.texts) == 1  # the second one waits for the day to pass

    rig.now += timedelta(days=1)
    await rig.step.run_once()

    assert len(rig.chat.texts) == 2
    assert all("1" in text and CANARY not in text and "Second" not in text for text in rig.chat.texts)


async def test_given_no_delete_when_a_cycle_runs_then_no_notice_is_sent() -> None:
    rig = Rig()
    rig.empty_label("A1", ripe=False)

    await rig.step.run_once()

    assert rig.chat.texts == []


async def test_given_a_notice_that_cannot_be_sent_when_a_cycle_runs_then_the_step_goes_on_and_the_next_cycle_retries(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rig = Rig()
    rig.chat.fail = True
    rig.empty_label(CANARY)
    caplog.set_level(logging.DEBUG)

    await rig.step.run_once()
    assert rig.chat.texts == []
    rig.chat.fail = False
    rig.now += CYCLE
    await rig.step.run_once()

    assert len(rig.chat.texts) == 1
    assert CANARY not in caplog.text


async def test_given_a_canary_label_when_every_path_runs_then_no_log_notice_or_error_holds_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rig = Rig()
    deleted = rig.empty_label(CANARY)
    refused = rig.empty_label(CANARY + "-refused", age=WAIT + 9 * CYCLE)
    rig.gmail.inject_mail_before_next(
        "labels.get", labels=("INBOX", refused), skip=5
    )  # the final re-read of the first delete attempt
    waiting = rig.gmail.add_label(CANARY + "-waiting")
    rig.store.timer_rows[waiting] = StoredTimer(NOW - timedelta(hours=1), NOW - CYCLE, WAIT)
    rig.gmail.add_label(CANARY + "-fresh")
    caplog.set_level(logging.DEBUG)

    await rig.step.run_once()
    rig.gmail.fail_next(500, times=3)
    rig.now += CYCLE
    await rig.step.run_once()  # a Gmail that fails
    rig.store.state = MigrationState.PENDING
    await rig.step.run_once()  # a gated cycle

    assert deleted not in rig.gmail.label_table
    assert CANARY not in caplog.text
    assert all(CANARY not in text for text in rig.chat.texts)
    assert all(CANARY not in str(record.exc_info) for record in caplog.records)
    assert all(CANARY not in str(row) for row in (rig.store.timer_rows, rig.store.left, rig.store.resort_ids))


# --- criterion 7: a running timer keeps the wait it started with ----------------------------------------------------


async def test_given_a_lowered_wait_when_a_timer_started_with_the_long_one_then_it_keeps_the_long_one() -> None:
    rig = Rig()
    label = rig.gmail.add_label("A1")
    rig.store.timer_rows[label] = StoredTimer(NOW - timedelta(hours=2), NOW - CYCLE, WAIT)  # started with 12 hours
    rig.store.cleanup_settings = CleanupSettings(
        timedelta(minutes=5), timedelta(days=7), timedelta(days=30)
    )  # the user lowered it to 5 minutes

    await rig.step.run_once()

    assert rig.exists(label)  # the lowered wait does not touch a running timer


async def test_given_a_timer_started_with_a_short_wait_when_the_wait_is_raised_then_the_short_one_counts() -> None:
    rig = Rig()
    label = rig.gmail.add_label("A1")
    rig.store.timer_rows[label] = StoredTimer(NOW - timedelta(hours=2), NOW - CYCLE, timedelta(hours=1))

    await rig.step.run_once()

    assert not rig.exists(label)


async def test_given_a_new_timer_when_it_starts_after_the_wait_was_lowered_then_it_has_the_new_wait() -> None:
    rig = Rig()
    rig.store.cleanup_settings = CleanupSettings(timedelta(minutes=5), timedelta(days=7), timedelta(days=30))
    label = rig.empty_label("A1", ripe=False)

    await rig.step.run_once()

    assert rig.store.timer_rows[label].wait == timedelta(minutes=5)


# --- criterion 8: the purge of the records --------------------------------------------------------------------------


async def test_given_a_new_day_when_cycles_run_then_the_records_are_purged_once_a_day() -> None:
    rig = Rig()
    rig.store.purged_counts = (2, 3)

    await rig.step.run_once()
    await rig.step.run_once()
    assert rig.store.purges == 1
    rig.now += timedelta(days=1)
    await rig.step.run_once()

    assert rig.store.purges == 2


async def test_given_a_migration_that_is_not_done_when_a_cycle_runs_then_the_records_are_still_purged() -> None:
    rig = Rig(MigrationState.CONFIRMED)

    await rig.step.run_once()

    assert rig.store.purges == 1


# --- criterion 9: a refusal keeps the timer and the cycle goes on -----


async def test_given_a_refused_delete_when_the_cycle_goes_on_then_the_timer_stays_and_the_next_label_goes() -> None:
    rig = Rig()
    refused = rig.empty_label("Refused", age=WAIT + 4 * CYCLE)
    next_one = rig.empty_label("Next")
    # Two reads in the scan, then the adapter's first read and its final re-read: the mail arrives before the 4th get.
    rig.gmail.inject_mail_before_next("labels.get", labels=("INBOX", refused), skip=3)

    result = await rig.step.run_once()

    assert rig.exists(refused)
    assert refused in rig.store.timer_rows
    assert not rig.exists(next_one)
    assert (result.refused, result.deleted) == (1, 1)


async def test_given_a_gmail_failure_on_the_delete_when_the_cycle_runs_then_it_stops_and_keeps_the_timers() -> None:
    rig = Rig()
    first = rig.empty_label("A1", age=WAIT + 4 * CYCLE)
    second = rig.empty_label("B1")
    rig.gmail.fail_call("labels.delete", 500, times=5)

    result = await rig.step.run_once()

    assert rig.exists(first)
    assert rig.exists(second)
    assert {first, second} <= set(rig.store.timer_rows)
    assert result.deleted == 0


async def test_given_an_unreadable_label_when_the_cycle_runs_then_the_others_are_still_checked() -> None:
    rig = Rig()
    broken = rig.empty_label("Broken", ripe=False)
    fine = rig.empty_label("Fine", ripe=False)
    rig.gmail.fail_call("labels.get", 403, times=1)  # the first read fails

    result = await rig.step.run_once()

    assert fine in rig.store.timer_rows
    assert broken not in rig.store.timer_rows
    assert result.errors == 1


# --- criterion 1: two overlapping cycles ---------------------------------------------------------------------------


class SlowDelete(GmailLabelDelete):
    """The delete call waits until the test lets it go, so that a second cycle can arrive meanwhile."""

    def __init__(self, gmail: FakeGmail) -> None:
        super().__init__(gmail, sleep=lambda _s: None)
        self.entered = threading.Event()
        self.release = threading.Event()

    def delete(self, label_id: str) -> None:
        self.entered.set()
        assert self.release.wait(timeout=10)
        super().delete(label_id)


async def until(condition: Callable[[], bool]) -> None:
    for _ in range(500):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not reached")


async def test_given_two_overlapping_cycles_when_both_run_then_only_one_deletes_and_none_deletes_twice() -> None:
    rig = Rig()
    slow = SlowDelete(rig.gmail)
    label = rig.empty_label("A1")
    first = asyncio.create_task(rig.make(slow).run_once())
    await until(slow.entered.is_set)  # the first cycle holds the lease and is inside the delete call

    second = await rig.make(slow).run_once()  # arrives while the first one is deleting

    assert second.deleted == 0
    assert second.leased_out is True
    slow.release.set()
    done = await first
    assert done.deleted == 1
    assert rig.gmail.calls.count("labels.delete") == 1
    assert not rig.exists(label)


async def test_given_the_lease_is_held_elsewhere_when_a_cycle_runs_then_no_delete_but_timers_still_run() -> None:
    rig = Rig()
    ripe = rig.empty_label("A1")
    fresh = rig.empty_label("B1", ripe=False)
    rig.store.lease_refused = True

    result = await rig.step.run_once()

    assert rig.exists(ripe)
    assert fresh in rig.store.timer_rows
    assert result.leased_out is True


async def test_given_a_label_deleted_by_an_earlier_cycle_when_a_stale_timer_is_read_then_it_is_not_deleted_again() -> (
    None
):
    rig = Rig()
    label = rig.empty_label("A1")
    await rig.step.run_once()
    rig.store.timer_rows[label] = StoredTimer(
        NOW - WAIT - CYCLE, NOW - CYCLE, WAIT
    )  # the stale timer the second one read

    result = await rig.make().run_once()

    assert rig.gmail.calls.count("labels.delete") == 1
    assert result.deleted == 0
