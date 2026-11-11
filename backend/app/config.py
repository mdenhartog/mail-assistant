"""Typed application settings loaded from the environment.

Every limit and every secret of the web sign-in and settings feature is defined here, once.
Secrets are ``SecretStr`` so they never appear in ``repr`` or in a dump.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.auth.expiry import ABSOLUTE, IDLE

# Cookie lifetimes are fixed (ADR-0036), not configurable.
LOGIN_COOKIE_MAX_AGE_SECONDS = 600
SESSION_COOKIE_MAX_AGE_SECONDS = 43200


class Settings(BaseSettings):
    """Application settings; every value comes from environment variables prefixed with ``APP_``.

    Missing values are allowed here and refused by ``app.startup.validate_startup``.
    """

    model_config = SettingsConfigDict(env_prefix="APP_", extra="forbid")

    app_name: str = "Mail Assistant"
    environment: Literal["development", "test", "production"] = "development"

    # The one user and where the code goes (C-1).
    username: str = ""
    email_address: str = ""

    # Mail sender: STARTTLS is required (W-14).
    smtp_host: str = ""
    smtp_port: int | None = None
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_starttls: bool = True

    # Keys: at least 32 bytes each, all different.
    code_hash_key: SecretStr = SecretStr("")
    csrf_key: SecretStr = SecretStr("")
    username_hash_key: SecretStr = SecretStr("")

    public_origin: str = ""
    database_url: SecretStr = SecretStr("")
    database_ssl: Literal["require", "verify-ca", "verify-full"] = "verify-full"
    # Trusted CA for the database; empty uses the system trust store (SSL_CERT_FILE).
    database_ca_file: str = ""
    database_statement_timeout_ms: int = Field(default=5000, gt=0, description="Server-side statement timeout.")
    # Must equal the agent's run interval (POLL_INTERVAL_SECONDS, 60 by default) rounded up to whole minutes.
    notice_interval_minutes: int = Field(default=1, description="Agent run interval in whole minutes, rounded up.")

    # Limits (C-4); tests lower them.
    rate_limit_per_minute: int = 30
    rate_window_seconds: int = 60
    body_limit_bytes: int = 8192
    code_ttl_seconds: int = 600
    resend_cooldown_seconds: int = 60
    codes_per_hour: int = 5
    max_attempts: int = 5
    open_login_request_cap: int = 100
    idle_seconds: int = int(IDLE.total_seconds())
    absolute_seconds: int = int(ABSOLUTE.total_seconds())

    # Client address: the one the last trusted proxy appended (ADR-0034).
    trusted_proxy_cidrs: list[str] = []
    trusted_proxy_hops: int = 1

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
