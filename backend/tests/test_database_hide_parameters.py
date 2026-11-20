"""SEC-02: the engine hides statement parameters, so a database error never carries a bound value."""

from typing import Any

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

import app.db as db_module
from app.db import Database

BOUND_VALUE = "recognisable-bound-parameter"


async def test_given_the_engine_when_created_then_it_hides_statement_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def capture(url: str, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return create_async_engine(url, **kwargs)

    monkeypatch.setattr(db_module, "create_async_engine", capture)

    database = Database.create(
        "postgresql+asyncpg://user:pw@127.0.0.1:1/db", ssl_context=None, statement_timeout_ms=1000
    )
    try:
        assert seen["hide_parameters"] is True
    finally:
        await database.dispose()


def test_given_hidden_parameters_when_a_database_error_is_printed_then_the_bound_value_is_not_in_it() -> None:
    error = DBAPIError.instance(
        "INSERT INTO t (v) VALUES (%s)",
        (BOUND_VALUE,),
        Exception("boom"),
        Exception,
        hide_parameters=True,
    )

    assert BOUND_VALUE not in str(error)
    assert BOUND_VALUE not in repr(error)
