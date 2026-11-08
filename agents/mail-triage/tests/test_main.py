"""U-01: the agent refuses to start with a broken configuration and never prints a secret (AC-24)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.main import EXIT_BAD_CONFIG, EXIT_OK, main
from tests.test_settings import VALID

if TYPE_CHECKING:
    import pytest


def test_given_valid_configuration_when_the_app_starts_then_it_exits_ok(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(VALID) == EXIT_OK

    captured = capsys.readouterr()
    assert not any(value in captured.out + captured.err for value in VALID.values())


def test_given_a_missing_secret_when_the_app_starts_then_it_refuses_and_names_only_the_key(
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = {key: value for key, value in VALID.items() if key != "ANTHROPIC_API_KEY"}

    assert main(env) == EXIT_BAD_CONFIG

    captured = capsys.readouterr()
    assert "ANTHROPIC_API_KEY" in captured.err
    assert not any(value in captured.out + captured.err for value in VALID.values())
