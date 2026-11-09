"""U-quiet-hours-05: the settings store against a real PostgreSQL (ADR-0025; AC-13, AC-21, AC-29, AC-30, AC-33, AC-36)."""

from __future__ import annotations

import asyncio
from datetime import time
from pathlib import Path
from typing import TYPE_CHECKING

import asyncpg
import pytest
from schedule_policy.policy import validate
from schedule_policy.testing import make_policy
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.db.pg_settings_store import PgSettingsStore
from app.db.repos import NothingToUndo, PolicyRefused, StoredSettings, StoredSettingsInvalid, VersionConflict

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from schedule_policy.policy import TimePolicy

GRANTS = Path(__file__).resolve().parents[2] / "app" / "db" / "grants.sql"
RUNTIME_ROLE = "mail_triage_runtime"
RUNTIME_PASSWORD = "runtime-test-only"  # noqa: S105  # a throwaway role inside a throwaway test container


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_url)
    yield engine
    await engine.dispose()


@pytest.fixture
def store(engine: AsyncEngine) -> PgSettingsStore:
    return PgSettingsStore(async_sessionmaker(engine, expire_on_commit=False))


async def test_given_no_row_when_read_then_none_and_when_written_with_version_0_then_version_1(
    store: PgSettingsStore,
) -> None:
    assert await store.read() is None

    policy = make_policy(zone="America/New_York", quiet_start=time(22, 30))
    written = await store.write(policy, 0, "telegram", "u1")

    assert written.version == 1
    assert (written.updated_via, written.updated_by) == ("telegram", "u1")
    assert await store.read() == written
    assert written.policy == policy


async def _audit_count(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        return (await connection.execute(text("select count(*) from settings.settings_change"))).scalar_one()


async def test_given_two_sessions_that_read_the_same_version_when_both_write_then_one_wins_and_one_audit_is_added(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    await store.write(make_policy(), 0, "web", "seed")
    barrier = asyncio.Barrier(2)

    async def writer(quiet_start: time, by: str) -> object:
        seen = await store.read()
        assert seen is not None
        await barrier.wait()  # both have read version 1; neither has written yet
        try:
            return await store.write(make_policy(quiet_start=quiet_start), seen.version, "telegram", by)
        except VersionConflict as conflict:
            return conflict

    outcomes = await asyncio.gather(writer(time(22, 0), "a"), writer(time(21, 0), "b"))

    winners = [o for o in outcomes if isinstance(o, StoredSettings)]
    losers = [o for o in outcomes if isinstance(o, VersionConflict)]
    assert (len(winners), len(losers)) == (1, 1)
    stored = await store.read()
    assert stored == winners[0]
    assert stored.version == 2
    assert validate(stored.policy) == []
    assert await _audit_count(engine) == 2  # the seed and the winner; the loser left nothing


class _NoDatabase:
    """A session factory that fails the test when anything asks it for a session."""

    def __call__(self) -> object:
        raise AssertionError("the database was touched")

    def begin(self) -> object:
        raise AssertionError("the database was touched")


@pytest.mark.parametrize(
    ("policy", "rule"),
    [
        (make_policy(zone="Mars/Olympus"), "zone_unknown"),
        (make_policy(quiet_start=time(22, 0), quiet_end=time(11, 0), remind_at=time(12, 0)), "quiet_window_length"),
        (make_policy(overview_at=time(23, 30)), "overview_in_quiet_hours"),
    ],
)
async def test_given_an_invalid_policy_when_written_then_refused_before_the_database(
    policy: TimePolicy, rule: str
) -> None:
    store = PgSettingsStore(_NoDatabase())  # type: ignore[arg-type]

    with pytest.raises(PolicyRefused) as refused:
        await store.write(policy, 0, "telegram", "u1")

    assert [problem.rule for problem in refused.value.problems] == [rule]


async def test_given_a_stored_row_when_an_invalid_policy_is_written_then_the_row_and_audit_stay(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    first = await store.write(make_policy(), 0, "web", "u1")

    with pytest.raises(PolicyRefused):
        await store.write(make_policy(zone="Mars/Olympus"), first.version, "telegram", "u1")

    assert await store.read() == first
    assert await _audit_count(engine) == 1


async def test_given_an_undo_with_the_current_version_when_run_then_the_previous_values_return_as_an_audited_write(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    before = make_policy()
    first = await store.write(before, 0, "web", "u1")
    second = await store.write(make_policy(zone="America/New_York", quiet_start=time(22, 0)), first.version, "telegram", "u2")

    undone = await store.undo(second.version, "telegram", "u2")

    assert undone.policy == before
    assert undone.version == second.version + 1
    assert await store.read() == undone
    assert await _audit_count(engine) == 3


async def test_given_an_undo_with_an_old_version_when_run_then_version_conflict_and_nothing_changes(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    first = await store.write(make_policy(), 0, "web", "u1")
    second = await store.write(make_policy(quiet_start=time(22, 0)), first.version, "telegram", "u2")
    third = await store.write(make_policy(quiet_start=time(21, 0)), second.version, "web", "u3")

    with pytest.raises(VersionConflict):
        await store.undo(second.version, "telegram", "u2")

    assert await store.read() == third
    assert await _audit_count(engine) == 3


async def test_given_only_the_first_write_when_undone_then_there_is_nothing_to_undo(
    store: PgSettingsStore,
) -> None:
    first = await store.write(make_policy(), 0, "web", "u1")

    with pytest.raises(NothingToUndo):
        await store.undo(first.version, "telegram", "u1")

    assert await store.read() == first


async def test_given_no_row_when_undone_then_version_conflict(store: PgSettingsStore) -> None:
    with pytest.raises(VersionConflict):
        await store.undo(1, "telegram", "u1")


async def test_given_a_stored_row_that_fails_validation_when_read_then_a_clear_error_names_the_rules_only(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    await store.write(make_policy(), 0, "web", "u1")
    async with engine.begin() as connection:  # the zone pattern CHECK lets a well-formed but unknown name through
        await connection.execute(text("update settings.schedule set zone = 'Mars/Olympus'"))

    with pytest.raises(StoredSettingsInvalid) as invalid:
        await store.read()

    assert invalid.value.rules == ("zone_unknown",)
    assert "Olympus" not in str(invalid.value)


@pytest.fixture
async def runtime_store(migrated_url: str) -> AsyncIterator[PgSettingsStore]:
    """A store connected as the runtime role, with the rights of app/db/grants.sql and no others."""
    owner = await asyncpg.connect(migrated_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await owner.execute(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}') THEN "
            f"CREATE ROLE {RUNTIME_ROLE} LOGIN PASSWORD '{RUNTIME_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE; "
            "END IF; END $$"
        )
        await owner.execute(GRANTS.read_text(encoding="utf-8"))
    finally:
        await owner.close()
    url = make_url(migrated_url).set(username=RUNTIME_ROLE, password=RUNTIME_PASSWORD)
    runtime_engine = create_async_engine(url)
    yield PgSettingsStore(async_sessionmaker(runtime_engine, expire_on_commit=False))
    await runtime_engine.dispose()


async def test_given_the_runtime_role_when_it_writes_reads_and_undoes_then_its_grants_are_enough(
    runtime_store: PgSettingsStore,
) -> None:
    first = await runtime_store.write(make_policy(), 0, "telegram", "u1")
    second = await runtime_store.write(make_policy(quiet_start=time(22, 0)), first.version, "telegram", "u1")

    undone = await runtime_store.undo(second.version, "telegram", "u1")

    assert undone.policy == first.policy
    assert await runtime_store.read() == undone


async def test_given_writes_when_they_commit_then_each_adds_exactly_one_audit_record(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    first = await store.write(make_policy(), 0, "web", "u1")
    second = await store.write(make_policy(quiet_start=time(22, 0)), first.version, "telegram", "u2")

    async with engine.connect() as connection:
        rows = (
            await connection.execute(text('select via, by, old, new from settings.settings_change order by (new->>\'version\')::int'))
        ).all()
    assert [(row.via, row.by) for row in rows] == [("web", "u1"), ("telegram", "u2")]
    assert rows[0].old is None
    assert rows[1].old["version"] == first.version
    assert rows[1].old["quiet_start"] == 23 * 60
    assert rows[1].new["version"] == second.version
    assert rows[1].new["quiet_start"] == 22 * 60
