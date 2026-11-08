"""Runtime settings, read once from the environment (fail closed).

Secrets come from the environment (``.env`` locally, a Kubernetes secret in production), never from code. They are
``SecretStr`` so they print masked. Quiet hours, the overview time, the snooze default and the time zone are constants
in code on purpose (spec C7); making them adjustable is a later intent (INT-002).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

if TYPE_CHECKING:
    from collections.abc import Mapping


class SettingsError(ValueError):
    """The configuration is incomplete or invalid; the agent must not start. The message never contains a value."""


class Settings(BaseSettings):
    """Everything configurable about the mail-triage agent."""

    model_config = SettingsConfigDict(frozen=True, extra="ignore")

    anthropic_api_key: SecretStr = Field(min_length=1)
    telegram_bot_token: SecretStr = Field(min_length=1)
    telegram_allowed_user_id: int = Field(gt=0)
    telegram_allowed_chat_id: int = Field(gt=0)
    model_small: str = Field(min_length=1)  # model ids come from configuration, never from literals in code
    model_large: str = Field(min_length=1)
    database_url: SecretStr = Field(min_length=1)  # contains the database password
    poll_interval_seconds: int = Field(default=60, ge=1)  # spec C1

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


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Read and validate the settings; raise ``SettingsError`` naming the keys (never the values) that are wrong."""
    source = os.environ if env is None else env
    values: dict[str, Any] = {name: source[name.upper()] for name in Settings.model_fields if name.upper() in source}
    try:
        return Settings(**values)
    except ValidationError as error:
        keys = sorted({str(problem["loc"][0]).upper() for problem in error.errors() if problem["loc"]})
        raise SettingsError(f"Missing or invalid configuration: {', '.join(keys)}") from None
