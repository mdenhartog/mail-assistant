"""Start-up validation of the configuration (AC-4): the backend refuses to start on a wrong one.

Errors and log lines name fields, never values.
"""

import logging
import re
from collections.abc import Iterator
from urllib.parse import urlsplit

from pydantic import SecretStr

from app.config import Settings

logger = logging.getLogger(__name__)

MIN_KEY_BYTES = 32
_EMAIL = re.compile(r"[^@\s]+@[^@\s.]+(\.[^@\s.]+)+")
_KEY_FIELDS = ("code_hash_key", "csrf_key", "username_hash_key")


class ConfigurationError(Exception):
    """The configuration is wrong; ``fields`` names every offending field (never a value)."""

    def __init__(self, fields: tuple[str, ...]) -> None:
        """Build the error from the offending field names."""
        super().__init__("invalid configuration: " + ", ".join(fields))
        self.fields = fields


def _secret_bytes(value: SecretStr) -> bytes:
    return value.get_secret_value().encode("utf-8")


def _smtp_problems(settings: Settings) -> Iterator[str]:
    if not settings.smtp_host.strip():
        yield "smtp_host"
    if settings.smtp_port is None or not 0 < settings.smtp_port < 65536:  # noqa: PLR2004
        yield "smtp_port"
    if not settings.smtp_user:
        yield "smtp_user"
    if not settings.smtp_password.get_secret_value():
        yield "smtp_password"
    if not settings.smtp_starttls:
        yield "smtp_starttls"


def _text_problems(settings: Settings) -> Iterator[str]:
    if not settings.username.strip():
        yield "username"
    if _EMAIL.fullmatch(settings.email_address) is None:
        yield "email_address"
    yield from _smtp_problems(settings)
    origin = urlsplit(settings.public_origin)
    if origin.scheme != "https" or not origin.hostname:
        yield "public_origin"


def _key_problems(settings: Settings) -> Iterator[str]:
    keys = {name: _secret_bytes(getattr(settings, name)) for name in _KEY_FIELDS}
    for name, key in keys.items():
        if len(key) < MIN_KEY_BYTES:
            yield name
    names = list(keys)
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            if keys[first] == keys[second]:
                yield first
                yield second


def validate_startup(settings: Settings) -> None:
    """Refuse a wrong configuration, whatever the environment.

    Args:
        settings: The settings to check.

    Raises:
        ConfigurationError: Naming every offending field, never a value.
    """
    problems = (*_text_problems(settings), *_key_problems(settings))
    fields = tuple(dict.fromkeys(problems))
    if fields:
        logger.error("startup.refused fields=%s", ", ".join(fields))
        raise ConfigurationError(fields)


async def purge_expired(database: object, clock: object) -> None:
    """Skeleton."""
    raise NotImplementedError


def attach_database(app: object, database: object, clock: object) -> None:
    """Skeleton."""
    raise NotImplementedError
