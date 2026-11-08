"""Bring the database schema up to date with Alembic, from inside the running agent.

Alembic's environment starts its own event loop, so the upgrade runs in a worker thread. The agent calls this after it
has taken the single-replica lock, so two copies never migrate at the same time.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def _upgrade(url: str) -> None:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")


async def upgrade(url: str) -> None:
    """Apply every migration that has not run yet."""
    await asyncio.to_thread(_upgrade, url)
