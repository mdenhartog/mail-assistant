"""SEC-02: the engine hides statement parameters, so a database error never carries a bound value."""

from sqlalchemy.exc import DBAPIError

from app.db import Database

BOUND_VALUE = "recognisable-bound-parameter"


async def test_given_a_database_error_when_printed_then_the_bound_parameter_is_not_in_it() -> None:
    database = Database.create(
        "postgresql+asyncpg://user:pw@127.0.0.1:1/db", ssl_context=None, statement_timeout_ms=1000
    )
    engine = database._engine
    try:
        error = DBAPIError.instance(
            "INSERT INTO t (v) VALUES (%s)",
            (BOUND_VALUE,),
            Exception("boom"),
            Exception,
            hide_parameters=engine.sync_engine.hide_parameters,
        )

        assert BOUND_VALUE not in str(error)
        assert BOUND_VALUE not in repr(error)
    finally:
        await database.dispose()
