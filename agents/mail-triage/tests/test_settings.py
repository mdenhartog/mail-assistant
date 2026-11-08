"""U-01: configuration of the mail-triage agent (spec AC-14, AC-24; threat model T-09)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.settings import Settings, SettingsError, load_settings

APP_DIR = Path(__file__).resolve().parent.parent / "app"

VALID = {
    "ANTHROPIC_API_KEY": "sk-ant-test-secret-value",
    "TELEGRAM_BOT_TOKEN": "123456:telegram-test-secret",
    "TELEGRAM_ALLOWED_USER_ID": "4242",
    "TELEGRAM_ALLOWED_CHAT_ID": "4242",
    "MODEL_SMALL": "model-small-test",
    "MODEL_LARGE": "model-large-test",
    "DATABASE_URL": "postgresql+asyncpg://user:db-test-secret@db:5432/mail",
}
REQUIRED = tuple(VALID)


def test_given_all_required_values_when_settings_load_then_they_are_typed_with_spec_defaults() -> None:
    settings = load_settings(VALID)

    assert isinstance(settings, Settings)
    assert settings.telegram_allowed_user_id == 4242
    assert settings.telegram_allowed_chat_id == 4242
    assert settings.model_small == "model-small-test"
    assert settings.model_large == "model-large-test"
    assert settings.poll_interval_seconds == 60  # spec C1
    assert settings.anthropic_api_key.get_secret_value() == VALID["ANTHROPIC_API_KEY"]


def test_given_settings_when_inspected_then_quiet_hours_are_not_configurable() -> None:
    """Spec C7: quiet hours, overview time and time zone are constants in code, not settings."""
    names = set(Settings.model_fields)

    assert not {n for n in names if "quiet" in n or "overview" in n or "timezone" in n or "snooze" in n}


@pytest.mark.parametrize("missing", REQUIRED)
def test_given_a_missing_required_value_when_loading_then_error_names_the_key_but_no_value(missing: str) -> None:
    env = {key: value for key, value in VALID.items() if key != missing}

    with pytest.raises(SettingsError) as error:
        load_settings(env)

    message = str(error.value)
    assert missing in message
    assert not any(value in message for value in VALID.values())


def test_given_an_invalid_value_when_loading_then_error_does_not_echo_the_value() -> None:
    env = {**VALID, "TELEGRAM_ALLOWED_USER_ID": "not-a-number-secret-marker"}

    with pytest.raises(SettingsError) as error:
        load_settings(env)

    assert "TELEGRAM_ALLOWED_USER_ID" in str(error.value)
    assert "secret-marker" not in str(error.value)


def test_given_settings_when_printed_then_every_secret_is_masked() -> None:
    settings = load_settings(VALID)

    shown = f"{settings!r} {settings!s} {settings.model_dump()} {settings.model_dump_json()}"

    for secret in ("sk-ant-test-secret-value", "telegram-test-secret", "db-test-secret"):
        assert secret not in shown


def test_given_the_app_source_when_scanned_then_no_model_id_literal_exists() -> None:
    literal = re.compile(r"""["'][^"']*claude-[^"']*["']""")

    offenders = [
        f"{path.name}: {match.group(0)}"
        for path in APP_DIR.rglob("*.py")
        for match in literal.finditer(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []
