# pyright: reportUnusedImport=false
# ruff: noqa: F811  # the shared fixtures are imported and used as parameters, like the other database tests
"""U-label-prefix-removal-11: the rename preview, the confirmation, the restore and the recently deleted record.

A real PostgreSQL, written as the web role (ADR-0061): the api reads the plan and writes only through
``confirm_label_rename`` and ``request_label_restore``.
"""

import logging
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
from tests.test_categories_api import (  # noqa: F401  # the app fixture and the constants of the list tests
    CSRF_KEY,
    MAILBOX,
    ORIGIN,
    USER,
    Api,
    api,
)

PREVIEW = "/api/label-rename"
CONFIRM = "/api/label-rename/confirmation"
RESTORE = "/api/label-rename/restore"
DELETED = "/api/label-rename/deleted"
GENERIC_409 = {"type": "about:blank", "title": "Conflict", "status": 409}
GENERIC_422 = {"type": "about:blank", "title": "Unprocessable content", "status": 422}
CANARY = "Canary-Zebra-Label"

# (label id, old name, new name, mail count, action)
ITEMS = [
    ("L1", "Assistant/Bills", "Bills", 3, "rename"),
    ("L2", "Assistant/Travel", "Travel", 40, "merge"),
    ("L3", "Assistant/Family", "Family", 12, "rename"),
]


class Client:
    """One signed-in session that sends the label rename requests."""

    def __init__(self, api: Api, headers: dict[str, str]) -> None:
        self.api = api
        self.headers = headers

    def _headers(self, drop: tuple[str, ...]) -> dict[str, str]:
        return {k: v for k, v in self.headers.items() if k not in drop}

    async def preview(self) -> Response:
        return await self.api.http.get(PREVIEW, headers=self.headers)

    async def deleted(self) -> Response:
        return await self.api.http.get(DELETED, headers=self.headers)

    async def confirm(self, body: Any, *, drop: tuple[str, ...] = (), raw: bytes | None = None) -> Response:
        headers = self._headers(drop)
        if raw is not None:
            headers["Content-Type"] = "application/json"
            return await self.api.http.post(CONFIRM, content=raw, headers=headers)
        return await self.api.http.post(CONFIRM, json=body, headers=headers)

    async def restore(self, *, drop: tuple[str, ...] = ()) -> Response:
        return await self.api.http.post(RESTORE, headers=self._headers(drop))


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


async def seed(
    owner: asyncpg.Connection,
    *,
    state: str = "pending",
    items: list[tuple[str, str, str, int, str]] | None = None,
    hashed: bool = True,
) -> str | None:
    """Write a plan as the owner and return its stored hash."""
    await owner.execute("insert into categories.mailbox (id) values ($1) on conflict do nothing", MAILBOX)
    await owner.execute(
        "insert into categories.label_migration (mailbox_id, state) values ($1, 'pending') on conflict do nothing",
        MAILBOX,
    )
    for label_id, old, new, count, action in ITEMS if items is None else items:
        await owner.execute(
            "insert into categories.label_rename_item (mailbox_id, label_id, old_name, new_name, mail_count, action) "
            "values ($1, $2, $3, $4, $5, $6)",
            MAILBOX,
            label_id,
            old,
            new,
            count,
            action,
        )
    stored = await owner.fetchval("select categories.label_plan_hash($1)", MAILBOX) if hashed else None
    await owner.execute("update categories.label_migration set plan_hash = $2 where mailbox_id = $1", MAILBOX, stored)
    if state != "pending":
        await owner.execute("update categories.label_rename_item set state = 'done' where mailbox_id = $1", MAILBOX)
        await owner.execute("update categories.label_migration set state = 'done' where mailbox_id = $1", MAILBOX)
    return stored


async def confirmations(owner: asyncpg.Connection) -> list[asyncpg.Record]:
    return await owner.fetch("select id, plan_hash, skipped_ids, channel from categories.label_confirmation")


async def state_of(owner: asyncpg.Connection) -> str:
    return await owner.fetchval("select state from categories.label_migration where mailbox_id = $1", MAILBOX)


# Criterion 1
async def test_given_a_pending_plan_when_the_preview_is_read_then_every_label_is_listed_largest_first(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    stored = await seed(owner)
    client = await sign_in(api)

    response = await client.preview()

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "pending"
    assert body["planHash"] == stored
    assert [i["id"] for i in body["items"]] == ["L2", "L3", "L1"]
    assert body["items"][0] == {
        "id": "L2",
        "oldName": "Assistant/Travel",
        "newName": "Travel",
        "mailCount": 40,
        "action": "merge",
        "itemState": "planned",
    }
    assert body["summary"] == {"labels": 3, "mails": 55}


async def test_given_no_plan_when_the_preview_is_read_then_the_state_is_none_and_the_list_empty(
    api: Api,
) -> None:
    client = await sign_in(api)

    response = await client.preview()

    assert response.status_code == 200
    assert response.json() == {
        "state": "none",
        "planHash": None,
        "items": [],
        "summary": {"labels": 0, "mails": 0},
    }


async def test_given_a_plan_still_being_built_when_the_preview_is_read_then_there_is_no_hash(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, hashed=False)
    client = await sign_in(api)

    body = (await client.preview()).json()

    assert body["planHash"] is None
    assert body["state"] == "pending"


async def test_given_a_plan_of_another_mailbox_when_the_preview_is_read_then_it_is_not_shown(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await owner.execute("insert into categories.mailbox (id) values ('second')")
    await owner.execute("insert into categories.label_migration (mailbox_id, state) values ('second', 'pending')")
    await owner.execute(
        "insert into categories.label_rename_item (mailbox_id, label_id, old_name, new_name, mail_count, action) "
        "values ('second', 'X', 'Assistant/X', 'X', 1, 'rename')"
    )
    client = await sign_in(api)

    assert (await client.preview()).json()["items"] == []


# Criterion 2 (AC 5)
async def test_given_the_preview_and_no_confirmation_when_it_is_read_then_nothing_was_changed(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner)
    client = await sign_in(api)
    before = await owner.fetch("select * from categories.label_rename_item order by label_id")

    for _ in range(3):
        assert (await client.preview()).status_code == 200

    assert await owner.fetch("select * from categories.label_rename_item order by label_id") == before
    assert await state_of(owner) == "pending"
    assert await confirmations(owner) == []
    assert await owner.fetchval("select count(*) from categories.label_restore_request") == 0


# Criterion 3
async def test_given_the_right_hash_when_confirmed_then_one_row_is_written_and_twice_is_still_one(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    stored = await seed(owner)
    client = await sign_in(api)

    first = await client.confirm({"planHash": stored, "skippedIds": []})
    second = await client.confirm({"planHash": stored, "skippedIds": []})

    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json() == second.json()
    rows = await confirmations(owner)
    assert len(rows) == 1
    assert (str(rows[0]["id"]), rows[0]["plan_hash"]) == (first.json()["confirmationId"], stored)
    assert await state_of(owner) == "confirmed"
    assert (await client.preview()).json()["state"] == "confirmed"


async def test_given_the_same_skip_set_in_another_order_when_confirmed_again_then_the_result_is_the_same(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    stored = await seed(owner)
    client = await sign_in(api)

    first = await client.confirm({"planHash": stored, "skippedIds": ["L1", "L3"]})
    second = await client.confirm({"planHash": stored, "skippedIds": ["L3", "L1", "L1"]})

    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json() == second.json()
    assert len(await confirmations(owner)) == 1


# Criterion 4
async def test_given_a_wrong_hash_when_confirmed_then_409_and_nothing_is_written(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner)
    client = await sign_in(api)

    response = await client.confirm({"planHash": "0" * 64, "skippedIds": []})

    assert response.status_code == 409
    assert response.json() == GENERIC_409
    assert await confirmations(owner) == []
    assert await state_of(owner) == "pending"


async def test_given_a_plan_that_changed_after_the_preview_when_the_old_hash_is_posted_then_409(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    stored = await seed(owner)
    client = await sign_in(api)
    await owner.execute("update categories.label_rename_item set new_name = 'Changed' where label_id = 'L1'")

    response = await client.confirm({"planHash": stored, "skippedIds": []})

    assert response.status_code == 409
    assert await confirmations(owner) == []


async def test_given_a_confirmed_plan_when_another_hash_or_skip_set_is_posted_then_409_and_one_row(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    stored = await seed(owner)
    client = await sign_in(api)
    assert (await client.confirm({"planHash": stored, "skippedIds": ["L1"]})).status_code == 200

    other_hash = await client.confirm({"planHash": "1" * 64, "skippedIds": ["L1"]})
    other_skips = await client.confirm({"planHash": stored, "skippedIds": []})

    assert (other_hash.status_code, other_skips.status_code) == (409, 409)
    assert len(await confirmations(owner)) == 1


async def test_given_a_plan_that_is_not_pending_when_confirmed_then_409_and_nothing_is_written(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    stored = await seed(owner, state="done")
    client = await sign_in(api)

    response = await client.confirm({"planHash": stored, "skippedIds": []})

    assert response.status_code == 409
    assert await confirmations(owner) == []


async def test_given_no_plan_when_confirmed_then_409(api: Api) -> None:
    client = await sign_in(api)

    assert (await client.confirm({"planHash": "a" * 64, "skippedIds": []})).status_code == 409


# Criterion 5
async def test_given_skipped_ids_when_confirmed_then_they_are_stored_as_skipped(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    stored = await seed(owner)
    client = await sign_in(api)

    response = await client.confirm({"planHash": stored, "skippedIds": ["L3", "L1"]})

    assert response.status_code == 200
    assert list((await confirmations(owner))[0]["skipped_ids"]) == ["L1", "L3"]


async def test_given_a_skipped_id_that_is_not_in_the_plan_when_confirmed_then_422_and_nothing_is_written(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    stored = await seed(owner)
    client = await sign_in(api)

    response = await client.confirm({"planHash": stored, "skippedIds": ["L1", "NOPE"]})

    assert response.status_code == 422
    assert response.json() == GENERIC_422
    assert await confirmations(owner) == []
    assert await state_of(owner) == "pending"


@pytest.mark.parametrize(
    "raw",
    [
        b'{"planHash": "%s", "skippedIds": [], "extra": 1}' % (b"a" * 64),
        b'{"skippedIds": []}',
        b'{"planHash": "short", "skippedIds": []}',
        b'{"planHash": "%s", "skippedIds": "L1"}' % (b"a" * 64),
        b'{"planHash": "%s", "skippedIds": [1]}' % (b"a" * 64),
        b'{"planHash": "%s"' % (b"a" * 64),
        b"[]",
    ],
)
async def test_given_a_body_of_the_wrong_shape_when_confirmed_then_422_and_nothing_is_written(
    api: Api,
    owner: asyncpg.Connection,
    raw: bytes,
) -> None:
    await seed(owner)
    client = await sign_in(api)

    response = await client.confirm(None, raw=raw)

    assert response.status_code == 422
    assert await confirmations(owner) == []


async def test_given_a_body_that_is_not_json_when_confirmed_then_415(api: Api, owner: asyncpg.Connection) -> None:
    await seed(owner)
    client = await sign_in(api)
    headers = {**client.headers, "Content-Type": "text/plain"}

    response = await api.http.post(CONFIRM, content=b"x", headers=headers)

    assert response.status_code == 415


# Criterion 6 (AC 27)
@pytest.mark.parametrize("state", ["confirmed", "done"])
async def test_given_a_renamed_plan_when_restore_is_posted_then_one_request_exists_and_twice_is_still_one(
    api: Api,
    owner: asyncpg.Connection,
    state: str,
) -> None:
    stored = await seed(owner)
    client = await sign_in(api)
    if state == "confirmed":
        assert (await client.confirm({"planHash": stored, "skippedIds": []})).status_code == 200
    else:
        await owner.execute("update categories.label_rename_item set state = 'done'")
        await owner.execute("update categories.label_migration set state = 'done'")

    first = await client.restore()
    second = await client.restore()

    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json() == second.json()
    assert await owner.fetchval("select count(*) from categories.label_restore_request") == 1
    assert str(await owner.fetchval("select id from categories.label_restore_request")) == first.json()["requestId"]


async def test_given_a_plan_not_yet_confirmed_when_restore_is_posted_then_409_and_nothing_is_written(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner)
    client = await sign_in(api)

    response = await client.restore()

    assert response.status_code == 409
    assert response.json() == GENERIC_409
    assert await owner.fetchval("select count(*) from categories.label_restore_request") == 0


# Criterion 7 (AC 29)
async def test_given_deleted_labels_when_read_then_names_for_the_retention_period_newest_first(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    now = api.app.state.clock.now()
    await owner.execute("insert into categories.mailbox (id) values ($1), ('second')", MAILBOX)
    days = 30  # the default while the schedule has no row
    rows = [
        (MAILBOX, "Old name", now - timedelta(days=days + 1)),
        (MAILBOX, "Middle", now - timedelta(days=2)),
        (MAILBOX, "Newest", now - timedelta(hours=1)),
        ("second", "Foreign", now - timedelta(hours=1)),
    ]
    for mailbox, name, at in rows:
        await owner.execute(
            "insert into categories.deleted_label (mailbox_id, label_id_hash, name, deleted_at) "
            "values ($1, $2, $3, $4)",
            mailbox,
            uuid.uuid4().hex + uuid.uuid4().hex,
            name,
            at,
        )
    client = await sign_in(api)

    response = await client.deleted()

    assert response.status_code == 200
    items = response.json()["items"]
    assert [i["name"] for i in items] == ["Newest", "Middle"]
    assert set(items[0]) == {"name", "deletedAt"}
    assert response.json()["retentionDays"] == days


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
async def test_given_the_recently_deleted_route_when_written_to_then_it_is_refused(
    api: Api,
    owner: asyncpg.Connection,
    method: str,
) -> None:
    client = await sign_in(api)

    response = await api.http.request(method, DELETED, headers=client.headers, json={})

    assert response.status_code == 405
    assert await owner.fetchval("select count(*) from categories.deleted_label") == 0


# Criterion 8
async def test_given_no_session_when_called_then_every_route_answers_401(api: Api, owner: asyncpg.Connection) -> None:
    stored = await seed(owner)
    client = Client(api, {})

    answers = [
        await client.preview(),
        await client.deleted(),
        await client.confirm({"planHash": stored, "skippedIds": []}),
        await client.restore(),
    ]

    assert [a.status_code for a in answers] == [401, 401, 401, 401]
    assert await confirmations(owner) == []


@pytest.mark.parametrize("drop", [("X-CSRF-Token",), ("Origin",)])
async def test_given_no_csrf_token_or_origin_when_written_then_403_and_nothing_is_written(
    api: Api,
    owner: asyncpg.Connection,
    drop: tuple[str, ...],
) -> None:
    stored = await seed(owner)
    client = await sign_in(api)

    confirm = await client.confirm({"planHash": stored, "skippedIds": []}, drop=drop)
    restore = await client.restore(drop=drop)

    assert (confirm.status_code, restore.status_code) == (403, 403)
    assert await confirmations(owner) == []
    assert await state_of(owner) == "pending"
    assert await owner.fetchval("select count(*) from categories.label_restore_request") == 0


# Label names stay out of logs, audit and errors (threat model T5, T6, T20)
async def test_given_a_canary_label_name_when_every_route_is_used_then_it_is_only_in_the_two_reads(
    api: Api,
    owner: asyncpg.Connection,
    canary_log_records: list[logging.LogRecord],
) -> None:
    stored = await seed(owner, items=[("C1", f"Assistant/{CANARY}", CANARY, 5, "rename")])
    await owner.execute("insert into categories.mailbox (id) values ($1) on conflict do nothing", MAILBOX)
    await owner.execute(
        "insert into categories.deleted_label (mailbox_id, label_id_hash, name, deleted_at) values ($1, $2, $3, $4)",
        MAILBOX,
        "a" * 64,
        CANARY,
        api.app.state.clock.now(),
    )
    client = await sign_in(api)

    reads = [await client.preview(), await client.deleted()]
    refusals = [
        await client.confirm({"planHash": "0" * 64, "skippedIds": ["C1"]}),
        await client.confirm({"planHash": stored, "skippedIds": [CANARY]}),
        await client.confirm(None, raw=b'{"planHash": "x", "skippedIds": ["%s"], "e": 1}' % CANARY.encode()),
        await client.restore(),
    ]
    await client.confirm({"planHash": stored, "skippedIds": []})
    refusals.append(await client.confirm({"planHash": "1" * 64, "skippedIds": ["C1"]}))

    assert all(CANARY in r.text for r in reads)
    assert [r.status_code for r in refusals] == [409, 422, 422, 409, 409]
    assert not [r for r in refusals if CANARY in r.text]
    formatted = [logging.Formatter().format(record) for record in canary_log_records]
    assert not [text for text in formatted if CANARY in text]
    audit = await owner.fetch("select row_to_json(e)::text as t from web_auth.security_event e")
    assert not [row for row in audit if CANARY in row["t"]]
