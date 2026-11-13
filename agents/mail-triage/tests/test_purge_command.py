"""U-web-settings-49: ``python -m app purge`` and the exit code of a failing step (AC-21)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app import wiring
from app.db.migrate import MigrationStepFailed
from app.db.purge import PurgeCounts
from app.main import EXIT_BAD_CONFIG, EXIT_OK, main
from app.settings import load_migrate_settings
from app.wiring import EXIT_MIGRATION_FAILED
from schedule_policy.testing import FakeClock
from tests.test_main_commands import Spy
from tests.test_migrate_settings import MIGRATE_VALID

if TYPE_CHECKING:
    import pytest

SECRET_URL = "postgresql+asyncpg://owner:owner-test-secret@db:5432/mail"  # noqa: S105  # a test value, never a real one


def test_given_the_purge_command_when_the_owner_values_are_set_then_only_purge_runs() -> None:
    spy, other = Spy(), Spy()

    assert main(MIGRATE_VALID, serve=other.serve, migrate=other.migrate, purge=spy.migrate, argv=["purge"]) == EXIT_OK

    assert len(spy.calls) == 1
    assert other.calls == []


def test_given_the_purge_command_when_the_owner_url_is_missing_then_it_fails_and_never_connects() -> None:
    spy = Spy()
    env = {key: value for key, value in MIGRATE_VALID.items() if key != "DATABASE_OWNER_URL"}

    assert main(env, purge=spy.migrate, argv=["purge"]) == EXIT_BAD_CONFIG
    assert spy.calls == []


async def test_given_a_failing_purge_step_when_the_migrate_command_runs_then_it_exits_non_zero_naming_the_step(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def failing(*args: object, **kwargs: object) -> None:
        raise MigrationStepFailed("purge")

    monkeypatch.setattr(wiring, "migrate_database", failing)

    with caplog.at_level(logging.ERROR):
        code = await wiring.migrate(load_migrate_settings(MIGRATE_VALID))

    assert code == EXIT_MIGRATION_FAILED
    assert "purge" in caplog.text
    assert "owner-test-secret" not in caplog.text


async def test_given_the_purge_command_when_it_runs_then_it_purges_with_the_clock_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[object] = []

    async def fake(owner_url: str, tls: object, clock: object) -> PurgeCounts:
        seen.append((owner_url, clock))
        return PurgeCounts(0, 0, 0, 0)

    monkeypatch.setattr(wiring, "purge_database", fake)
    clock = FakeClock()

    code = await wiring.purge(load_migrate_settings(MIGRATE_VALID), clock)

    assert code == EXIT_OK
    assert seen == [(SECRET_URL, clock)]


async def test_given_a_failing_purge_command_when_it_runs_then_it_exits_non_zero_without_the_url(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def failing(owner_url: str, tls: object, clock: object) -> PurgeCounts:
        raise ConnectionError(owner_url)

    monkeypatch.setattr(wiring, "purge_database", failing)

    with caplog.at_level(logging.ERROR):
        code = await wiring.purge(load_migrate_settings(MIGRATE_VALID))

    assert code == EXIT_MIGRATION_FAILED
    assert "purge" in caplog.text
    assert "owner-test-secret" not in caplog.text
