"""U-web-settings-38: the production factory wires the running api (AC-4, AC-29) and the legacy factory is gone."""

import json
import re
from collections.abc import Iterator
from importlib import import_module
from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

import app.main
from app.config import Settings, get_settings
from app.mail.smtp import SmtpMailSender
from app.production import create_production_app
from app.startup import ConfigurationError

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "backend" / "Dockerfile"
COMPOSE = ROOT / "compose.yaml"
# Port 1 refuses the connection at once, so no test waits for a database.
ENVIRONMENT = {
    "APP_ENVIRONMENT": "production",
    "APP_USERNAME": "factory-user",
    "APP_EMAIL_ADDRESS": "owner@example.test",
    "APP_SMTP_HOST": "smtp.example.test",
    "APP_SMTP_PORT": "587",
    "APP_SMTP_FROM": "assistant@example.test",
    "APP_SMTP_USER": "factory-smtp-user",
    "APP_SMTP_PASSWORD": "factory-smtp-password",
    "APP_CODE_HASH_KEY": "a" * 32,
    "APP_CSRF_KEY": "b" * 32,
    "APP_USERNAME_HASH_KEY": "c" * 32,
    "APP_PUBLIC_ORIGIN": "https://settings.example.test",
    "APP_DATABASE_URL": "postgresql+asyncpg://web:factory-db-password@127.0.0.1:1/app",
    "APP_DATABASE_SSL": "verify-full",
}


@pytest.fixture(autouse=True)
def fresh_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def set_environment(monkeypatch: pytest.MonkeyPatch, *, without: tuple[str, ...] = ()) -> None:
    for name, value in ENVIRONMENT.items():
        if name not in without:
            monkeypatch.setenv(name, value)
        else:
            monkeypatch.delenv(name, raising=False)


def dockerfile_command() -> list[str]:
    match = re.search(r"^CMD (\[.*\])$", DOCKERFILE.read_text(encoding="utf-8"), re.MULTILINE)
    assert match is not None
    return json.loads(match.group(1))


def test_given_the_main_module_when_read_then_the_legacy_create_app_is_gone() -> None:
    assert not hasattr(app.main, "create_app")
    assert "create_app" not in Path(app.main.__file__).read_text(encoding="utf-8")


def test_given_the_image_command_when_read_then_it_runs_the_production_factory_without_an_access_log() -> None:
    command = dockerfile_command()
    target = command[command.index("uvicorn") + 1]
    module, _, name = target.partition(":")

    assert "--factory" in command
    assert "--no-access-log" in command
    assert callable(getattr(import_module(module), name))
    assert (module, name) == ("app.production", "create_production_app")


def test_given_the_dev_service_when_read_then_it_starts_the_same_factory() -> None:
    command = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["api-dev"]["command"]

    assert "app.production:create_production_app" in command
    assert "--factory" in command


async def test_given_the_environment_when_the_factory_runs_then_the_app_has_every_part_attached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_environment(monkeypatch)

    application = create_production_app()
    try:
        state = application.state
        assert isinstance(state.mailer, SmtpMailSender)
        for part in ("database", "sessions", "security_events", "code_requests", "verify_code"):
            assert hasattr(state, part), part
        assert state.settings.smtp_from == "assistant@example.test"
    finally:
        await application.state.database.dispose()


async def test_given_an_unreachable_database_when_readyz_then_503_and_not_fail_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_environment(monkeypatch)
    application = create_production_app()

    try:
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            response = await client.get("/readyz")
            health = await client.get("/healthz")
    finally:
        await application.state.database.dispose()

    assert response.status_code == 503
    assert "factory-db-password" not in response.text
    assert health.status_code == 200


@pytest.mark.parametrize(
    ("missing", "field"),
    [
        ("APP_SMTP_HOST", "smtp_host"),
        ("APP_SMTP_PORT", "smtp_port"),
        ("APP_SMTP_FROM", "smtp_from"),
        ("APP_SMTP_USER", "smtp_user"),
        ("APP_SMTP_PASSWORD", "smtp_password"),
        ("APP_USERNAME", "username"),
        ("APP_PUBLIC_ORIGIN", "public_origin"),
    ],
)
def test_given_a_missing_setting_when_the_factory_runs_then_it_refuses_naming_the_field_only(
    monkeypatch: pytest.MonkeyPatch, missing: str, field: str
) -> None:
    set_environment(monkeypatch, without=(missing,))

    with pytest.raises(ConfigurationError) as raised:
        create_production_app()

    assert raised.value.fields == (field,)
    assert "factory-smtp-password" not in str(raised.value)


def test_given_no_environment_when_the_factory_runs_then_it_refuses_before_touching_the_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_environment(monkeypatch, without=tuple(ENVIRONMENT))

    with pytest.raises(ConfigurationError):
        create_production_app()


async def test_given_an_app_without_a_database_when_readyz_then_503() -> None:
    from tests.fakes import make_app  # noqa: PLC0415

    async with AsyncClient(transport=ASGITransport(app=make_app()), base_url="http://test") as client:
        assert (await client.get("/readyz")).status_code == 503


def test_given_the_settings_when_read_then_smtp_from_is_a_field_the_chart_can_set() -> None:
    assert "smtp_from" in Settings.model_fields
