"""Runtime settings, read once from the environment (fail closed).

Secrets come from the environment (``.env`` locally, a Kubernetes secret in production), never from code. They are
``SecretStr`` so they print masked. Quiet hours, the overview time, the remind-me-later default and the time zone are
not settings of the environment: they are stored in the database and changed through ``/settings`` (INT-002, ADR-0025);
the defaults live in ``schedule_policy.policy``.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, SecretStr, ValidationError, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from app.db.engine import DatabaseTls

if TYPE_CHECKING:
    from collections.abc import Mapping


class SettingsError(ValueError):
    """The configuration is incomplete or invalid; the agent must not start. The message never contains a value."""


class DatabaseTlsSettings(BaseSettings):
    """How the database is reached, shared by the agent and the migrate job (SEC-10, W-8, W-9).

    ``environment`` defaults to production, so a deployment that forgets it is held to the strict rule: the connection
    must be ``verify-full``. Development and test may use a weaker mode (a local database without TLS).
    """

    environment: Literal["production", "development", "test"] = "production"  # must come before database_ssl
    database_ssl: Literal["disable", "require", "verify-ca", "verify-full"] = "verify-full"
    database_ca_file: str = ""  # PEM file with the CA of the database certificate; empty uses the system trust store

    @field_validator("database_ssl")
    @classmethod
    def _production_verifies_the_host(cls, mode: str, info: ValidationInfo) -> str:
        if info.data.get("environment", "production") == "production" and mode != "verify-full":
            raise ValueError("production needs verify-full")
        return mode

    @property
    def database_tls(self) -> DatabaseTls:
        """The mode and the CA file, as the engine and the migrate job take them."""
        return DatabaseTls(self.database_ssl, self.database_ca_file)


class Settings(DatabaseTlsSettings):
    """Everything configurable about the mail-triage agent."""

    model_config = SettingsConfigDict(frozen=True, extra="ignore")

    anthropic_api_key: SecretStr = Field(min_length=1)
    telegram_bot_token: SecretStr = Field(min_length=1)
    telegram_allowed_user_id: int = Field(gt=0)
    telegram_allowed_chat_id: int = Field(gt=0)
    model_small: str = Field(min_length=1)  # model ids come from configuration, never from literals in code
    model_large: str = Field(min_length=1)
    database_url: SecretStr = Field(min_length=1)  # contains the database password
    google_client_id: str = Field(min_length=1)  # the OAuth client of the one-time consent and of token refresh
    google_client_secret: SecretStr = Field(min_length=1)
    token_encryption_key: SecretStr = Field(min_length=1)  # Fernet key for the stored refresh token (AC-25)
    poll_interval_seconds: int = Field(default=60, ge=1)  # spec C1
    daily_model_budget: int = Field(default=200, ge=0)  # model calls per day (AC-26)
    alerts_per_hour: int = Field(default=5, ge=1)  # individual alerts per hour before batching (AC-26)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Read only what ``load_settings`` hands in, so tests and the app never depend on ambient variables."""
        return (init_settings,)


class MigrateSettings(DatabaseTlsSettings):
    """What the ``migrate`` command needs, and only that (ADR-0025). The running agent never reads these.

    The owner role runs the migrations and owns every table; the runtime roles (``mail_triage_runtime`` and
    ``web_settings_runtime``) own nothing. Their passwords are set from here, so the secret store is the single source
    of them.
    """

    model_config = SettingsConfigDict(frozen=True, extra="ignore")

    database_owner_url: SecretStr = Field(min_length=1)  # contains the owner's password
    runtime_role_password: SecretStr = Field(min_length=1)
    web_role_password: SecretStr = Field(min_length=1)  # password of web_settings_runtime (ADR-0033)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Read only what ``load_migrate_settings`` hands in."""
        return (init_settings,)


def _load[T: BaseSettings](model: type[T], env: Mapping[str, str] | None) -> T:
    source = os.environ if env is None else env
    values: dict[str, Any] = {name: source[name.upper()] for name in model.model_fields if name.upper() in source}
    try:
        return model(**values)
    except ValidationError as error:
        keys = sorted({str(problem["loc"][0]).upper() for problem in error.errors() if problem["loc"]})
        raise SettingsError(f"Missing or invalid configuration: {', '.join(keys)}") from None


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Read and validate the settings; raise ``SettingsError`` naming the keys (never the values) that are wrong."""
    return _load(Settings, env)


def load_migrate_settings(env: Mapping[str, str] | None = None) -> MigrateSettings:
    """Read the owner credentials for the migrate command; same rules as ``load_settings``."""
    return _load(MigrateSettings, env)


def load_database_tls(env: Mapping[str, str] | None = None) -> DatabaseTls:
    """Read only the database TLS settings (the consent command needs no others); same rules as ``load_settings``."""
    return _load(DatabaseTlsSettings, env).database_tls
