"""U-quiet-hours-14: the wiring reads the stored settings, through one policy source shared by every use case."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.engine import DatabaseTls, make_engine
from app.db.pg_list_sync import PgLabelBook
from app.db.pg_policy_source import PgPolicySource
from app.settings import load_settings
from app.usecases.catchup import BUDGET_RESERVE
from app.usecases.settings_dialog import SettingsDialog
from app.usecases.web_notice_actions import WebNoticeActions
from app.wiring import build_runner
from tests.test_settings import VALID


class _Clock:
    """A fake clock: the wiring must hand this very object to the one conversation store."""

    def __call__(self) -> datetime:
        return datetime(2020, 1, 1, tzinfo=UTC)


def _runner(now: Any = lambda: None, sinks: tuple[Any, ...] = ()) -> Any:
    engine = create_async_engine("postgresql+asyncpg://nobody:x@127.0.0.1:1/none")  # never connected in this test
    return build_runner(
        load_settings(VALID),
        sessions=async_sessionmaker(engine, expire_on_commit=False),
        client=httpx.AsyncClient(timeout=httpx.Timeout(5.0)),
        mailbox=object(),
        sender=object(),
        labels=object(),  # type: ignore[arg-type]
        build_mailbox=object(),  # type: ignore[arg-type]
        apply_mailbox=object(),  # type: ignore[arg-type]
        own_address="marco@example.com",
        heartbeat=None,  # type: ignore[arg-type]
        now=now,
        managed_sinks=sinks,
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


def test_given_the_wiring_when_built_then_the_web_notice_buttons_are_registered_for_the_allowed_chat() -> None:
    settings = load_settings(VALID)

    actions = vars(_runner()._router).get("_web")

    assert isinstance(actions, WebNoticeActions)
    assert vars(actions)["_chat_id"] == settings.telegram_allowed_chat_id
    assert vars(actions)["_by"] == str(settings.telegram_allowed_user_id)


def runner_handlers(router: Any) -> Any:
    return vars(router).get("_handlers", {}).values()


def test_given_the_engine_factory_when_an_engine_is_made_then_bound_parameters_are_hidden() -> None:
    engine = make_engine("postgresql+asyncpg://nobody:x@127.0.0.1:1/none", DatabaseTls("disable"))

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


def test_given_the_wiring_when_built_then_triage_and_catch_up_share_one_label_book_on_the_database() -> None:
    sink = object()

    runner = _runner(sinks=(sink,))

    book = runner._pipeline._labels
    assert isinstance(book, PgLabelBook)
    assert runner._catchup._labels is book
    assert vars(book)["_followers"] == (sink,)  # the guarded adapters learn the managed labels from the book
    assert vars(runner._list_sync)["_sinks"][1:] == (sink,)  # and from the label sync


def test_given_the_wiring_when_built_then_the_resort_parts_hold_no_archive_label_of_their_own() -> None:
    runner = _runner()

    for part in (runner._resort_build, runner._resort_apply, runner._move_back, runner._list_sync):
        assert "_archive" not in vars(part)


def test_given_the_wiring_when_built_then_the_tip_call_spends_from_the_one_daily_budget_above_the_reserve() -> None:
    build = _runner()._resort_build
    model = vars(vars(build)["_tips"])["_model"]

    assert vars(model)["_budget"] is vars(build)["_budget"]
    assert vars(model)["_reserve"] == BUDGET_RESERVE
