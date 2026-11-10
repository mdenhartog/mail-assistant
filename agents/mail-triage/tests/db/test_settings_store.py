"""U-quiet-hours-05: the settings store on a real PostgreSQL (ADR-0025; AC-13, AC-21, AC-29, AC-30, AC-33, AC-36)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import traceback
from dataclasses import replace
from datetime import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.db.pg_settings_store import PgSettingsStore
from app.db.repos import (
    NothingToUndo,
    PolicyRefused,
    SettingsStoreFailure,
    SettingsView,
    StoredSettings,
    StoredSettingsInvalid,
    VersionConflict,
)
from schedule_policy.policy import TimePolicy, validate
from schedule_policy.testing import make_policy

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Coroutine

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
    second = await store.write(
        make_policy(zone="America/New_York", quiet_start=time(22, 0)), first.version, "telegram", "u2"
    )

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


async def test_given_previous_values_that_no_longer_validate_when_undone_then_refused_and_nothing_changes(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    first = await store.write(make_policy(), 0, "web", "u1")
    second = await store.write(make_policy(quiet_start=time(22, 0)), first.version, "web", "u1")
    async with engine.begin() as connection:  # as if the tz database had dropped the old zone
        await connection.execute(
            text(
                "update settings.settings_change set old = jsonb_set(old, '{zone}', '\"Mars/Olympus\"') "
                "where old is not null"
            )
        )

    with pytest.raises(PolicyRefused):
        await store.undo(second.version, "telegram", "u1")

    assert await store.read() == second


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


async def test_given_a_stored_row_with_a_null_value_when_read_then_it_is_an_invalid_row_not_a_type_error(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    await store.write(make_policy(), 0, "web", "u1")
    async with engine.begin() as connection:  # lift the NOT NULL as an operator with owner rights could
        await connection.execute(text("alter table settings.schedule alter column remind_at drop not null"))
        await connection.execute(text("update settings.schedule set remind_at = null"))

    with pytest.raises(StoredSettingsInvalid) as invalid:
        await store.read()

    assert invalid.value.rules == ("value_missing",)


async def test_given_a_valid_row_when_read_for_the_dialogue_then_version_and_policy_are_returned(
    store: PgSettingsStore,
) -> None:
    assert await store.read_for_dialogue() == SettingsView(0, None)
    policy = make_policy(quiet_start=time(22, 30))
    await store.write(policy, 0, "web", "u1")

    assert await store.read_for_dialogue() == SettingsView(1, policy)


async def test_given_an_invalid_row_when_read_for_the_dialogue_then_its_version_and_rules_come_back_without_values(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    await store.write(make_policy(), 0, "web", "u1")
    async with engine.begin() as connection:
        await connection.execute(text("update settings.schedule set zone = 'Mars/Olympus'"))

    view = await store.read_for_dialogue()

    assert view == SettingsView(1, None, ("zone_unknown",))
    assert "Olympus" not in repr(view)


async def test_given_an_invalid_row_when_written_over_at_its_version_then_a_whole_new_valid_row_is_stored(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    await store.write(make_policy(), 0, "web", "u1")
    async with engine.begin() as connection:
        await connection.execute(text("update settings.schedule set zone = 'Mars/Olympus'"))
    version = (await store.read_for_dialogue()).version

    written = await store.write(make_policy(zone="Europe/Paris"), version, "telegram", "u1")

    assert written.version == version + 1
    assert await store.read() == written


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


_FAIL_AT_COMMIT = """
CREATE FUNCTION public.fail_at_commit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'injected fault at commit'; END $$;
CREATE CONSTRAINT TRIGGER fail_at_commit AFTER INSERT OR UPDATE ON settings.schedule
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.fail_at_commit();
"""


async def _inject_commit_fault(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        raw = await connection.get_raw_connection()
        await raw.driver_connection.execute(_FAIL_AT_COMMIT)  # type: ignore[union-attr]


async def test_given_a_fault_after_validation_when_a_first_write_commits_then_nothing_is_stored(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    await _inject_commit_fault(engine)

    with pytest.raises(SettingsStoreFailure):
        await store.write(make_policy(), 0, "telegram", "u1")

    assert await store.read() is None
    assert await _audit_count(engine) == 0


async def test_given_a_fault_after_validation_when_an_update_commits_then_row_and_audit_are_unchanged(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    first = await store.write(make_policy(), 0, "web", "u1")
    second = await store.write(make_policy(quiet_start=time(22, 0)), first.version, "web", "u1")
    await _inject_commit_fault(engine)

    with pytest.raises(SettingsStoreFailure):
        await store.write(make_policy(quiet_start=time(21, 0)), second.version, "telegram", "u1")
    with pytest.raises(SettingsStoreFailure):
        await store.undo(second.version, "telegram", "u1")

    assert await store.read() == second
    assert await _audit_count(engine) == 2


CASES_FILE = Path(__file__).resolve().parents[4] / "packages" / "schedule-policy" / "contract" / "settings_cases.json"
CASES: list[dict[str, Any]] = json.loads(CASES_FILE.read_text("utf-8"))["cases"]
# Rules the migration's CHECK constraints also enforce; the rest (known zone, whole minutes, no offset) need code.
DATABASE_RULES = {"quiet_window_empty", "quiet_window_length", "overview_in_quiet_hours", "remind_in_quiet_hours"}


def _contract_policy(raw: dict[str, str]) -> TimePolicy:
    return TimePolicy(
        zone=raw["zone"],
        quiet_start=time.fromisoformat(raw["quiet_start"]),
        quiet_end=time.fromisoformat(raw["quiet_end"]),
        overview_at=time.fromisoformat(raw["overview_at"]),
        remind_at=time.fromisoformat(raw["remind_at"]),
    )


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
async def test_given_a_contract_case_when_written_through_the_store_then_the_outcome_matches_the_package(
    case: dict[str, Any], store: PgSettingsStore
) -> None:
    policy = _contract_policy(case["policy"])

    if case["rules"]:
        with pytest.raises(PolicyRefused) as refused:
            await store.write(policy, 0, "web", "u1")
        assert [problem.rule for problem in refused.value.problems] == case["rules"]
        assert await store.read() is None
    else:
        written = await store.write(policy, 0, "web", "u1")
        assert written.policy == policy
        assert await store.read() == written


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
async def test_given_a_contract_case_when_inserted_as_minutes_then_the_database_checks_agree_where_they_can(
    case: dict[str, Any], engine: AsyncEngine
) -> None:
    rules = set(case["rules"])
    if rules - DATABASE_RULES and rules != {"zone_unknown"}:
        pytest.skip("malformed times cannot be stored as minutes")
    raw = case["policy"]

    def minutes(text_value: str) -> int:
        clock = time.fromisoformat(text_value)
        return clock.hour * 60 + clock.minute

    statement = text(
        "insert into settings.schedule (id, zone, quiet_start, quiet_end, overview_at, remind_at, updated_via, "
        "updated_by) values (1, :zone, :qs, :qe, :ov, :rm, 'web', 'u1')"
    )
    params = {
        "zone": raw["zone"],
        "qs": minutes(raw["quiet_start"]),
        "qe": minutes(raw["quiet_end"]),
        "ov": minutes(raw["overview_at"]),
        "rm": minutes(raw["remind_at"]),
    }
    zone_shape_ok = re.fullmatch(r"[A-Za-z_]+(/[A-Za-z0-9_+-]+){0,2}", raw["zone"]) is not None
    # A well-formed but unknown zone name is beyond SQL (ADR-0025): the database lets it through, validate refuses it.
    expected_accepted = (not (rules & DATABASE_RULES)) and zone_shape_ok

    try:
        async with engine.begin() as connection:
            await connection.execute(statement, params)
    except IntegrityError:
        assert not expected_accepted
    else:
        assert expected_accepted


CANARY = "Pacific/Kiritimati"


def _everything_said_about(error: BaseException) -> str:
    """What any logger could print about an error: message, repr and the full traceback chain."""
    return "\n".join([str(error), repr(error), "".join(traceback.format_exception(error))])


async def test_given_the_canary_zone_when_every_failure_path_is_logged_then_no_record_holds_the_zone(
    store: PgSettingsStore, engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    logger = logging.getLogger("test.settings")
    canary = make_policy(zone=CANARY, quiet_start=time(22, 0))
    first = await store.write(canary, 0, "telegram", "u1")
    errors: list[BaseException] = []

    async def attempt(call: Coroutine[Any, Any, object]) -> None:
        try:
            await call
        except (VersionConflict, PolicyRefused, NothingToUndo, SettingsStoreFailure) as error:
            errors.append(error)
            logger.exception("settings write failed: %s", error)

    await attempt(store.write(canary, 0, "telegram", "u1"))  # conflict: a row exists
    await attempt(store.write(replace(canary, overview_at=time(23, 0)), first.version, "telegram", "u1"))  # refused
    await attempt(store.undo(first.version, "telegram", "u1"))  # nothing to undo
    async with engine.begin() as connection:  # a statement that fails: its error text carries the bound parameters
        await connection.execute(
            text("alter table settings.schedule add constraint ck_fault check (version < 2) not valid")
        )
    await attempt(store.write(replace(canary, quiet_start=time(21, 0)), first.version, "telegram", "u1"))  # fault

    assert {type(error) for error in errors} == {VersionConflict, PolicyRefused, NothingToUndo, SettingsStoreFailure}
    assert CANARY not in caplog.text
    assert all(CANARY not in _everything_said_about(error) for error in errors)
    assert all("Kiritimati" not in record.getMessage() for record in caplog.records)


async def test_given_writes_when_they_commit_then_each_adds_exactly_one_audit_record(
    store: PgSettingsStore, engine: AsyncEngine
) -> None:
    first = await store.write(make_policy(), 0, "web", "u1")
    second = await store.write(make_policy(quiet_start=time(22, 0)), first.version, "telegram", "u2")

    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text("select via, by, old, new from settings.settings_change order by (new->>'version')::int")
            )
        ).all()
    assert [(row.via, row.by) for row in rows] == [("web", "u1"), ("telegram", "u2")]
    assert rows[0].old is None
    assert rows[1].old["version"] == first.version
    assert rows[1].old["quiet_start"] == 23 * 60
    assert rows[1].new["version"] == second.version
    assert rows[1].new["quiet_start"] == 22 * 60


# ---- U-quiet-hours-05b: a database fault on read is a SettingsStoreFailure, never the raw driver error --------------


async def _no_grants_store(migrated_url: str) -> tuple[PgSettingsStore, AsyncEngine]:
    """A store connected as a role that exists but has no rights on the settings schema."""
    owner = await asyncpg.connect(migrated_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await owner.execute(
            f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}') THEN "
            f"CREATE ROLE {RUNTIME_ROLE} LOGIN PASSWORD '{RUNTIME_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE; "
            "END IF; END $$"
        )
        await owner.execute(f"REVOKE ALL ON SCHEMA settings FROM {RUNTIME_ROLE}")
    finally:
        await owner.close()
    url = make_url(migrated_url).set(username=RUNTIME_ROLE, password=RUNTIME_PASSWORD)
    no_grants_engine = create_async_engine(url)
    return PgSettingsStore(async_sessionmaker(no_grants_engine, expire_on_commit=False)), no_grants_engine


async def _read_fault(
    kind: str, store: PgSettingsStore, engine: AsyncEngine, migrated_url: str
) -> SettingsStoreFailure:
    """Store a canary zone, break the database the way ``kind`` names, and read."""
    await store.write(make_policy(zone=CANARY, quiet_start=time(22, 0)), 0, "telegram", "u1")
    broken, to_dispose = store, None
    if kind == "missing_table":
        async with engine.begin() as connection:
            await connection.execute(text("alter table settings.schedule rename to schedule_gone"))
    else:
        broken, to_dispose = await _no_grants_store(migrated_url)
    try:
        with pytest.raises(SettingsStoreFailure) as raised:
            await broken.read()
    finally:
        if to_dispose is not None:
            await to_dispose.dispose()
    return raised.value


_READ_FAULTS = {
    "missing_table": ("UndefinedTableError", "42P01"),
    "permission_denied": ("InsufficientPrivilegeError", "42501"),
}


@pytest.mark.parametrize("kind", list(_READ_FAULTS))
async def test_given_a_database_fault_when_read_then_a_store_failure_names_class_and_sqlstate_only(
    kind: str, store: PgSettingsStore, engine: AsyncEngine, migrated_url: str
) -> None:
    failure = await _read_fault(kind, store, engine, migrated_url)

    assert (failure.cause_class, failure.sqlstate) == _READ_FAULTS[kind]


async def test_given_a_pooled_connection_the_server_has_closed_when_read_then_a_store_failure_without_the_text(
    store: PgSettingsStore, engine: AsyncEngine, migrated_url: str
) -> None:
    await store.write(make_policy(zone=CANARY, quiet_start=time(22, 0)), 0, "telegram", "u1")
    assert await store.read() is not None  # the connection is now in the pool
    admin = await asyncpg.connect(migrated_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await admin.execute(
            "select pg_terminate_backend(pid) from pg_stat_activity "
            "where pid <> pg_backend_pid() and datname = current_database()"
        )
    finally:
        await admin.close()

    with pytest.raises(SettingsStoreFailure) as raised:
        await store.read()

    said = _everything_said_about(raised.value)
    assert "Kiritimati" not in said
    assert "SELECT" not in said
    assert raised.value.cause_class


@pytest.mark.parametrize("kind", list(_READ_FAULTS))
async def test_given_a_database_fault_when_read_then_no_sql_parameter_or_zone_is_in_the_error_or_the_log(
    kind: str, store: PgSettingsStore, engine: AsyncEngine, migrated_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    failure = await _read_fault(kind, store, engine, migrated_url)
    logging.getLogger("test.settings").error("settings read failed: %s", failure, exc_info=failure)

    said = _everything_said_about(failure) + caplog.text
    for forbidden in (CANARY, "Kiritimati", "SELECT", "FROM settings", "parameters", "schedule"):
        assert forbidden not in said, forbidden
    assert failure.__cause__ is None
    assert failure.__suppress_context__
