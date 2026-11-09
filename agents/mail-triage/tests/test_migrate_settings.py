"""U-quiet-hours-15a: the owner credentials belong to the migrate command only (ADR-0025; AC-30)."""

from __future__ import annotations

import pytest

from app.settings import Settings, SettingsError, load_migrate_settings, load_settings
from tests.test_settings import VALID

MIGRATE_VALID = {
    "DATABASE_OWNER_URL": "postgresql+asyncpg://owner:owner-test-secret@db:5432/mail",
    "RUNTIME_ROLE_PASSWORD": "runtime-role-test-secret",
}


def test_given_the_agent_settings_when_loaded_without_the_owner_url_then_they_load_and_hold_no_owner_field() -> None:
    settings = load_settings(VALID)

    assert not {name for name in Settings.model_fields if "owner" in name}
    assert "owner" not in repr(settings)


def test_given_the_owner_url_and_runtime_password_when_migrate_settings_load_then_both_are_masked_secrets() -> None:
    settings = load_migrate_settings(MIGRATE_VALID)

    assert settings.database_owner_url.get_secret_value() == MIGRATE_VALID["DATABASE_OWNER_URL"]
    assert settings.runtime_role_password.get_secret_value() == MIGRATE_VALID["RUNTIME_ROLE_PASSWORD"]
    shown = f"{settings!r} {settings!s} {settings.model_dump()} {settings.model_dump_json()}"
    assert not any(value in shown for value in MIGRATE_VALID.values())


@pytest.mark.parametrize("missing", tuple(MIGRATE_VALID))
def test_given_a_missing_migrate_value_when_loading_then_the_error_names_the_key_and_no_value(missing: str) -> None:
    env = {key: value for key, value in MIGRATE_VALID.items() if key != missing}

    with pytest.raises(SettingsError) as error:
        load_migrate_settings(env)

    assert missing in str(error.value)
    assert not any(value in str(error.value) for value in MIGRATE_VALID.values())


def test_given_an_empty_owner_url_when_loading_migrate_settings_then_it_is_refused_by_key() -> None:
    with pytest.raises(SettingsError) as error:
        load_migrate_settings({**MIGRATE_VALID, "DATABASE_OWNER_URL": ""})

    assert "DATABASE_OWNER_URL" in str(error.value)


def test_given_agent_settings_in_the_environment_when_migrate_settings_load_then_they_are_not_needed() -> None:
    settings = load_migrate_settings({**VALID, **MIGRATE_VALID})

    assert not hasattr(settings, "anthropic_api_key")
