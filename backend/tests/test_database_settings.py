"""U-web-settings-09, unit level: the TLS context, the driver arguments, the production refusal, no SQL clock."""

import ast
import re
import ssl
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.db import build_ssl_context, connect_arguments
from app.startup import ConfigurationError, validate_startup
from tests.fakes import make_settings

APP_DIR = Path(__file__).resolve().parents[1] / "app"
SQL_CLOCK = re.compile(r"\bnow\s*\(\s*\)|current_timestamp|current_date|localtimestamp|clock_timestamp", re.IGNORECASE)


def test_given_verify_full_when_context_built_then_hostname_and_certificate_are_checked() -> None:
    context = build_ssl_context("verify-full")

    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.minimum_version == ssl.TLSVersion.TLSv1_2  # set explicitly: the OpenSSL default may be "none"


def test_given_verify_ca_when_context_built_then_certificate_is_checked_but_not_the_host() -> None:
    context = build_ssl_context("verify-ca")

    assert context.check_hostname is False
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_given_require_when_context_built_then_nothing_is_verified() -> None:
    context = build_ssl_context("require")

    assert context.check_hostname is False
    assert context.verify_mode == ssl.CERT_NONE


def test_given_unknown_mode_when_context_built_then_refused() -> None:
    with pytest.raises(ValueError, match="mode"):
        build_ssl_context("disable")


def test_given_settings_when_driver_arguments_built_then_context_is_verify_full_and_timeout_is_set() -> None:
    settings = make_settings(
        database_url=SecretStr("postgresql+asyncpg://u:p@h/db"), database_statement_timeout_ms=1234
    )

    arguments = connect_arguments(settings)

    assert isinstance(arguments["ssl"], ssl.SSLContext)
    assert arguments["ssl"].check_hostname is True
    assert arguments["ssl"].verify_mode == ssl.CERT_REQUIRED
    assert arguments["server_settings"]["statement_timeout"] == "1234"


@pytest.mark.parametrize("mode", ["require", "verify-ca"])
def test_given_production_with_a_weaker_mode_when_checked_then_refused_naming_database_url(mode: str) -> None:
    with pytest.raises(ConfigurationError) as raised:
        validate_startup(
            make_settings(environment="production", database_ssl=mode, trusted_proxy_cidrs=["10.244.0.0/16"])
        )

    assert raised.value.fields == ("database_url",)


def test_given_production_with_verify_full_when_checked_then_accepted() -> None:
    validate_startup(
        make_settings(environment="production", database_ssl="verify-full", trusted_proxy_cidrs=["10.244.0.0/16"])
    )


def test_given_development_with_require_when_checked_then_accepted() -> None:
    validate_startup(make_settings(environment="development", database_ssl="require"))


@pytest.mark.parametrize("mode", ["off", "disable", "allow", "prefer", ""])
def test_given_ssl_off_when_settings_built_then_refused(mode: str) -> None:
    with pytest.raises(ValidationError):
        Settings(database_ssl=mode)  # pyright: ignore[reportArgumentType]


def _sql_strings(source: str) -> list[str]:
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


def test_given_the_source_tree_when_searched_then_no_sql_text_reads_the_database_clock() -> None:
    hits = [
        f"{path.relative_to(APP_DIR)}: {text[:60]!r}"
        for path in APP_DIR.rglob("*.py")
        for text in _sql_strings(path.read_text(encoding="utf-8"))
        if SQL_CLOCK.search(text)
    ]

    assert hits == []


def test_given_sql_text_with_now_when_searched_then_the_rule_finds_it() -> None:
    assert [t for t in _sql_strings('x = "update t set a = now()"') if SQL_CLOCK.search(t)]
    assert [t for t in _sql_strings('x = "select CURRENT_TIMESTAMP"') if SQL_CLOCK.search(t)]
    assert not [t for t in _sql_strings('"""now() in a docstring"""\nx = clock.now()') if SQL_CLOCK.search(t)]


def test_given_default_settings_when_read_then_timeout_is_five_seconds_and_the_ca_is_the_system_one() -> None:
    settings = Settings()

    assert settings.database_statement_timeout_ms == 5000
    assert settings.database_ca_file == ""
    with pytest.raises(ValidationError):
        Settings(database_statement_timeout_ms=0)
