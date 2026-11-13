"""U-web-settings-58: the agent and the migrate job reach the database over verify-full TLS (SEC-10, W-8, W-9)."""

from __future__ import annotations

import ssl
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.db import engine as engine_module
from app.db import migrate
from app.db.engine import DatabaseTls, connect_args, make_engine, ssl_argument
from app.main import EXIT_BAD_CONFIG, EXIT_OK, main
from app.settings import SettingsError, load_migrate_settings, load_settings
from tests.test_migrate_settings import MIGRATE_VALID
from tests.test_settings import VALID

if TYPE_CHECKING:
    from pathlib import Path

    from app.settings import MigrateSettings, Settings

WEAKER = ("disable", "require", "verify-ca")


@pytest.fixture
def ca_file(tmp_path: Path) -> Path:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-only CA")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    path = tmp_path / "ca.crt"
    path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return path


# -- settings: production refuses anything weaker than verify-full -------------------------------------------------


def test_given_no_environment_when_settings_load_then_production_with_verify_full_applies() -> None:
    settings = load_settings(VALID)

    assert settings.environment == "production"
    assert settings.database_ssl == "verify-full"
    assert settings.database_ca_file == ""


@pytest.mark.parametrize("mode", WEAKER)
def test_given_production_and_a_weaker_sslmode_when_settings_load_then_start_up_refuses_naming_the_key(
    mode: str,
) -> None:
    with pytest.raises(SettingsError) as error:
        load_settings({**VALID, "ENVIRONMENT": "production", "DATABASE_SSL": mode})

    assert "DATABASE_SSL" in str(error.value)
    assert not any(value in str(error.value) for value in VALID.values())


@pytest.mark.parametrize("mode", WEAKER)
def test_given_production_and_a_weaker_sslmode_when_migrate_settings_load_then_the_job_refuses(mode: str) -> None:
    with pytest.raises(SettingsError) as error:
        load_migrate_settings({**MIGRATE_VALID, "ENVIRONMENT": "production", "DATABASE_SSL": mode})

    assert "DATABASE_SSL" in str(error.value)


@pytest.mark.parametrize("environment", ["development", "test"])
@pytest.mark.parametrize("mode", ["disable", "require", "verify-ca", "verify-full"])
def test_given_a_non_production_environment_when_any_sslmode_is_set_then_it_is_allowed(
    environment: str, mode: str
) -> None:
    settings = load_settings({**VALID, "ENVIRONMENT": environment, "DATABASE_SSL": mode})
    migrate_settings = load_migrate_settings({**MIGRATE_VALID, "ENVIRONMENT": environment, "DATABASE_SSL": mode})

    assert settings.database_ssl == migrate_settings.database_ssl == mode


def test_given_an_unknown_sslmode_when_settings_load_then_they_are_refused() -> None:
    with pytest.raises(SettingsError, match="DATABASE_SSL"):
        load_settings({**VALID, "ENVIRONMENT": "development", "DATABASE_SSL": "prefer"})


def test_given_the_ca_file_when_settings_load_then_the_tls_settings_carry_mode_and_file() -> None:
    env = {"ENVIRONMENT": "production", "DATABASE_SSL": "verify-full", "DATABASE_CA_FILE": "/etc/db-ca/ca.crt"}

    assert load_settings({**VALID, **env}).database_tls == DatabaseTls("verify-full", "/etc/db-ca/ca.crt")
    assert load_migrate_settings({**MIGRATE_VALID, **env}).database_tls == DatabaseTls(
        "verify-full", "/etc/db-ca/ca.crt"
    )


def test_given_a_weaker_sslmode_in_production_when_the_agent_starts_then_serve_never_runs() -> None:
    async def never(_settings: Settings) -> int:
        raise AssertionError("start-up must refuse before the agent runs")

    assert main({**VALID, "ENVIRONMENT": "production", "DATABASE_SSL": "require"}, serve=never) == EXIT_BAD_CONFIG


def test_given_a_weaker_sslmode_in_production_when_the_job_starts_then_migrate_never_runs() -> None:
    async def never(_settings: MigrateSettings) -> int:
        raise AssertionError("start-up must refuse before the job migrates")

    env = {**MIGRATE_VALID, "ENVIRONMENT": "production", "DATABASE_SSL": "disable"}
    assert main(env, migrate=never, argv=["migrate"]) == EXIT_BAD_CONFIG


def test_given_verify_full_when_the_job_starts_then_migrate_runs_with_the_tls_settings() -> None:
    seen: list[DatabaseTls] = []

    async def fake_migrate(settings: MigrateSettings) -> int:
        seen.append(settings.database_tls)
        return EXIT_OK

    env = {**MIGRATE_VALID, "DATABASE_SSL": "verify-full", "DATABASE_CA_FILE": "/etc/db-ca/ca.crt"}
    assert main(env, migrate=fake_migrate, argv=["migrate"]) == EXIT_OK
    assert seen == [DatabaseTls("verify-full", "/etc/db-ca/ca.crt")]


# -- the engine ---------------------------------------------------------------------------------------------------


def test_given_verify_full_and_a_ca_when_the_argument_is_built_then_the_context_checks_certificate_and_host(
    ca_file: Path,
) -> None:
    context = ssl_argument("verify-full", str(ca_file))

    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_given_the_weaker_modes_when_the_argument_is_built_then_each_is_as_documented(ca_file: Path) -> None:
    assert ssl_argument("disable", "") is False
    require = ssl_argument("require", "")
    assert isinstance(require, ssl.SSLContext)
    assert require.verify_mode == ssl.CERT_NONE
    verify_ca = ssl_argument("verify-ca", str(ca_file))
    assert isinstance(verify_ca, ssl.SSLContext)
    assert verify_ca.verify_mode == ssl.CERT_REQUIRED
    assert verify_ca.check_hostname is False


def test_given_an_unknown_mode_when_the_argument_is_built_then_it_is_refused() -> None:
    with pytest.raises(ValueError, match="ssl mode"):
        ssl_argument("prefer", "")


def test_given_a_missing_ca_file_when_the_argument_is_built_then_it_fails_without_hiding_it() -> None:
    with pytest.raises(FileNotFoundError):
        ssl_argument("verify-full", "/nonexistent/ca.crt")


def test_given_tls_settings_when_the_engine_is_made_then_the_driver_gets_the_context(
    monkeypatch: pytest.MonkeyPatch, ca_file: Path
) -> None:
    seen: dict[str, Any] = {}

    def fake_create(url: str, **kwargs: Any) -> object:
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(engine_module, "create_async_engine", fake_create)

    make_engine("postgresql+asyncpg://u:pw@db:5432/app", DatabaseTls("verify-full", str(ca_file)))

    assert isinstance(seen["connect_args"]["ssl"], ssl.SSLContext)
    assert seen["hide_parameters"] is True
    assert connect_args(DatabaseTls("disable", ""))["ssl"] is False


# -- the migrate job ------------------------------------------------------------------------------------------------


def _spy(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    async def fake_connect(**kwargs: Any) -> object:
        seen.update(kwargs)
        raise ConnectionRefusedError  # the first thing the job does is connect; nothing more is needed

    monkeypatch.setattr(migrate.asyncpg, "connect", fake_connect)
    return seen


async def test_given_verify_full_when_the_job_connects_then_asyncpg_gets_the_context_with_the_ca(
    monkeypatch: pytest.MonkeyPatch, ca_file: Path
) -> None:
    seen = _spy(monkeypatch)

    with pytest.raises(ConnectionRefusedError):
        await migrate.migrate_database(
            "postgresql+asyncpg://owner:pw@db:5432/app", {}, DatabaseTls("verify-full", str(ca_file))
        )

    assert isinstance(seen["ssl"], ssl.SSLContext)
    assert seen["ssl"].check_hostname is True
    assert (seen["host"], seen["port"], seen["user"], seen["database"]) == ("db", 5432, "owner", "app")


async def test_given_verify_full_when_the_job_upgrades_then_alembic_connects_with_the_same_context(
    monkeypatch: pytest.MonkeyPatch, ca_file: Path
) -> None:
    class Lock:
        async def execute(self, *_args: object) -> None:
            return None

        async def close(self) -> None:
            return None

    async def fake_connect(**_kwargs: Any) -> Lock:
        return Lock()

    captured: dict[str, Any] = {}

    def fake_upgrade(url: str, connect_args_: dict[str, Any]) -> None:
        captured.update(connect_args_)
        raise RuntimeError("stop after the upgrade was asked for")

    monkeypatch.setattr(migrate.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(migrate, "_upgrade", fake_upgrade)

    with pytest.raises(RuntimeError, match="stop after"):
        await migrate.migrate_database(
            "postgresql+asyncpg://owner:pw@db:5432/app",
            {"mail_triage_runtime": "x", "web_settings_runtime": "y"},
            DatabaseTls("verify-full", str(ca_file)),
        )

    assert isinstance(captured["ssl"], ssl.SSLContext)
    assert captured["ssl"].check_hostname is True


async def test_given_a_url_with_its_own_ssl_value_when_the_job_connects_then_the_setting_decides(
    monkeypatch: pytest.MonkeyPatch, ca_file: Path
) -> None:
    seen = _spy(monkeypatch)

    with pytest.raises(ConnectionRefusedError):
        await migrate.migrate_database(
            "postgresql+asyncpg://owner:pw@db:5432/app?ssl=disable", {}, DatabaseTls("verify-full", str(ca_file))
        )

    assert isinstance(seen["ssl"], ssl.SSLContext)  # not a value inside the secret URL
