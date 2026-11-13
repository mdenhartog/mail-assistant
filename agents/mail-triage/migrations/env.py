"""Alembic environment: asynchronous, URL from the Alembic config (never from a file with a password)."""

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.models import Base

config = context.config
target_metadata = Base.metadata


def _migrate(connection) -> None:  # noqa: ANN001
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run() -> None:
    engine = create_async_engine(
        config.get_main_option("sqlalchemy.url") or "", connect_args=config.attributes.get("connect_args", {})
    )
    async with engine.connect() as connection:
        await connection.run_sync(_migrate)
    await engine.dispose()


asyncio.run(_run())
