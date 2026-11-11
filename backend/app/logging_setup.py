"""Logging hygiene: noisy client libraries are pinned (U-web-settings-14).

``httpx`` and ``httpcore`` log full request URLs (query strings included) at INFO and ``aiosmtplib`` logs the SMTP
conversation, so all three stay at WARNING. The uvicorn access log is off in the image command (``--no-access-log``).
"""

import logging

PINNED_LOGGERS: tuple[str, ...] = ("httpx", "httpcore", "aiosmtplib")


def configure_logging() -> None:
    """Pin the client-library loggers to WARNING."""
    for name in PINNED_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
