# pyright: reportUnusedImport=false
# ruff: noqa: F811  # the shared fixtures are imported and used as parameters, like the other database tests
"""U-label-structure-21: the sort-again request routes against a real PostgreSQL, written as the web role (ADR-0056)."""

import asyncio
import uuid
from datetime import timedelta
from typing import Any

import asyncpg
import pytest
from httpx import Response

from app.auth.cookies import COOKIE_NAME
from app.auth.csrf import csrf_token
from tests.db.conftest import (  # noqa: F401  # the shared fixtures of U-09
    db,
    owner,
    pg_server,
    server,
    template_name,
    web_database,
)
from tests.fakes import make_settings
from tests.test_categories_api import (  # noqa: F401  # the app fixture and the constants of the list tests
    CSRF_KEY,
    MAILBOX,
    ORIGIN,
    USER,
    Api,
    api,
)

POST = "/api/resort-requests"
LATEST = "/api/resort-requests/latest"
COUNT = "select count(*) from categories.resort_request where mailbox_id = $1"


class Client:
    """One signed-in session that sends the sort-again requests."""

    def __init__(self, api: Api, headers: dict[str, str]) -> None:
        self.api = api
        self.headers = headers

    async def post(self, body: Any = None, *, raw: bytes | None = None, drop: tuple[str, ...] = ()) -> Response:
        headers = {k: v for k, v in self.headers.items() if k not in drop}
        if raw is not None:
            headers["Content-Type"] = "application/json"
            return await self.api.http.post(POST, content=raw, headers=headers)
        return await self.api.http.post(POST, json=body, headers=headers)

    async def ask(self, threshold: Any, **switches: Any) -> Response:
        return await self.post({"threshold": threshold}, **switches)

    async def latest(self) -> Response:
        return await self.api.http.get(LATEST, headers=self.headers)


async def sign_in(api: Api) -> Client:
    value, created = await api.store.create(USER, api.app.state.clock.now())
    return Client(
        api,
        {
            "X-CSRF-Token": csrf_token(CSRF_KEY, created.id_hash),
            "Origin": ORIGIN,
            "Cookie": f"{COOKIE_NAME}={value}",
        },
    )


async def mailbox(owner: asyncpg.Connection) -> None:
    await owner.execute("insert into categories.mailbox (id) values ($1) on conflict do nothing", MAILBOX)


async def seed_plan(
    owner: asyncpg.Connection, state: str, request_id: uuid.UUID | None = None, *, kind: str = "review"
) -> None:
    await mailbox(owner)
    await owner.execute(
        "insert into categories.plan (mailbox_id, id, list_version, state, checked_count, cap, unclear_count, "
        "not_looked_at, kind, request_id, terminal_at) values ($1, $2, 1, $3, 0, 10, 0, 0, $4, $5, "
        "case when $6 then now() end)",
        MAILBOX,
        uuid.uuid4(),
        state,
        kind,
        request_id,
        state in ("applied", "discarded"),
    )


# Criterion 1
@pytest.mark.parametrize("threshold", [50, 100, 75])
async def test_given_a_threshold_from_50_to_100_when_posted_then_a_request_exists_and_the_response_says_so(
    api: Api,
    owner: asyncpg.Connection,
    threshold: int,
) -> None:
    await mailbox(owner)
    client = await sign_in(api)

    response = await client.ask(threshold)

    assert response.status_code == 201
    body = response.json()
    assert body["threshold"] == threshold
    row = await owner.fetchrow("select id, threshold, channel from categories.resort_request")
    assert row is not None
    assert (str(row["id"]), row["threshold"], row["channel"]) == (body["requestId"], threshold, "web")
    assert await owner.fetchval(COUNT, MAILBOX) == 1


# Criterion 2
@pytest.mark.parametrize("threshold", [49, 0, -1, 101, 1000, 50.5, 50.0, "50 ", "50", "abc", "", True, None, [50]])
async def test_given_a_threshold_that_is_not_an_integer_from_50_to_100_when_posted_then_422_and_no_request(
    api: Api,
    owner: asyncpg.Connection,
    threshold: Any,
) -> None:
    await mailbox(owner)
    client = await sign_in(api)

    response = await client.ask(threshold)

    assert response.status_code == 422
    assert response.json() == {"type": "about:blank", "title": "Unprocessable content", "status": 422}
    assert await owner.fetchval(COUNT, MAILBOX) == 0


@pytest.mark.parametrize("raw", [b"{}", b'{"threshold": 60, "extra": 1}', b'{"threshold": 60', b"[]", b"60"])
async def test_given_a_body_of_the_wrong_shape_when_posted_then_422_and_no_request(
    api: Api,
    owner: asyncpg.Connection,
    raw: bytes,
) -> None:
    await mailbox(owner)
    client = await sign_in(api)

    assert (await client.post(raw=raw)).status_code == 422
    assert await owner.fetchval(COUNT, MAILBOX) == 0


# Criterion 3
@pytest.mark.parametrize("state", ["building", "ready", "scheduled", "applying"])
async def test_given_an_open_plan_when_posted_then_409_and_no_request(
    api: Api,
    owner: asyncpg.Connection,
    state: str,
) -> None:
    await seed_plan(owner, state)
    client = await sign_in(api)

    response = await client.ask(60)

    assert response.status_code == 409
    assert response.json() == {"type": "about:blank", "title": "Conflict", "status": 409}
    assert await owner.fetchval(COUNT, MAILBOX) == 0


async def test_given_a_request_the_agent_has_not_turned_into_a_plan_when_posted_again_then_409_and_one_request(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await mailbox(owner)
    client = await sign_in(api)

    first = await client.ask(60)
    second = await client.ask(70)

    assert (first.status_code, second.status_code) == (201, 409)
    assert await owner.fetchval(COUNT, MAILBOX) == 1
    assert await owner.fetchval("select threshold from categories.resort_request") == 60


async def test_given_two_posts_at_once_when_both_arrive_then_one_request_and_one_409(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await mailbox(owner)
    client = await sign_in(api)

    answers = await asyncio.gather(*(client.ask(60) for _ in range(5)))

    assert sorted(a.status_code for a in answers) == [201, 409, 409, 409, 409]
    assert await owner.fetchval(COUNT, MAILBOX) == 1


async def test_given_a_request_whose_plan_has_ended_when_posted_then_a_new_request_is_made(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await mailbox(owner)
    client = await sign_in(api)
    first = (await client.ask(60)).json()
    await seed_plan(owner, "building", uuid.UUID(first["requestId"]), kind="auto")
    assert (await client.ask(70)).status_code == 409  # the plan is open
    await owner.execute("update categories.plan set state = 'replaced', terminal_at = now()")

    third = await client.ask(70)

    assert third.status_code == 201
    assert await owner.fetchval(COUNT, MAILBOX) == 2


# Criterion 4
@pytest.mark.parametrize(
    "switch",
    [{"drop": ("X-CSRF-Token",)}, {"drop": ("Origin",)}],
)
async def test_given_no_token_or_no_origin_when_posted_then_403_and_no_request(
    api: Api,
    owner: asyncpg.Connection,
    switch: dict[str, Any],
) -> None:
    await mailbox(owner)
    client = await sign_in(api)

    response = await client.ask(60, drop=switch["drop"])

    assert response.status_code == 403
    assert await owner.fetchval(COUNT, MAILBOX) == 0


async def test_given_a_foreign_origin_when_posted_then_403_and_no_request(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await mailbox(owner)
    client = await sign_in(api)
    client.headers["Origin"] = "https://evil.example.test"

    assert (await client.ask(60)).status_code == 403
    assert await owner.fetchval(COUNT, MAILBOX) == 0


async def test_given_no_session_when_posted_or_read_then_401(api: Api, owner: asyncpg.Connection) -> None:
    await mailbox(owner)
    client = Client(api, {})

    assert (await client.ask(60)).status_code == 401
    assert (await client.latest()).status_code == 401
    assert await owner.fetchval(COUNT, MAILBOX) == 0


async def test_given_the_hourly_limit_used_up_when_posted_then_429_with_retry_after_until_the_oldest_ages_out(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    api.app.state.settings = make_settings(categories_mailbox_id=MAILBOX, category_saves_per_hour=2)
    await mailbox(owner)
    for _ in range(2):
        await owner.execute("insert into categories.resort_request (mailbox_id, threshold) values ($1, 60)", MAILBOX)
    await seed_plan(owner, "applied")
    client = await sign_in(api)

    refused = await client.ask(60)

    assert refused.status_code == 429
    assert 1 <= int(refused.headers["retry-after"]) <= 3600
    assert await owner.fetchval(COUNT, MAILBOX) == 2


async def test_given_requests_older_than_an_hour_when_posted_then_they_do_not_count(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    api.app.state.settings = make_settings(categories_mailbox_id=MAILBOX, category_saves_per_hour=1)
    await mailbox(owner)
    old = api.app.state.clock.now() - timedelta(hours=2)
    await owner.execute("alter table categories.resort_request disable trigger resort_request_derive")
    await owner.execute(
        "insert into categories.resort_request (mailbox_id, threshold, at) values ($1, 60, $2)", MAILBOX, old
    )
    await owner.execute("alter table categories.resort_request enable trigger resort_request_derive")
    row_id = await owner.fetchval("select id from categories.resort_request")
    await seed_plan(owner, "applied", row_id)
    client = await sign_in(api)

    assert (await client.ask(60)).status_code == 201


# Criterion 5
async def test_given_the_first_visit_when_the_latest_is_read_then_the_value_is_50(api: Api) -> None:
    client = await sign_in(api)

    response = await client.latest()

    assert response.status_code == 200
    assert response.json() == {"threshold": 50}


async def test_given_requests_when_the_latest_is_read_then_it_is_the_threshold_of_the_newest(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await mailbox(owner)
    client = await sign_in(api)
    await owner.execute("insert into categories.resort_request (mailbox_id, threshold) values ($1, 80)", MAILBOX)
    first = await owner.fetchval("select id from categories.resort_request")
    await seed_plan(owner, "applied", first)
    assert (await client.ask(65)).status_code == 201

    assert (await client.latest()).json() == {"threshold": 65}


async def test_given_a_request_of_another_mailbox_when_the_latest_is_read_then_it_is_not_used(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await owner.execute("insert into categories.mailbox (id) values ('second')")
    await owner.execute("insert into categories.resort_request (mailbox_id, threshold) values ('second', 90)")
    client = await sign_in(api)

    assert (await client.latest()).json() == {"threshold": 50}
