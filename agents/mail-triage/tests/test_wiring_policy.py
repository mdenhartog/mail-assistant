"""U-quiet-hours-14: the wiring reads the stored settings, through one policy source shared by every use case."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.pg_policy_source import PgPolicySource
from app.settings import load_settings
from app.usecases.settings_dialog import SettingsDialog
from app.wiring import build_runner, make_engine
from tests.test_settings import VALID


class _Clock:
    """A fake clock: the wiring must hand this very object to the one conversation store."""

    def __call__(self) -> datetime:
        return datetime(2020, 1, 1, tzinfo=UTC)


def _runner(now: Any = lambda: None) -> Any:
    engine = create_async_engine("postgresql+asyncpg://nobody:x@127.0.0.1:1/none")  # never connected in this test
    return build_runner(
        load_settings(VALID),
        sessions=async_sessionmaker(engine, expire_on_commit=False),
        client=httpx.AsyncClient(timeout=httpx.Timeout(5.0)),
        mailbox=object(),
        sender=object(),
        own_address="marco@example.com",
        heartbeat=None,  # type: ignore[arg-type]
        now=now,
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


def test_given_the_engine_factory_when_an_engine_is_made_then_bound_parameters_are_hidden() -> None:
    engine = make_engine("postgresql+asyncpg://nobody:x@127.0.0.1:1/none")

    assert engine.sync_engine.hide_parameters is True


def test_given_a_fake_clock_when_the_runner_is_built_then_the_store_and_the_router_share_one_conversation_store() -> (
    None
):
    clock = _Clock()

    runner = _runner(clock)

    from_store = vars(runner._store)["_conversations"]
    from_router = vars(runner._router)["_conversations"]
    assert from_store is from_router
    assert vars(from_store)["_now"] is clock
