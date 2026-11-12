import logging
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.auth.expiry import ABSOLUTE, IDLE
from app.config import (
    LOGIN_COOKIE_MAX_AGE_SECONDS,
    SESSION_COOKIE_MAX_AGE_SECONDS,
    Settings,
)
from app.startup import ConfigurationError, validate_startup
from tests.fakes import make_app, make_settings

BACKEND = Path(__file__).resolve().parents[1]


def refused_fields(**overrides: object) -> tuple[str, ...]:
    with pytest.raises(ConfigurationError) as raised:
        validate_startup(make_settings(**overrides))
    return raised.value.fields


def test_given_complete_valid_configuration_when_checked_then_no_error() -> None:
    validate_startup(make_settings())


def test_given_settings_when_fields_listed_then_none_skips_or_disables_the_check() -> None:
    forbidden = ("skip", "disable", "bypass", "insecure", "validate", "check", "no_")

    names = [name for name in Settings.model_fields if any(word in name for word in forbidden)]

    assert names == []


@pytest.mark.parametrize("environment", ["development", "test", "production"])
def test_given_empty_username_when_app_created_then_configuration_error_names_username(environment: str) -> None:
    with pytest.raises(ConfigurationError) as raised:
        make_app(make_settings(username="", environment=environment))

    assert "username" in raised.value.fields
    assert "username" in str(raised.value)


def test_given_unset_username_when_checked_then_refused() -> None:
    settings = Settings(environment="test")

    with pytest.raises(ConfigurationError) as raised:
        validate_startup(settings)

    assert "username" in raised.value.fields


@pytest.mark.parametrize("address", ["", "not-an-address", "a@b@c", "a@b", " @x.y", "a b@c.d"])
def test_given_bad_email_address_when_checked_then_refused_naming_email_address(address: str) -> None:
    assert refused_fields(email_address=address) == ("email_address",)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("smtp_host", ""),
        ("smtp_port", None),
        ("smtp_port", 0),
        ("smtp_user", ""),
        ("smtp_password", SecretStr("")),
    ],
)
def test_given_missing_smtp_value_when_checked_then_refused_naming_the_field(field: str, value: object) -> None:
    assert refused_fields(**{field: value}) == (field,)


def test_given_smtp_without_starttls_when_checked_then_refused() -> None:
    assert refused_fields(smtp_starttls=False) == ("smtp_starttls",)


def test_given_smtp_starttls_default_when_read_then_true() -> None:
    assert Settings().smtp_starttls is True


def test_given_code_hash_key_of_31_bytes_when_checked_then_refused() -> None:
    assert refused_fields(code_hash_key=SecretStr("k" * 31)) == ("code_hash_key",)


def test_given_code_hash_key_of_32_bytes_when_checked_then_accepted() -> None:
    validate_startup(make_settings(code_hash_key=SecretStr("k" * 32)))


def test_given_multibyte_key_when_checked_then_length_counts_bytes() -> None:
    validate_startup(make_settings(code_hash_key=SecretStr("é" * 16)))
    assert refused_fields(code_hash_key=SecretStr("é" * 15)) == ("code_hash_key",)


@pytest.mark.parametrize("field", ["csrf_key", "username_hash_key"])
def test_given_other_key_shorter_than_32_bytes_when_checked_then_refused(field: str) -> None:
    assert refused_fields(**{field: SecretStr("k" * 31)}) == (field,)


@pytest.mark.parametrize(
    ("first", "second"),
    [("code_hash_key", "csrf_key"), ("code_hash_key", "username_hash_key"), ("csrf_key", "username_hash_key")],
)
def test_given_two_equal_keys_when_checked_then_refused_naming_both(first: str, second: str) -> None:
    same = SecretStr("s" * 32)
    others = {
        "code_hash_key": SecretStr("a" * 32),
        "csrf_key": SecretStr("b" * 32),
        "username_hash_key": SecretStr("c" * 32),
    }
    others[first] = same
    others[second] = same

    assert set(refused_fields(**others)) == {first, second}


@pytest.mark.parametrize(
    "origin", ["", "http://settings.example.test", "settings.example.test", "https://", "ftp://x.y"]
)
def test_given_public_origin_that_is_not_https_when_checked_then_refused(origin: str) -> None:
    assert refused_fields(public_origin=origin) == ("public_origin",)


def test_given_several_problems_when_checked_then_all_fields_are_named() -> None:
    assert set(refused_fields(username="", smtp_host="")) == {"username", "smtp_host"}


def test_given_refused_start_with_canaries_when_logs_and_exception_read_then_only_field_names_appear(
    caplog: pytest.LogCaptureFixture,
) -> None:
    canary = "canary-smtp-secret"
    settings = make_settings(
        username="",
        smtp_password=SecretStr(canary),
        code_hash_key=SecretStr(canary + "-1"),
        csrf_key=SecretStr(canary + "-1"),
        username_hash_key=SecretStr(canary + "-2"),
    )
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ConfigurationError) as raised:
        make_app(settings)

    assert "code_hash_key" in str(raised.value)
    texts = [str(raised.value), repr(raised.value), *(record.getMessage() for record in caplog.records)]
    assert [text for text in texts if canary in text] == []
    assert any("username" in record.getMessage() for record in caplog.records)
    assert canary not in repr(settings)
    assert canary not in settings.model_dump_json()


def test_given_limit_settings_when_read_then_defaults_equal_the_spec_values() -> None:
    settings = Settings()

    assert settings.rate_limit_per_minute == 30
    assert settings.body_limit_bytes == 8192
    assert settings.code_ttl_seconds == 600
    assert settings.resend_cooldown_seconds == 60
    assert settings.codes_per_hour == 5
    assert settings.max_attempts == 5
    assert settings.idle_seconds == 1800
    assert settings.absolute_seconds == 43200
    assert settings.rate_window_seconds == 60


def test_given_limit_settings_when_lowered_then_tests_can_set_them() -> None:
    settings = make_settings(rate_limit_per_minute=2, body_limit_bytes=16, max_attempts=1)

    assert (settings.rate_limit_per_minute, settings.body_limit_bytes, settings.max_attempts) == (2, 16, 1)
    validate_startup(settings)


def test_given_limits_when_compared_with_pure_modules_then_defaults_are_the_same_values() -> None:
    settings = Settings()

    assert settings.idle_seconds == IDLE.total_seconds()
    assert settings.absolute_seconds == ABSOLUTE.total_seconds()


def test_given_cookie_lifetimes_when_read_then_login_600_and_session_43200() -> None:
    assert LOGIN_COOKIE_MAX_AGE_SECONDS == 600
    assert SESSION_COOKIE_MAX_AGE_SECONDS == 43200


def test_given_proxy_settings_when_read_then_defaults_trust_nobody() -> None:
    settings = Settings()

    assert settings.trusted_proxy_cidrs == []
    assert settings.trusted_proxy_hops == 1


def test_given_secret_fields_when_settings_printed_then_values_are_hidden() -> None:
    settings = make_settings(database_url=SecretStr("postgresql+asyncpg://u:pw-canary@h/db"))

    assert "pw-canary" not in repr(settings)


def test_given_pyproject_when_read_then_coverage_gate_is_90() -> None:
    options = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]

    assert "--cov-fail-under=90" in options["addopts"]


def test_given_ci_workflow_when_read_then_backend_job_runs_uv_run_pytest() -> None:
    workflows = (BACKEND.parent / ".github" / "workflows").glob("*.y*ml")

    assert any("uv run pytest" in path.read_text(encoding="utf-8") for path in workflows)


def test_given_app_package_when_vulture_runs_then_no_dead_code_is_reported() -> None:
    result = subprocess.run([sys.executable, "-m", "vulture"], cwd=BACKEND, capture_output=True, text=True, check=False)

    assert result.stdout == ""
    assert result.returncode == 0


# U-web-settings-24: the limit and proxy settings are checked at start


@pytest.mark.parametrize(
    "overrides",
    [
        {"trusted_proxy_cidrs": ["not-a-cidr"]},
        {"trusted_proxy_cidrs": ["10.0.0.0/8", "10.0.0.0/99"]},
        {"trusted_proxy_hops": 0},
        {"rate_limit_per_minute": 0},
        {"rate_window_seconds": 0},
        {"body_limit_bytes": 0},
    ],
)
def test_given_a_wrong_limit_or_proxy_setting_when_checked_then_start_is_refused(
    overrides: dict[str, object],
) -> None:
    fields = refused_fields(**overrides)

    assert fields == (next(iter(overrides)),)


def test_given_valid_proxy_cidrs_when_checked_then_no_error() -> None:
    validate_startup(make_settings(trusted_proxy_cidrs=["10.42.0.0/16", "fd00::/8"], trusted_proxy_hops=2))
