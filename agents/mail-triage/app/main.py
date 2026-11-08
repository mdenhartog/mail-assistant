"""Start-up of the mail-triage agent: validate the configuration, then run until stopped.

A broken configuration stops the agent before it touches anything. Every log handler gets the redaction filter with
the secrets this process holds, so a secret that slips into a message never reaches a log (spec AC-24). ``serve`` is
injectable so the start-up can be tested without Google, Telegram or a database.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import TYPE_CHECKING

from app.obs.redaction import RedactionFilter, Redactor
from app.settings import SettingsError, load_settings
from app.wiring import serve as run_agent

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Mapping
    from typing import Any

    from app.settings import Settings

EXIT_OK = 0
EXIT_BAD_CONFIG = 2


def _protect_logs(settings: Settings) -> None:
    secrets = (
        settings.anthropic_api_key,
        settings.telegram_bot_token,
        settings.database_url,
        settings.google_client_secret,
        settings.token_encryption_key,
    )
    redactor = Redactor(secret.get_secret_value() for secret in secrets)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for handler in logging.getLogger().handlers:
        handler.addFilter(RedactionFilter(redactor))


def main(
    env: Mapping[str, str] | None = None,
    serve: Callable[[Settings], Coroutine[Any, Any, int]] = run_agent,
) -> int:
    """Return the process exit code."""
    try:
        settings = load_settings(env)
    except SettingsError as error:
        sys.stderr.write(f"{error}\n")
        return EXIT_BAD_CONFIG
    _protect_logs(settings)
    return asyncio.run(serve(settings))
