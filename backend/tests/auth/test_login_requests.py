# pyright: reportUnusedImport=false
"""U-web-settings-16, database level: the login request store against a real PostgreSQL and a FakeClock."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Final

import asyncpg
import pytest

from app.auth.login_requests import Applicant, Dead, LoginRequest, LoginRequestRefused, LoginRequests, Ok, Wrong
from app.auth.request_code_rules import RequestLimits
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
CLIENT = "c" * 64
ELSEWHERE = "d" * 64
# No limit bites unless a test lowers it.
OPEN: Final = RequestLimits(
    cooldown=timedelta(0),
    codes_per_hour=1000,
    live_per_username=1000,
    open_per_client=1000,
    requests_per_client_per_hour=1000,
    class_open_cap=CAP,
)
RIGHT = "123456"
WRONG = "000000"


async def make(  # noqa: PLR0913  # a request is described by who, what and when
    store: LoginRequests,
    username_key: str,
    code: str,
    now: datetime,
    *,
    client: str = CLIENT,
    cookie: str | None = None,
    limits: RequestLimits = OPEN,
) -> LoginRequest:
    """A code request of the owner (USER is the configured username) from a client, under no limit unless given."""
    return await store.create(Applicant(username_key, USER, client, cookie, known=True), code, now, limits)


async def decoy(  # noqa: PLR0913  # a request is described by who and when
    store: LoginRequests,
    username_key: str,
    now: datetime,
    *,
    client: str = CLIENT,
    cookie: str | None = None,
    limits: RequestLimits = OPEN,
) -> LoginRequest:
    return await store.create_decoy(Applicant(username_key, USER, client, cookie, known=False), now, limits)


def lowered(**overrides: int | timedelta) -> RequestLimits:
    values: dict[str, int | timedelta] = {
        "cooldown": OPEN.cooldown,
        "codes_per_hour": OPEN.codes_per_hour,
        "live_per_username": OPEN.live_per_username,
        "open_per_client": OPEN.open_per_client,
        "requests_per_client_per_hour": OPEN.requests_per_client_per_hour,
        "class_open_cap": OPEN.class_open_cap,
    }
    values.update(overrides)
    return RequestLimits(**values)  # pyright: ignore[reportArgumentType]


async def live_ids(connection: asyncpg.Connection) -> set[str]:
    return {row["id"] for row in await connection.fetch("SELECT id FROM web_auth.login_request WHERE dead_at IS NULL")}


@pytest.fixture
def store(web_database: Database) -> LoginRequests:  # noqa: F811
    return LoginRequests(web_database, FakeIds(), hash_key=KEY, ttl=TTL, max_attempts=MAX_ATTEMPTS)


async def test_given_the_right_code_at_9_59_when_checked_then_ok_and_the_same_code_is_dead(
    store: LoginRequests,
) -> None:
    request = await make(store, USER, RIGHT, T0)

    first = await store.check(request.id, RIGHT, T0 + timedelta(minutes=9, seconds=59))
    second = await store.check(request.id, RIGHT, T0 + timedelta(minutes=9, seconds=59))

    assert first == Ok()
    assert second == Dead()


async def test_given_the_right_code_at_10_00_when_checked_then_dead(store: LoginRequests) -> None:
    request = await make(store, USER, RIGHT, T0)

    verdict = await store.check(request.id, RIGHT, T0 + timedelta(minutes=10))

    assert verdict == Dead(existing=True)
    assert request.expires_at == T0 + TTL


async def test_given_five_wrong_codes_when_checked_then_attempts_left_count_down_and_the_fifth_is_dead(
    store: LoginRequests,
) -> None:
    request = await make(store, USER, RIGHT, T0)

    verdicts = [await store.check(request.id, WRONG, T0) for _ in range(5)]
    after = await store.check(request.id, RIGHT, T0)

    assert verdicts == [Wrong(4), Wrong(3), Wrong(2), Wrong(1), Dead(existing=True)]
    assert after == Dead()


async def test_given_four_wrong_codes_when_the_right_one_is_checked_then_ok(store: LoginRequests) -> None:
    request = await make(store, USER, RIGHT, T0)
    for _ in range(4):
        await store.check(request.id, WRONG, T0)

    assert await store.check(request.id, RIGHT, T0) == Ok()


async def test_given_a_malformed_code_when_checked_then_it_counts_as_a_wrong_attempt(store: LoginRequests) -> None:
    request = await make(store, USER, RIGHT, T0)

    assert await store.check(request.id, "12", T0) == Wrong(4)


async def test_given_an_old_and_a_newer_code_when_the_old_is_checked_then_dead(store: LoginRequests) -> None:
    old = await make(store, USER, "111111", T0)
    new = await make(store, USER, "222222", T0 + timedelta(minutes=2), cookie=old.id)

    assert await store.check(old.id, "111111", T0 + timedelta(minutes=3)) == Dead()
    assert await store.check(new.id, "222222", T0 + timedelta(minutes=3)) == Ok()


async def test_given_another_browsers_dead_unknown_and_missing_ids_when_checked_then_dead_and_no_attempt_counted(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    other = await make(store, OTHER, "111111", T0)
    await store.check(other.id, "111111", T0)  # used, so dead
    await make(store, USER, RIGHT, T0)

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
    first = await make(store, USER, RIGHT, T0)
    second = await make(store, OTHER, RIGHT, T0)

    await store.check(first.id, WRONG, T0)

    rows = {row["id"]: row["attempts"] for row in await owner.fetch("SELECT id, attempts FROM web_auth.login_request")}
    assert rows == {first.id: 1, second.id: 0}


async def test_given_two_simultaneous_checks_of_the_right_code_when_run_then_exactly_one_is_ok(
    store: LoginRequests,
) -> None:
    request = await make(store, USER, RIGHT, T0)
    barrier = asyncio.Barrier(2)

    async def attempt() -> object:
        await barrier.wait()
        return await store.check(request.id, RIGHT, T0)

    verdicts = await asyncio.gather(attempt(), attempt())

    assert sorted(type(verdict).__name__ for verdict in verdicts) == ["Dead", "Ok"]


async def test_given_rows_older_than_an_hour_when_a_request_is_created_then_they_are_removed(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    old = await make(store, OTHER, RIGHT, T0)
    recent = await make(store, USER, RIGHT, T0 + timedelta(minutes=1))

    fresh = await make(store, USER, RIGHT, T0 + timedelta(minutes=61))

    ids = {row["id"] for row in await owner.fetch("SELECT id FROM web_auth.login_request")}
    assert old.id not in ids
    assert {recent.id, fresh.id} <= ids


async def test_given_the_production_id_source_when_a_request_is_created_then_the_id_fits_the_column(
    web_database: Database,  # noqa: F811
) -> None:
    store = LoginRequests(web_database, SecretsIdSource(), hash_key=KEY, ttl=TTL, max_attempts=MAX_ATTEMPTS)

    request = await make(store, USER, RIGHT, T0)

    assert len(request.id) == 32  # VARCHAR(32) of migration 0008
    assert await store.check(request.id, RIGHT, T0) == Ok()


async def test_given_a_stored_request_when_read_as_the_owner_then_only_the_hash_of_the_code_is_stored(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    request = await make(store, USER, RIGHT, T0)

    row = await owner.fetchrow("SELECT l::text AS whole, code_hash FROM web_auth.login_request l")

    assert row is not None
    assert RIGHT not in row["whole"]
    assert len(row["code_hash"]) == 64
    assert request.id in row["whole"]


async def test_given_requests_in_every_state_when_attempts_left_is_read_then_only_a_live_one_has_a_number(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    live = await make(store, USER, RIGHT, T0)
    assert await store.attempts_left(live.id, T0) == MAX_ATTEMPTS
    await store.check(live.id, WRONG, T0)
    assert await store.attempts_left(live.id, T0) == MAX_ATTEMPTS - 1
    assert await store.attempts_left(live.id, T0 + TTL) is None
    assert await store.attempts_left("n" * 32, T0) is None
    assert await store.attempts_left(None, T0) is None
    await store.check(live.id, RIGHT, T0)
    assert await store.attempts_left(live.id, T0) is None
    assert await owner.fetchval("SELECT attempts FROM web_auth.login_request") == 1


# ---- U-web-settings-53 ---------------------------------------------------------------------------------------------


# Criterion 1 (RT-01, AC-16)
async def test_given_decoys_at_their_cap_when_the_owner_creates_a_request_then_it_is_created_and_a_decoy_is_not_stored(
    store: LoginRequests,
) -> None:
    limits = lowered(class_open_cap=3)
    for index in range(3):
        await decoy(store, f"{index}" * 64, T0, client=f"{index}" * 64, limits=limits)

    owner_request = await make(store, USER, RIGHT, T0, client=ELSEWHERE, limits=limits)

    assert owner_request.id
    swallowed = await decoy(store, "9" * 64, T0 + timedelta(seconds=100), client="9" * 64, limits=limits)
    assert swallowed.id
    assert not swallowed.stored  # the usual answer, never a refusal the owner would not get (RT2-03)


# Criterion 1
async def test_given_the_owner_rows_when_a_decoy_is_counted_then_the_owner_rows_do_not_count_against_the_decoy_cap(
    store: LoginRequests,
) -> None:
    limits = lowered(class_open_cap=1)
    await make(store, USER, RIGHT, T0, client=ELSEWHERE, limits=limits)

    created = await decoy(store, "1" * 64, T0, limits=limits)

    assert created.id


# Criterion 1
async def test_given_a_decoy_at_a_full_class_when_read_then_nothing_was_written_and_nothing_was_killed(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    limits = lowered(class_open_cap=1)
    first = await decoy(store, "1" * 64, T0, client="1" * 64, limits=limits)

    swallowed = await decoy(store, "2" * 64, T0, client="2" * 64, limits=limits)

    assert not swallowed.stored
    assert await live_ids(owner) == {first.id}
    assert await owner.fetchval("SELECT count(*) FROM web_auth.login_request") == 1


# Criterion 2 (W-7)
async def test_given_the_per_client_open_number_when_one_client_asks_again_then_it_is_refused_and_another_is_not(
    store: LoginRequests,
) -> None:
    limits = lowered(open_per_client=2)
    await decoy(store, "1" * 64, T0, limits=limits)
    await make(store, USER, RIGHT, T0 + timedelta(seconds=10), limits=limits)

    with pytest.raises(LoginRequestRefused) as refused:
        await decoy(store, "2" * 64, T0 + timedelta(seconds=100), limits=limits)
    other = await decoy(store, "2" * 64, T0 + timedelta(seconds=100), client=ELSEWHERE, limits=limits)

    assert refused.value.wait_seconds == 500
    assert other.id


# Criterion 2
async def test_given_the_per_client_hourly_number_when_one_client_asks_again_then_it_is_refused_and_another_is_not(
    store: LoginRequests,
) -> None:
    limits = lowered(requests_per_client_per_hour=2)
    await decoy(store, "1" * 64, T0, limits=limits)
    await make(store, USER, RIGHT, T0 + timedelta(minutes=11), limits=limits)  # the first has expired by now
    third_at = T0 + timedelta(minutes=22)

    with pytest.raises(LoginRequestRefused) as refused:
        await decoy(store, "2" * 64, third_at, limits=limits)
    other = await decoy(store, "2" * 64, third_at, client=ELSEWHERE, limits=limits)
    after = await decoy(store, "3" * 64, T0 + timedelta(minutes=61), limits=limits)

    assert refused.value.wait_seconds == 38 * 60  # the first leaves the hour at T0 + 60 minutes
    assert other.id
    assert after.id


# Criterion 2
async def test_given_a_stored_request_when_read_then_it_holds_the_client_digest_it_was_given(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    await make(store, USER, RIGHT, T0, client="9" * 64)

    row = await owner.fetchrow("SELECT client_hash FROM web_auth.login_request")

    assert row is not None
    assert row["client_hash"] == "9" * 64


# Criterion 3 (RT-04)
async def test_given_a_live_request_when_another_client_asks_then_the_first_stays_live_and_its_code_checks(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    first = await make(store, USER, "111111", T0, client=CLIENT)

    second = await make(store, USER, "222222", T0 + timedelta(minutes=2), client=ELSEWHERE)

    assert await live_ids(owner) == {first.id, second.id}
    assert await store.check(first.id, "111111", T0 + timedelta(minutes=3)) == Ok()


# Criterion 3
async def test_given_a_live_request_when_the_same_client_asks_again_without_the_cookie_then_both_stay_live(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    first = await make(store, USER, "111111", T0, client=CLIENT)

    second = await make(store, USER, "222222", T0 + timedelta(minutes=2), client=CLIENT)

    assert await live_ids(owner) == {first.id, second.id}


# Criterion 3
async def test_given_a_live_request_when_its_cookie_comes_from_another_client_then_the_first_is_replaced(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    first = await make(store, USER, "111111", T0, client=CLIENT)
    other = await make(store, USER, "333333", T0, client=ELSEWHERE)

    second = await make(store, USER, "222222", T0 + timedelta(minutes=2), client="e" * 64, cookie=first.id)

    assert await live_ids(owner) == {other.id, second.id}


# Criterion 3
async def test_given_the_cookie_of_another_username_when_a_request_is_made_then_that_request_is_not_replaced(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    owners = await make(store, USER, "111111", T0, client=CLIENT)

    decoyed = await decoy(store, "1" * 64, T0 + timedelta(minutes=2), client=ELSEWHERE, cookie=owners.id)

    assert await live_ids(owner) == {owners.id, decoyed.id}


# Criterion 3
async def test_given_a_refused_request_with_the_live_cookie_when_read_then_the_live_request_was_not_killed(
    store: LoginRequests,
    owner: asyncpg.Connection,  # noqa: F811
) -> None:
    limits = lowered(cooldown=timedelta(seconds=60))
    first = await make(store, USER, "111111", T0, limits=limits)

    with pytest.raises(LoginRequestRefused):
        await make(store, USER, "222222", T0 + timedelta(seconds=10), cookie=first.id, limits=limits)

    assert await live_ids(owner) == {first.id}


# Criterion 3
async def test_given_the_live_number_of_a_username_when_another_client_asks_then_it_is_refused_until_one_expires(
    store: LoginRequests,
) -> None:
    limits = lowered(live_per_username=2)
    await make(store, USER, "111111", T0, client="1" * 64, limits=limits)
    await make(store, USER, "222222", T0 + timedelta(seconds=60), client="2" * 64, limits=limits)

    with pytest.raises(LoginRequestRefused) as refused:
        await make(store, USER, "333333", T0 + timedelta(seconds=120), client="3" * 64, limits=limits)
    after = await make(store, USER, "333333", T0 + timedelta(seconds=600), client="3" * 64, limits=limits)

    assert refused.value.wait_seconds == 480
    assert after.id


# Criterion 4
async def test_given_the_cooldown_when_a_request_comes_too_early_then_the_wait_is_the_rest_of_the_cooldown(
    store: LoginRequests,
) -> None:
    limits = lowered(cooldown=timedelta(seconds=60))
    await decoy(store, USER, T0, limits=limits)

    with pytest.raises(LoginRequestRefused) as refused:
        await decoy(store, USER, T0 + timedelta(seconds=45), limits=limits)

    assert refused.value.wait_seconds == 15


# Criterion 5 (AC-30; the rule on failed sends is in the module docstring of request_code)
@pytest.mark.parametrize("known", [True, False])
async def test_given_five_rows_never_marked_sent_when_a_sixth_is_created_then_it_is_refused_until_the_oldest_leaves(
    store: LoginRequests, known: bool
) -> None:
    limits = lowered(codes_per_hour=5)

    async def ask(moment: datetime) -> LoginRequest:
        if known:
            return await make(store, USER, RIGHT, moment, limits=limits)
        return await decoy(store, USER, moment, limits=limits)

    for index in range(5):
        await ask(T0 + timedelta(seconds=60 * index))

    with pytest.raises(LoginRequestRefused) as sixth:
        await ask(T0 + timedelta(seconds=300))
    with pytest.raises(LoginRequestRefused) as late:
        await ask(T0 + timedelta(seconds=3599))
    after = await ask(T0 + timedelta(seconds=3600))

    assert sixth.value.wait_seconds == 3300
    assert late.value.wait_seconds == 1
    assert after.id


# Criterion 5
async def test_given_sent_and_unsent_rows_when_the_hourly_cap_counts_then_both_count_from_created_at(
    store: LoginRequests,
) -> None:
    limits = lowered(codes_per_hour=2)
    sent = await make(store, USER, RIGHT, T0, limits=limits)
    await store.mark_sent(sent.id, T0 + timedelta(seconds=30))
    await make(store, USER, RIGHT, T0 + timedelta(seconds=10), limits=limits)

    with pytest.raises(LoginRequestRefused) as refused:
        await make(store, USER, RIGHT, T0 + timedelta(seconds=20), limits=limits)

    assert refused.value.wait_seconds == 3580  # from the creation of the first row, not from its send


# Criterion 6 is in agents/mail-triage/tests/db/test_login_request_client_migration.py
