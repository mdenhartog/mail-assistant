"""U-quiet-hours-15a: ``python -m app`` has two commands, ``serve`` (default) and ``migrate`` (ADR-0025)."""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

from app.main import EXIT_BAD_CONFIG, EXIT_OK, main
from tests.test_migrate_settings import MIGRATE_VALID
from tests.test_settings import VALID

if TYPE_CHECKING:
    import pytest

    from app.settings import MigrateSettings, Settings


class Spy:
    def __init__(self, code: int = EXIT_OK) -> None:
        self.calls: list[object] = []
        self.code = code

    async def serve(self, settings: Settings) -> int:
        self.calls.append(settings)
        return self.code

    async def migrate(self, settings: MigrateSettings) -> int:
        self.calls.append(settings)
        return self.code


def test_given_no_command_when_the_app_starts_then_it_serves_and_does_not_migrate() -> None:
    spy, other = Spy(), Spy()

    assert main(VALID, serve=spy.serve, migrate=other.migrate, argv=[]) == EXIT_OK

    assert len(spy.calls) == 1
    assert other.calls == []


def test_given_the_migrate_command_when_the_owner_values_are_set_then_only_migrate_runs() -> None:
    spy, other = Spy(), Spy()

    assert main(MIGRATE_VALID, serve=other.serve, migrate=spy.migrate, argv=["migrate"]) == EXIT_OK

    assert len(spy.calls) == 1
    assert other.calls == []


def test_given_the_migrate_command_when_the_agent_settings_are_absent_then_it_still_runs() -> None:
    spy = Spy()

    assert main(MIGRATE_VALID, serve=Spy().serve, migrate=spy.migrate, argv=["migrate"]) == EXIT_OK


def test_given_a_missing_owner_url_when_migrate_starts_then_it_fails_naming_the_key_and_never_connects(
    capsys: pytest.CaptureFixture[str],
) -> None:
    spy = Spy()
    env = {**VALID, "RUNTIME_ROLE_PASSWORD": MIGRATE_VALID["RUNTIME_ROLE_PASSWORD"]}

    assert main(env, serve=Spy().serve, migrate=spy.migrate, argv=["migrate"]) == EXIT_BAD_CONFIG

    err = capsys.readouterr().err
    assert "DATABASE_OWNER_URL" in err
    assert not any(value in err for value in {**VALID, **MIGRATE_VALID}.values())
    assert spy.calls == []


def test_given_the_serve_command_when_the_owner_url_is_in_the_environment_then_the_agent_never_receives_it() -> None:
    spy = Spy()

    main({**VALID, **MIGRATE_VALID}, serve=spy.serve, migrate=Spy().migrate, argv=["serve"])

    assert "owner-test-secret" not in repr(spy.calls[0])
    assert not hasattr(spy.calls[0], "database_owner_url")


def test_given_an_unknown_command_when_the_app_starts_then_it_refuses_with_a_usage_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    spy = Spy()

    assert main(VALID, serve=spy.serve, migrate=spy.migrate, argv=["drop-everything"]) == EXIT_BAD_CONFIG

    assert "serve" in capsys.readouterr().err
    assert spy.calls == []


def test_given_the_migrate_command_when_a_secret_reaches_a_log_then_it_is_scrubbed() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logging.getLogger().addHandler(handler)

    async def leaky(settings: MigrateSettings) -> int:
        del settings
        logging.getLogger("app.test").warning(
            "leaked %s and %s", MIGRATE_VALID["DATABASE_OWNER_URL"], MIGRATE_VALID["RUNTIME_ROLE_PASSWORD"]
        )
        return EXIT_OK

    try:
        main(MIGRATE_VALID, migrate=leaky, argv=["migrate"])
    finally:
        logging.getLogger().removeHandler(handler)

    assert "leaked" in stream.getvalue()
    assert "owner-test-secret" not in stream.getvalue()
    assert MIGRATE_VALID["RUNTIME_ROLE_PASSWORD"] not in stream.getvalue()
