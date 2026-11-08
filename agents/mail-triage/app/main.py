"""Start-up of the mail-triage agent: validate the configuration, then run.

Later units add the polling loop here. Until then the agent only proves that it starts with a safe configuration.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from app.settings import SettingsError, load_settings

if TYPE_CHECKING:
    from collections.abc import Mapping

EXIT_OK = 0
EXIT_BAD_CONFIG = 2


def main(env: Mapping[str, str] | None = None) -> int:
    """Return the process exit code. A broken configuration stops the agent before it touches anything."""
    try:
        load_settings(env)
    except SettingsError as error:
        sys.stderr.write(f"{error}\n")
        return EXIT_BAD_CONFIG
    return EXIT_OK
