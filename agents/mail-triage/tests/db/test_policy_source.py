"""U-quiet-hours-08: PolicySource with fallback and notice (C-9; AC-1, AC-31, AC-32, AC-33; threat model T-6, T-9)."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, time
from typing import TYPE_CHECKING, TypeVar

import asyncpg
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.db.pg_policy_source import PgPolicySource, SettingsReader
from app.db.pg_settings_store import PgSettingsStore
from app.db.repos import StoredSettings, StoredSettingsInvalid
from app.usecases.policy_notice import PolicyNotice
from schedule_policy.policy import DEFAULT_POLICY, TimePolicy
from schedule_policy.testing import make_policy
from tests.db.conftest import alembic_config

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable

T = TypeVar("T")
RUNTIME_ROLE = "mail_triage_runtime"
RUNTIME_PASSWORD = "runtime-test-only"  # noqa: S105  # a throwaway role inside a throwaway test container


class FakeNotifier:
    """Marco's Telegram chat: keeps every note sent."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def say(self, text: str) -> None:
        self.sent.append(text)


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> PgSettingsStore:
    return PgSettingsStore(async_sessionmaker(engine, expire_on_commit=False))


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def source(store: PgSettingsStore, notifier: FakeNotifier) -> PgPolicySource:
    return PgPolicySource(store, PolicyNotice(notifier))


async def test_given_a_stored_valid_row_when_read_then_its_policy_is_returned(
    store: PgSettingsStore, source: PgPolicySource, notifier: FakeNotifier
) -> None:
    stored = make_policy(zone="America/New_York", quiet_start=time(22, 30))
    await store.write(stored, 0, "telegram", "u1")

    assert await source.current() == stored
    assert notifier.sent == []


async def test_given_no_row_when_read_then_the_default_policy_and_no_notice(
    source: PgPolicySource, notifier: FakeNotifier
) -> None:
    assert await source.current() == DEFAULT_POLICY
    assert notifier.sent == []


# Statements that make the stored row break a rule. The constraints of migration 0004 keep most of these out of a
# healthy database, so each case first lifts the constraint it needs (as an operator with owner rights could).
_CORRUPTIONS = {
    "unknown_zone": ["update settings.schedule set zone = 'Mars/Olympus'"],
    "window_of_13_hours": [
        "alter table settings.schedule drop constraint ck_schedule_window_length",
        "alter table settings.schedule drop constraint ck_schedule_overview_outside",
        "alter table settings.schedule drop constraint ck_schedule_remind_outside",
        "update settings.schedule set quiet_start = 22 * 60, quiet_end = 11 * 60",
    ],
    "overview_inside_the_window": [
        "alter table settings.schedule drop constraint ck_schedule_overview_outside",
        "update settings.schedule set overview_at = 23 * 60 + 30",
    ],
    "null_value": [
        "alter table settings.schedule alter column remind_at drop not null",
        "update settings.schedule set remind_at = null",
    ],
}
GOOD = make_policy(zone="America/New_York", quiet_start=time(22, 30), quiet_end=time(6, 30), overview_at=time(17, 15))


async def _corrupt(engine: AsyncEngine, case: str) -> None:
    async with engine.begin() as connection:
        for statement in _CORRUPTIONS[case]:
            await connection.execute(text(statement))


@pytest.mark.parametrize("case", list(_CORRUPTIONS))
@pytest.mark.parametrize("had_good_read", [False, True])
async def test_given_an_invalid_stored_row_when_read_then_last_good_or_default_one_notice_and_log(  # noqa: PLR0913, PLR0917
    case: str,
    had_good_read: bool,
    store: PgSettingsStore,
    engine: AsyncEngine,
    source: PgPolicySource,
    notifier: FakeNotifier,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    await store.write(GOOD, 0, "telegram", "u1")
    if had_good_read:
        assert await source.current() == GOOD
    await _corrupt(engine, case)

    first = await source.current()
    second = await source.current()

    expected = GOOD if had_good_read else DEFAULT_POLICY
    assert (first, second) == (expected, expected)
    assert len(notifier.sent) == 1
    assert expected.zone in notifier.sent[0]
    assert any("settings_invalid" in record.getMessage() for record in caplog.records)
    assert "Olympus" not in caplog.text


# ---- criterion 3: the database cannot answer -----------------------------------------------------------------------


class SlowStore:
    """A settings store whose read takes longer than any deadline."""

    async def read(self) -> StoredSettings | None:
        await asyncio.Event().wait()
        return None


class RefusingStore:
    """A settings store whose connection is refused. A real closed port is no use here: on Windows the refusal only
    arrives after the connect attempt has timed out, which would test the timeout instead.
    """

    async def read(self) -> StoredSettings | None:
        raise ConnectionRefusedError(10061, "refused postgresql://nobody:nothing@127.0.0.1:1/none")


class RecordingDeadline:
    """The real ``asyncio.wait_for``, remembering the deadline it was given so a test can check the 2 s."""

    def __init__(self) -> None:
        self.seconds: list[float] = []

    async def __call__(self, awaitable: Awaitable[T], seconds: float) -> T:
        self.seconds.append(seconds)
        return await asyncio.wait_for(awaitable, seconds)


class FakeDeadline(RecordingDeadline):
    """Stands in for ``asyncio.wait_for`` with no real waiting: the read gets a few loop turns; if it is not done by
    then it counts as slower than the deadline.
    """

    async def __call__(self, awaitable: Awaitable[T], seconds: float) -> T:
        self.seconds.append(seconds)
        task = asyncio.ensure_future(awaitable)
        for _ in range(10):
            await asyncio.sleep(0)
        if task.done():
            return task.result()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise TimeoutError


def _runtime_role_without_grants_url(migrated_url: str) -> str:
    url = make_url(migrated_url).set(username=RUNTIME_ROLE, password=RUNTIME_PASSWORD)
    return url.render_as_string(hide_password=False)


async def _create_runtime_role(url: str) -> None:
    owner = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await owner.execute(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}') THEN "
            f"CREATE ROLE {RUNTIME_ROLE} LOGIN PASSWORD '{RUNTIME_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE; "
            "END IF; END $$"
        )
    finally:
        await owner.close()


@pytest.fixture
async def broken_store(request: pytest.FixtureRequest, database_url: str) -> AsyncIterator[SettingsReader]:
    """A store that fails in the way named by the test parameter, against a real PostgreSQL where one is needed."""
    kind: str = request.param
    urls = {"missing_table": database_url}  # a database no migration has run on
    if kind == "connection_refused":
        yield RefusingStore()
        return
    if kind == "permission_denied":
        await asyncio.to_thread(command.upgrade, alembic_config(database_url), "head")  # env.py runs its own loop
        await _create_runtime_role(database_url)
        urls[kind] = _runtime_role_without_grants_url(database_url)  # a role with no grants on the settings schema
    if kind == "timeout":
        yield SlowStore()
        return
    engine = create_async_engine(urls[kind])
    yield PgSettingsStore(async_sessionmaker(engine, expire_on_commit=False))
    await engine.dispose()


# What the log must name: the error class (or the SQLSTATE the database gave) and never a value.
_LOGGED = {
    "connection_refused": ["ConnectionRefusedError"],
    "missing_table": ["UndefinedTableError", "sqlstate=42P01"],
    "permission_denied": ["InsufficientPrivilegeError", "sqlstate=42501"],
    "timeout": ["TimeoutError"],
}


@pytest.mark.parametrize("broken_store", list(_LOGGED), indirect=True)
async def test_given_a_database_that_cannot_answer_when_read_then_the_fallback_and_the_class_logged(
    broken_store: SettingsReader,
    notifier: FakeNotifier,
    caplog: pytest.LogCaptureFixture,
    request: pytest.FixtureRequest,
) -> None:
    caplog.set_level(logging.DEBUG)
    request_kind: str = request.node.callspec.params["broken_store"]
    deadline = FakeDeadline() if request_kind == "timeout" else RecordingDeadline()
    source = PgPolicySource(broken_store, PolicyNotice(notifier), deadline)

    first = await source.current()
    second = await source.current()

    assert (first, second) == (DEFAULT_POLICY, DEFAULT_POLICY)
    assert deadline.seconds == [2.0, 2.0]
    assert len(notifier.sent) == 1
    assert DEFAULT_POLICY.zone in notifier.sent[0]
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert all(expected in logged for expected in _LOGGED[request_kind]), logged
    assert "settings_invalid" not in logged
    assert "nothing" not in caplog.text  # the password inside the refused connection's error text


# ---- criteria 4, 5, 6: last good, canary, one notice per incident -------------------------------------------------


async def test_given_a_good_read_then_a_corrupted_row_when_read_then_the_first_values_and_a_fresh_process_the_defaults(
    store: PgSettingsStore, engine: AsyncEngine, source: PgPolicySource, notifier: FakeNotifier
) -> None:
    await store.write(GOOD, 0, "telegram", "u1")
    assert await source.current() == GOOD
    await _corrupt(engine, "unknown_zone")

    assert await source.current() == GOOD

    fresh_process = PgPolicySource(store, PolicyNotice(notifier))
    assert await fresh_process.current() == DEFAULT_POLICY


CANARY = "Pacific/Kiritimati"
BOT_TOKEN = "123456789:AAH-secret_token_value"  # noqa: S105  # a made-up token shape for the redaction check


class FailingNotifier:
    """Telegram is down; its error text carries the bot token, as an HTTP library's does inside the request URL."""

    async def say(self, text: str) -> None:
        raise RuntimeError(f"POST https://api.telegram.org/bot{BOT_TOKEN}/sendMessage failed")


@pytest.mark.parametrize("case", ["unknown_zone", "window_of_13_hours", "overview_inside_the_window", "null_value"])
async def test_given_a_canary_zone_when_corrupted_and_fallen_back_then_no_log_shows_it_but_the_notice_does(
    case: str,
    store: PgSettingsStore,
    engine: AsyncEngine,
    notifier: FakeNotifier,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    source = PgPolicySource(store, PolicyNotice(notifier))
    await store.write(make_policy(zone=CANARY), 0, "telegram", "u1")
    assert (await source.current()).zone == CANARY
    await _corrupt(engine, case)  # the stored row still holds the canary zone in three of the four cases

    assert (await source.current()).zone == CANARY

    assert CANARY in notifier.sent[0]  # Marco must be told what is in use; the notice goes to Telegram, not the log
    assert caplog.records
    for record in caplog.records:
        everything = f"{record.getMessage()} {record.args} {record.exc_text} {record.__dict__}"
        assert "Kiritimati" not in everything
    assert "Kiritimati" not in caplog.text


async def test_given_telegram_is_down_when_the_notice_fails_then_the_read_still_answers_and_no_token_is_logged(
    store: PgSettingsStore, engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    source = PgPolicySource(store, PolicyNotice(FailingNotifier()))
    await store.write(GOOD, 0, "telegram", "u1")
    await source.current()
    await _corrupt(engine, "unknown_zone")

    assert await source.current() == GOOD

    assert "policy_notice_failed" in caplog.text
    assert BOT_TOKEN not in caplog.text
    assert "secret_token_value" not in caplog.text


class ScriptedStore:
    """A settings store that answers each read with the next item of the script: a row, None, or an error to raise."""

    def __init__(self, *script: StoredSettings | Exception | None) -> None:
        self._script = list(script)

    async def read(self) -> StoredSettings | None:
        outcome = self._script.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _row(policy: TimePolicy = DEFAULT_POLICY) -> StoredSettings:
    return StoredSettings(policy, 1, datetime(2026, 1, 1, tzinfo=UTC), "telegram", "u1")


async def test_given_an_incident_over_several_reads_when_it_persists_then_one_notice_until_it_recovers() -> None:
    notifier = FakeNotifier()
    invalid = StoredSettingsInvalid(("zone_unknown",))
    store = ScriptedStore(invalid, invalid, TimeoutError(), invalid, _row(), invalid, invalid)
    source = PgPolicySource(store, PolicyNotice(notifier))

    for _ in range(4):  # the incident goes on, with two kinds of fault
        await source.current()
    assert len(notifier.sent) == 1

    await source.current()  # recovery
    assert len(notifier.sent) == 1

    await source.current()  # a new incident
    await source.current()
    assert len(notifier.sent) == 2


async def test_given_reads_that_fail_at_the_same_moment_when_they_run_together_then_one_notice() -> None:
    notifier = FakeNotifier()
    invalid = StoredSettingsInvalid(("zone_unknown",))
    source = PgPolicySource(ScriptedStore(*[invalid] * 5), PolicyNotice(notifier))

    await asyncio.gather(*(source.current() for _ in range(5)))

    assert len(notifier.sent) == 1


async def test_given_a_notice_that_could_not_be_sent_when_the_next_read_fails_then_it_is_tried_again() -> None:
    class FlakyNotifier(FakeNotifier):
        async def say(self, text: str) -> None:
            if not self.sent and not hasattr(self, "tried"):
                self.tried = True
                raise ConnectionError
            await super().say(text)

    notifier = FlakyNotifier()
    invalid = StoredSettingsInvalid(("zone_unknown",))
    source = PgPolicySource(ScriptedStore(invalid, invalid, invalid), PolicyNotice(notifier))

    for _ in range(3):
        await source.current()

    assert len(notifier.sent) == 1


async def test_given_a_row_deleted_after_a_good_read_when_read_then_the_defaults_without_a_notice() -> None:
    notifier = FakeNotifier()
    source = PgPolicySource(ScriptedStore(_row(GOOD), None), PolicyNotice(notifier))

    assert await source.current() == GOOD
    assert await source.current() == DEFAULT_POLICY
    assert notifier.sent == []
