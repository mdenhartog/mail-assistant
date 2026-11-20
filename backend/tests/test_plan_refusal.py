"""U-mail-categories-17: the SQLSTATE of a refused database function becomes a 409, a 422 or stays a fault."""

import pytest
from sqlalchemy.exc import DBAPIError

from app.plan_repo import PlanConflict, PlanMalformed, refusal_of


class _DriverError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__("row values: sender-canary")
        self.sqlstate = sqlstate


def _error(sqlstate: str) -> DBAPIError:
    return DBAPIError("select", {}, _DriverError(sqlstate))


@pytest.mark.parametrize(
    ("sqlstate", "expected"), [("MC409", PlanConflict), ("22023", PlanMalformed), ("42501", None), ("23505", None)]
)
def test_given_a_sqlstate_when_translated_then_409_422_or_left_alone(
    sqlstate: str, expected: type[Exception] | None
) -> None:
    refusal = refusal_of(_error(sqlstate))

    assert type(refusal) is expected if expected else refusal is None
    assert "canary" not in str(refusal)
