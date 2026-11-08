"""Typed application settings loaded from the environment."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings; every value comes from environment variables prefixed with ``APP_``."""

    model_config = SettingsConfigDict(env_prefix="APP_", extra="forbid")

    app_name: str = "Mail Assistant"
    environment: Literal["development", "test", "production"] = "development"

    @property
    def docs_enabled(self) -> bool:
        """Whether the interactive API docs are served (never in production)."""
        return self.environment != "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance.

    Returns:
        The cached settings loaded from the environment.
    """
    return Settings()
