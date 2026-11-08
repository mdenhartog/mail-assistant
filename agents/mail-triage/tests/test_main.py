"""U-01: the agent refuses to start with a broken configuration and never prints a secret (AC-24)."""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

from app.main import EXIT_BAD_CONFIG, EXIT_OK, main
from tests.test_settings import VALID

if TYPE_CHECKING:
    import pytest

    from app.settings import Settings


async def _never(settings: Settings) -> int:
    raise AssertionError("the agent must not start with a broken configuration")


def test_given_valid_configuration_when_the_app_starts_then_it_runs_the_agent_and_exits_ok(
    capsys: pytest.CaptureFixture[str],
) -> None:
    started: list[Settings] = []

    async def fake_serve(settings: Settings) -> int:
        started.append(settings)
        return EXIT_OK

    assert main(VALID, serve=fake_serve) == EXIT_OK

    assert len(started) == 1
    captured = capsys.readouterr()
    assert not any(value in captured.out + captured.err for value in VALID.values())


def test_given_a_running_agent_when_a_secret_reaches_a_log_then_it_is_scrubbed() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logging.getLogger().addHandler(handler)

    async def fake_serve(settings: Settings) -> int:
        del settings
        logging.getLogger("app.test").warning("leaked %s and %s", VALID["ANTHROPIC_API_KEY"], VALID["DATABASE_URL"])
        return EXIT_OK

    try:
        main(VALID, serve=fake_serve)
    finally:
        logging.getLogger().removeHandler(handler)

    assert "leaked" in stream.getvalue()
    assert VALID["ANTHROPIC_API_KEY"] not in stream.getvalue()
    assert "db-test-secret" not in stream.getvalue()


def test_given_the_agent_stops_with_a_code_when_the_app_ends_then_that_code_is_the_exit_code() -> None:
    async def locked(settings: Settings) -> int:
        del settings
        return 4

    assert main(VALID, serve=locked) == 4


def test_given_a_broken_configuration_when_the_app_starts_then_the_agent_is_never_started() -> None:
    called: list[bool] = []

    async def fake_serve(settings: Settings) -> int:
        called.append(True)
        del settings
        return EXIT_OK

    assert main({}, serve=fake_serve) == EXIT_BAD_CONFIG
    assert called == []


def test_given_a_missing_secret_when_the_app_starts_then_it_refuses_and_names_only_the_key(
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {key: value for key, value in VALID.items() if key != "ANTHROPIC_API_KEY"}

    assert main(env, serve=_never) == EXIT_BAD_CONFIG

    captured = capsys.readouterr()
    assert "ANTHROPIC_API_KEY" in captured.err
    assert not any(value in captured.out + captured.err for value in VALID.values())
