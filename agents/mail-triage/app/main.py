"""Start-up of the mail-triage agent: ``python -m app [serve|migrate]``.

``serve`` (the default) validates the configuration, checks that the schema is current and runs until stopped.
``migrate`` is the one-shot job of ADR-0025: it connects as the owner role, migrates, and sets up the runtime role.
The two commands read different settings, so the running agent never holds the owner credentials.

A broken configuration stops the process before it touches anything. Every log handler gets the redaction filter with
the secrets this process holds, so a secret that slips into a message never reaches a log (spec AC-24). The commands are
injectable so the start-up can be tested without Google, Telegram or a database.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import TYPE_CHECKING

from app.obs.redaction import RedactionFilter, Redactor
from app.settings import SettingsError, load_migrate_settings, load_settings
from app.wiring import migrate as run_migration
from app.wiring import serve as run_agent

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Mapping, Sequence
    from typing import Any

    from pydantic import SecretStr

    from app.settings import MigrateSettings, Settings

EXIT_OK = 0
EXIT_BAD_CONFIG = 2
COMMANDS = ("serve", "migrate")


def _protect_logs(*secrets: SecretStr) -> None:
    redactor = Redactor(secret.get_secret_value() for secret in secrets)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for handler in logging.getLogger().handlers:
        handler.addFilter(RedactionFilter(redactor))


def _fail(message: object) -> int:
    sys.stderr.write(f"{message}\n")
    return EXIT_BAD_CONFIG


def main(
    env: Mapping[str, str] | None = None,
    serve: Callable[[Settings], Coroutine[Any, Any, int]] = run_agent,
    migrate: Callable[[MigrateSettings], Coroutine[Any, Any, int]] = run_migration,
    argv: Sequence[str] = (),
) -> int:
    """Return the process exit code."""
    command = argv[0] if argv else "serve"
    if command not in COMMANDS or len(argv) > 1:
        return _fail(f"usage: python -m app [{'|'.join(COMMANDS)}]")
    try:
        if command == "migrate":
            migrate_settings = load_migrate_settings(env)
            _protect_logs(
                migrate_settings.database_owner_url,
                migrate_settings.runtime_role_password,
                migrate_settings.web_role_password,
            )
            return asyncio.run(migrate(migrate_settings))
        settings = load_settings(env)
    except SettingsError as error:
        return _fail(error)
    _protect_logs(
        settings.anthropic_api_key,
        settings.telegram_bot_token,
        settings.database_url,
        settings.google_client_secret,
        settings.token_encryption_key,
    )
    return asyncio.run(serve(settings))
