"""U-quiet-hours-14: the wiring reads the stored settings, through one policy source shared by every use case."""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.pg_policy_source import PgPolicySource
from app.settings import load_settings
from app.usecases.settings_dialog import SettingsDialog
from app.wiring import build_runner
from tests.test_settings import VALID


def _runner() -> Any:
    engine = create_async_engine("postgresql+asyncpg://nobody:x@127.0.0.1:1/none")  # never connected in this test
    return build_runner(
        load_settings(VALID),
        sessions=async_sessionmaker(engine, expire_on_commit=False),
        client=httpx.AsyncClient(timeout=httpx.Timeout(5.0)),
        mailbox=object(),
        sender=object(),
        own_address="marco@example.com",
        heartbeat=None,  # type: ignore[arg-type]
        now=lambda: None,  # type: ignore[arg-type,return-value]
    )


def test_given_the_wiring_when_built_then_every_use_case_shares_one_pg_policy_source() -> None:
    runner = _runner()

    sources = [
        runner._pipeline._policy,
        runner._catchup._policy,
        runner._delivery._policy,
        runner._snooze._policy,
        runner._overview._policies,
    ]

    assert all(isinstance(source, PgPolicySource) for source in sources)
    assert len({id(source) for source in sources}) == 1


def test_given_the_wiring_when_built_then_the_settings_dialogue_is_registered_with_the_router() -> None:
    handlers = list(runner_handlers(_runner()._router))

    assert any(isinstance(handler, SettingsDialog) for handler in handlers)


def runner_handlers(router: Any) -> Any:
    return vars(router).get("_handlers", {}).values()
