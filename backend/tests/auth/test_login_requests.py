# pyright: reportUnusedImport=false
"""U-web-settings-16, database level: the login request store against a real PostgreSQL and a FakeClock."""

import asyncio
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from app.auth.code_rules import hourly_cap_reached
from app.auth.login_requests import Dead, LoginRequestCapReached, LoginRequests, Ok, Wrong
from app.db import Database
from app.ids import SecretsIdSource
from tests.db.conftest import (  # noqa: F401  # the shared fixtures of U-09, used here without editing them
    db,
    owner,
    pg_server,
    server,
    template_name,
    web_database,
)
from tests.fakes import FakeIds

T0 = datetime(2026, 3, 1, 14, 0, 0, tzinfo=UTC)
KEY = b"k" * 32
TTL = timedelta(seconds=600)
MAX_ATTEMPTS = 5
CAP = 100
USER = "u" * 64
OTHER = "o" * 64
RIGHT = "123456"
WRONG = "000000"


@pytest.fixture
def store(web_database: Database) -> LoginRequests:  # noqa: F811
    return LoginRequests(web_database, FakeIds(), hash_key=KEY, ttl=TTL, max_attempts=MAX_ATTEMPTS)


async def test_given_the_right_code_at_9_59_when_checked_then_ok_and_the_same_code_is_dead(
    store: LoginRequests,
) -> None:
    request = await store.create(USER, RIGHT, T0, CAP)

    first = await store.check(request.id, RIGHT, T0 + timedelta(minutes=9, seconds=59))
    second = await store.check(request.id, RIGHT, T0 + timedelta(minutes=9, seconds=59))

    assert first == Ok()
    assert second == Dead()


async def test_given_the_right_code_at_10_00_when_checked_then_dead(store: LoginRequests) -> None:
    request = await store.create(USER, RIGHT, T0, CAP)

    verdict = await store.check(request.id, RIGHT, T0 + timedelta(minutes=10))

    assert verdict == Dead()
    assert request.expires_at == T0 + TTL


async def test_given_five_wrong_codes_when_checked_then_attempts_left_count_down_and_the_fifth_is_dead(
    store: LoginRequests,
) -> None:
    request = await store.create(USER, RIGHT, T0, CAP)

    verdicts = [await store.check(request.id, WRONG, T0) for _ in range(5)]
    after = await store.check(request.id, RIGHT, T0)

    assert verdicts == [Wrong(4), Wrong(3), Wrong(2), Wrong(1), Dead()]
    assert after == Dead()


async def test_given_four_wrong_codes_when_the_right_one_is_checked_then_ok(store: LoginRequests) -> None:
    request = await store.create(USER, RIGHT, T0, CAP)
    for _ in range(4):
        await store.check(request.id, WRONG, T0)

    assert await store.check(request.id, RIGHT, T0) == Ok()


async def test_given_a_malformed_code_when_checked_then_it_counts_as_a_wrong_attempt(store: LoginRequests) -> None:
    request = await store.create(USER, RIGHT, T0, CAP)

    assert await store.check(request.id, "12", T0) == Wrong(4)


async def test_given_an_old_and_a_newer_code_when_the_old_is_checked_then_dead(store: LoginRequests) -> None:
    old = await store.create(USER, "111111", T0, CAP)
    new = await store.create(USER, "222222", T0 + timedelta(minutes=2), CAP)

    assert await store.check(old.id, "111111", T0 + timedelta(minutes=3)) == Dead()
    assert await store.check(new.id, "222222", T0 + timedelta(minutes=3)) == Ok()


async def test_given_another_browsers_dead_unknown_and_missing_ids_when_checked_then_dead_and_no_attempt_counted(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    other = await store.create(OTHER, "111111", T0, CAP)
    await store.check(other.id, "111111", T0)  # used, so dead
    await store.create(USER, RIGHT, T0, CAP)

    verdicts = [
        await store.check(other.id, WRONG, T0),
        await store.check("unknown-id", WRONG, T0),
        await store.check(None, WRONG, T0),
    ]

    attempts = await owner.fetch("SELECT attempts FROM web_auth.login_request")
    assert verdicts == [Dead(), Dead(), Dead()]
    assert all(row["attempts"] == 0 for row in attempts)


async def test_given_a_wrong_code_for_one_request_when_checked_then_only_that_row_counts(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    first = await store.create(USER, RIGHT, T0, CAP)
    second = await store.create(OTHER, RIGHT, T0, CAP)

    await store.check(first.id, WRONG, T0)

    rows = {row["id"]: row["attempts"] for row in await owner.fetch("SELECT id, attempts FROM web_auth.login_request")}
    assert rows == {first.id: 1, second.id: 0}


async def test_given_two_simultaneous_checks_of_the_right_code_when_run_then_exactly_one_is_ok(
    store: LoginRequests,
) -> None:
    request = await store.create(USER, RIGHT, T0, CAP)
    barrier = asyncio.Barrier(2)

    async def attempt() -> object:
        await barrier.wait()
        return await store.check(request.id, RIGHT, T0)

    verdicts = await asyncio.gather(attempt(), attempt())

    assert sorted(type(verdict).__name__ for verdict in verdicts) == ["Dead", "Ok"]


async def test_given_five_sent_codes_when_read_then_five_and_the_cap_refuses_the_sixth(store: LoginRequests) -> None:
    for index in range(5):
        moment = T0 + timedelta(seconds=index)
        request = await store.create(USER, RIGHT, moment, CAP)
        await store.mark_sent(request.id, moment)
    now = T0 + timedelta(minutes=30)

    count = await store.sent_in_last_hour(USER, now)

    assert count == 5
    assert hourly_cap_reached([now - timedelta(minutes=30)] * count, now, 5)


async def test_given_a_send_at_the_edge_of_the_hour_when_read_then_59_59_counts_and_60_01_does_not(
    store: LoginRequests,
) -> None:
    request = await store.create(USER, RIGHT, T0, CAP)
    await store.mark_sent(request.id, T0)

    assert await store.sent_in_last_hour(USER, T0 + timedelta(minutes=59, seconds=59)) == 1
    assert await store.sent_in_last_hour(USER, T0 + timedelta(minutes=60)) == 0
    assert await store.sent_in_last_hour(USER, T0 + timedelta(minutes=60, seconds=1)) == 0


async def test_given_sent_codes_of_another_username_when_read_then_they_are_not_counted(store: LoginRequests) -> None:
    request = await store.create(OTHER, RIGHT, T0, CAP)
    await store.mark_sent(request.id, T0)

    assert await store.sent_in_last_hour(USER, T0) == 0


async def test_given_five_failed_sends_when_read_then_zero_sent_and_the_newest_creation_is_the_last_request(
    store: LoginRequests,
) -> None:
    for index in range(5):
        await store.create(USER, RIGHT, T0 + timedelta(seconds=index), CAP)
    now = T0 + timedelta(seconds=10)

    assert await store.sent_in_last_hour(USER, now) == 0
    assert await store.last_requested_at(USER) == T0 + timedelta(seconds=4)


async def test_given_no_request_when_last_requested_at_is_read_then_none(store: LoginRequests) -> None:
    assert await store.last_requested_at(USER) is None


async def test_given_the_cap_of_open_requests_when_one_more_is_created_then_refused_and_nothing_written(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await store.create("a" * 64, RIGHT, T0, 2)
    await store.create("b" * 64, RIGHT, T0, 2)

    with pytest.raises(LoginRequestCapReached):
        await store.create("c" * 64, RIGHT, T0, 2)

    rows = await owner.fetch("SELECT username_key, dead_at FROM web_auth.login_request")
    assert sorted(row["username_key"][0] for row in rows) == ["a", "b"]
    assert all(row["dead_at"] is None for row in rows)


async def test_given_the_cap_reached_when_the_same_username_asks_again_then_it_replaces_its_own_request(
    store: LoginRequests,
) -> None:
    await store.create("a" * 64, RIGHT, T0, 2)
    await store.create("b" * 64, RIGHT, T0, 2)

    again = await store.create("a" * 64, RIGHT, T0 + timedelta(minutes=2), 2)

    assert again.created_at == T0 + timedelta(minutes=2)


async def test_given_dead_and_expired_requests_when_the_cap_is_counted_then_only_open_ones_count(
    store: LoginRequests,
) -> None:
    used = await store.create("a" * 64, RIGHT, T0, 1)
    await store.check(used.id, RIGHT, T0)
    await store.create("b" * 64, RIGHT, T0, 2)  # open until T0 + 10 minutes

    later = T0 + timedelta(minutes=11)
    created = await store.create("c" * 64, RIGHT, later, 1)

    assert created.id


async def test_given_rows_older_than_an_hour_when_a_request_is_created_then_they_are_removed(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    old = await store.create(OTHER, RIGHT, T0, CAP)
    recent = await store.create(USER, RIGHT, T0 + timedelta(minutes=1), CAP)

    fresh = await store.create(USER, RIGHT, T0 + timedelta(minutes=61), CAP)

    ids = {row["id"] for row in await owner.fetch("SELECT id FROM web_auth.login_request")}
    assert old.id not in ids
    assert {recent.id, fresh.id} <= ids


async def test_given_the_production_id_source_when_a_request_is_created_then_the_id_fits_the_column(
    web_database: Database,  # noqa: F811
) -> None:
    store = LoginRequests(web_database, SecretsIdSource(), hash_key=KEY, ttl=TTL, max_attempts=MAX_ATTEMPTS)

    request = await store.create(USER, RIGHT, T0, CAP)

    assert len(request.id) == 32  # VARCHAR(32) of migration 0008
    assert await store.check(request.id, RIGHT, T0) == Ok()


async def test_given_a_stored_request_when_read_as_the_owner_then_only_the_hash_of_the_code_is_stored(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    request = await store.create(USER, RIGHT, T0, CAP)

    row = await owner.fetchrow("SELECT l::text AS whole, code_hash FROM web_auth.login_request l")

    assert row is not None
    assert RIGHT not in row["whole"]
    assert len(row["code_hash"]) == 64
    assert request.id in row["whole"]


async def test_given_sent_codes_when_their_times_are_read_then_only_those_of_the_last_hour_come_oldest_first(
    store: LoginRequests,
) -> None:
    for offset in (120, 0, 60):
        moment = T0 + timedelta(seconds=offset)
        request = await store.create(USER, RIGHT, moment, CAP)
        await store.mark_sent(request.id, moment)
    unsent = await store.create(USER, RIGHT, T0 + timedelta(seconds=180), CAP)
    other = await store.create(OTHER, RIGHT, T0, CAP)
    await store.mark_sent(other.id, T0)
    assert unsent.id

    now = T0 + timedelta(seconds=3660)

    assert await store.sent_times_in_last_hour(USER, now) == [T0 + timedelta(seconds=120)]
    assert await store.sent_times_in_last_hour(USER, T0 + timedelta(seconds=3599)) == [
        T0,
        T0 + timedelta(seconds=60),
        T0 + timedelta(seconds=120),
    ]


async def test_given_the_pad_when_run_then_it_writes_nothing(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await store.pad()

    assert await owner.fetchval("SELECT count(*) FROM web_auth.login_request") == 0
