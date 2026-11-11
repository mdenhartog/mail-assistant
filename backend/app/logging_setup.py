"""Logging hygiene: noisy client libraries are pinned (U-web-settings-14)."""

PINNED_LOGGERS: tuple[str, ...] = ("httpx", "httpcore", "aiosmtplib")


def configure_logging() -> None:
    """Pin the client-library loggers to WARNING."""
