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
    "GOOGLE_CLIENT_ID": "client-id-test.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "google-client-test-secret",
    "TOKEN_ENCRYPTION_KEY": "token-key-test-secret",
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
    assert settings.daily_model_budget == 200  # spec C1 / AC-26
    assert settings.alerts_per_hour == 5  # spec AC-26
    assert settings.google_client_id == VALID["GOOGLE_CLIENT_ID"]
    assert settings.google_client_secret.get_secret_value() == VALID["GOOGLE_CLIENT_SECRET"]
    assert settings.token_encryption_key.get_secret_value() == VALID["TOKEN_ENCRYPTION_KEY"]
    assert "google-client-test-secret" not in repr(settings)
    assert "token-key-test-secret" not in repr(settings)
    assert settings.anthropic_api_key.get_secret_value() == VALID["ANTHROPIC_API_KEY"]


def test_given_no_pinned_settings_when_settings_load_then_only_google_security_mail_is_pinned() -> None:
    senders = load_settings(VALID).pinned_senders

    assert senders.google_security == frozenset({"accounts.google.com"})
    assert senders.sign_in == frozenset()  # deployment configuration, no default (ADR-0048)


def test_given_the_two_pinned_settings_when_settings_load_then_each_is_a_clean_lowercase_set() -> None:
    env = {
        **VALID,
        "GOOGLE_SECURITY_SENDER_DOMAINS": " Accounts.Google.com, other.example.test ,,",
        "SIGN_IN_MAIL_DOMAINS": " Login.Example.test ",
    }

    senders = load_settings(env).pinned_senders

    assert senders.google_security == frozenset({"accounts.google.com", "other.example.test"})
    assert senders.sign_in == frozenset({"login.example.test"})


def test_given_an_empty_sign_in_setting_when_settings_load_then_it_means_none() -> None:
    assert load_settings({**VALID, "SIGN_IN_MAIL_DOMAINS": ""}).pinned_senders.sign_in == frozenset()


@pytest.mark.parametrize("name", ["GOOGLE_SECURITY_SENDER_DOMAINS", "SIGN_IN_MAIL_DOMAINS"])
@pytest.mark.parametrize("value", [" , ", "not a domain", "user@example.test", "a" * 300])
def test_given_an_unusable_pinned_setting_when_settings_load_then_startup_fails(name: str, value: str) -> None:
    with pytest.raises(SettingsError):
        load_settings({**VALID, name: value})


def test_given_an_empty_google_security_setting_when_settings_load_then_startup_fails() -> None:
    with pytest.raises(SettingsError):
        load_settings({**VALID, "GOOGLE_SECURITY_SENDER_DOMAINS": ""})


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


def test_given_no_archive_label_value_when_settings_load_then_it_is_assistant_archive() -> None:
    assert load_settings(VALID).archive_label == "Assistant/Archive"


@pytest.mark.parametrize("value", ["Bewaard", "Mail/Done", "Assistant/Archive", "assistant/archive"])
def test_given_a_valid_archive_label_when_settings_load_then_it_is_kept(value: str) -> None:
    assert load_settings({**VALID, "ARCHIVE_LABEL": value}).archive_label == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        " Bewaard",
        "Bewaard ",
        "Bew\naard",
        "a..b",
        "INBOX",
        "spam",
        "CATEGORY_PROMOTIONS",
        "Assistant/Other",
        "Assistant/Travel",
        "Assistant/",
        "a" * 226,
    ],
)
def test_given_an_unusable_archive_label_when_settings_load_then_startup_fails_without_the_value(value: str) -> None:
    with pytest.raises(SettingsError) as error:
        load_settings({**VALID, "ARCHIVE_LABEL": value})

    assert "ARCHIVE_LABEL" in str(error.value)
    assert value.strip() == "" or value not in str(error.value)
