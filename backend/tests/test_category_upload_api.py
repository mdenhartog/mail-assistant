# pyright: reportUnusedImport=false
# ruff: noqa: F811  # the shared fixtures are imported and used as parameters, like the other database tests
"""U-label-structure-12: upload, preview, confirm and restore of the category list against a real PostgreSQL."""

import asyncio
import hashlib
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
from tests.fakes import make_settings
from tests.test_categories_api import (  # noqa: F401  # the app fixture and the seed helpers of the list tests
    CSRF_KEY,
    MAILBOX,
    ORIGIN,
    USER,
    VERSIONS,
    Api,
    api,
    seed,
)

UPLOAD = "/api/categories/upload"
RESTORE = "/api/categories/restore-previous"
YAML = "application/yaml"
FILE = (
    "schema: 1\n"
    "generalInstructions: Be brief\n"
    "categories:\n"
    "  - name: Invoices\n"
    "    description: Bills and receipts\n"
    "  - name: Travel\n"
    "    description: Trips\n"
    "    senders:\n"
    "      - airline.example.nl\n"
)
CANARIES = ("canary-description-12", "canary-sender-12@example.nl", "canary-instructions-12", "canary-name-12")
CANARY_FILE = (
    "schema: 1\n"
    "generalInstructions: canary-instructions-12\n"
    "categories:\n"
    "  - name: canary-name-12\n"
    "    description: canary-description-12\n"
    "    senders:\n"
    "      - canary-sender-12@example.nl\n"
)


class Client:
    """One signed-in session that sends the upload routes' requests."""

    def __init__(self, api: Api, headers: dict[str, str]) -> None:
        self.api = api
        self.headers = headers

    async def send(  # noqa: PLR0913  # one switch per part of the request
        self,
        path: str,
        *,
        content: bytes | None = None,
        json_body: Any = None,
        content_type: str | None = None,
        drop: tuple[str, ...] = (),
        extra: dict[str, str] | None = None,
    ) -> Response:
        headers = {k: v for k, v in self.headers.items() if k not in drop}
        if content_type:
            headers["Content-Type"] = content_type
        headers.update(extra or {})
        return await self.api.http.post(path, content=content, json=json_body, headers=headers)

    async def upload(self, text: str = FILE, **switches: Any) -> Response:
        return await self.send(UPLOAD, content=text.encode(), content_type=YAML, **switches)

    async def confirm(self, preview: dict[str, Any], **switches: Any) -> Response:
        return await self.send(
            f"{UPLOAD}/{preview['previewId']}/confirm", json_body={"fileHash": preview["fileHash"]}, **switches
        )

    async def restore(self, version: int, **switches: Any) -> Response:
        return await self.send(RESTORE, json_body={"version": version}, **switches)


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


async def preview_of(client: Client, text: str = FILE) -> dict[str, Any]:
    response = await client.upload(text)
    assert response.status_code == 200, (response.text, dict(response.headers))
    return response.json()


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# Found by the R1 journey (U-label-structure-17): many new categories were counted as one
async def test_given_several_new_categories_when_uploaded_then_the_preview_counts_each_of_them(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)
    names = [f"  - name: Fresh {n}\n    description: d\n" for n in range(5)]
    text = "schema: 1\ncategories:\n" + "".join(names)

    body = await preview_of(client, text)

    assert (body["added"], body["changed"], body["removed"]) == (5, 0, 1)


# Criterion 1
async def test_given_a_valid_file_when_uploaded_then_the_preview_has_the_counts_and_only_the_preview_row_is_stored(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills"), ("Old", "Gone soon")])
    client = await sign_in(api)

    response = await client.upload()

    assert response.status_code == 200
    body = response.json()
    assert body["added"] == 1
    assert body["changed"] == 1
    assert body["removed"] == 1
    assert body["removedCategories"] == ["Old"]
    assert body["baseVersion"] == 1
    assert body["fileHash"] == digest(FILE)
    uuid.UUID(body["previewId"])
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1
    assert await owner.fetchval("select count(*) from categories.upload_preview") == 1
    row = await owner.fetchrow(
        "select base_version, file_hash, session_digest, expires_at from categories.upload_preview"
    )
    assert row is not None
    assert (row["base_version"], row["file_hash"]) == (1, digest(FILE))
    assert row["expires_at"] - api.app.state.clock.now() == timedelta(minutes=15)
    assert await owner.fetchval("select count(*) from categories.list_audit") == 1


async def test_given_a_body_that_is_not_yaml_when_uploaded_then_415(api: Api, owner: asyncpg.Connection) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)

    response = await client.send(UPLOAD, content=FILE.encode(), content_type="application/json")

    assert response.status_code == 415


async def test_given_no_list_yet_when_uploaded_then_409(api: Api) -> None:
    client = await sign_in(api)

    assert (await client.upload()).status_code == 409


# Criterion 2
async def test_given_a_preview_when_confirmed_then_one_new_version_with_audit_and_unconfirmed_changes_nothing(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills"), ("Old", "Gone soon")])
    client = await sign_in(api)
    preview = await preview_of(client)
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1  # not confirmed: nothing changed

    response = await client.confirm(preview)

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 2
    assert [(c["name"], c["description"]) for c in body["categories"]] == [
        ("Invoices", "Bills and receipts"),
        ("Travel", "Trips"),
    ]
    assert body["generalInstructions"] == "Be brief"
    assert await owner.fetchval(VERSIONS, MAILBOX) == 2
    audit = await owner.fetch("select version, channel from categories.list_audit order by 1")
    assert [(row["version"], row["channel"]) for row in audit] == [(1, "operator"), (2, "web")]
    assert await owner.fetchval("select count(*) from categories.upload_preview where used_at is not null") == 1


# Criterion 3
@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("schema: 1\ncategories:\n  - &a\n    name: X\n    description: y\n", "anchor"),
        ("schema: 1\ncategories: !!python/object:os.system x\n", "tag"),
        ("schema: 2\ncategories: []\n", "schema_unsupported"),
        ("schema: 1\ncategories:\n  - name: ''\n    description: ''\n  - name: A/\n    description: d\n", "name_empty"),
    ],
)
async def test_given_an_invalid_or_hostile_file_when_uploaded_then_422_with_line_and_field_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,
    text: str,
    rule: str,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)

    response = await client.upload(text)

    assert response.status_code == 422
    problems = response.json()["problems"]
    assert rule in [p["rule"] for p in problems]
    assert all(isinstance(p["line"], int) and p["field"] and p["message"] for p in problems)
    assert await owner.fetchval("select count(*) from categories.upload_preview") == 0
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


async def test_given_a_file_above_the_limit_when_uploaded_then_413_before_parsing(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)

    response = await client.upload("x" * (320 * 1024 + 1))

    assert response.status_code == 413
    assert await owner.fetchval("select count(*) from categories.upload_preview") == 0


# Criterion 4
async def test_given_a_confirm_from_another_session_then_409_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    preview = await preview_of(await sign_in(api))

    response = await (await sign_in(api)).confirm(preview)

    assert response.status_code == 409
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1
    assert await owner.fetchval("select count(*) from categories.upload_preview where used_at is not null") == 0


async def test_given_a_changed_file_hash_then_409_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)
    preview = await preview_of(client)

    response = await client.confirm({**preview, "fileHash": digest("another file")})

    assert response.status_code == 409
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


async def test_given_an_unknown_preview_id_then_409(api: Api, owner: asyncpg.Connection) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)
    preview = await preview_of(client)

    response = await client.confirm({**preview, "previewId": str(uuid.UUID(int=7))})

    assert response.status_code == 409


async def test_given_an_expired_preview_then_409_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)
    preview = await preview_of(client)
    api.app.state.clock.advance(timedelta(minutes=15, seconds=1))

    response = await client.confirm(preview)

    assert response.status_code == 409
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


async def test_given_the_list_changed_since_the_preview_then_409_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)
    preview = await preview_of(client)
    await owner.execute("insert into categories.list_version (mailbox_id, version) values ($1, 2)", MAILBOX)

    response = await client.confirm(preview)

    assert response.status_code == 409
    assert await owner.fetchval("select count(*) from categories.category where version = 2") == 0


async def test_given_a_double_submit_then_one_version_and_the_second_gets_409(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)
    preview = await preview_of(client)

    first, second = await asyncio.gather(client.confirm(preview), client.confirm(preview))

    assert sorted([first.status_code, second.status_code]) == [200, 409]
    assert await owner.fetchval(VERSIONS, MAILBOX) == 2


async def test_given_a_used_preview_when_confirmed_again_then_409(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)
    preview = await preview_of(client)
    assert (await client.confirm(preview)).status_code == 200

    assert (await client.confirm(preview)).status_code == 409
    assert await owner.fetchval(VERSIONS, MAILBOX) == 2


# Criterion 5
@pytest.mark.parametrize(
    "switch",
    [
        {"drop": ("X-CSRF-Token",)},
        {"extra": {"Origin": "https://evil.example.test"}},
        {"drop": ("Origin",)},
    ],
)
async def test_given_no_token_or_a_foreign_origin_when_upload_confirm_or_restore_then_403(
    api: Api,
    owner: asyncpg.Connection,
    switch: dict[str, Any],
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)
    preview = await preview_of(client)

    assert (await client.upload(**switch)).status_code == 403
    assert (await client.confirm(preview, **switch)).status_code == 403
    assert (await client.restore(1, **switch)).status_code == 403
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1
    assert await owner.fetchval("select count(*) from categories.upload_preview") == 1


async def test_given_no_session_when_upload_confirm_or_restore_then_401(api: Api) -> None:
    client = Client(api, {})

    assert (await client.upload()).status_code == 401
    assert (await client.confirm({"previewId": str(uuid.UUID(int=1)), "fileHash": digest("x")})).status_code == 401
    assert (await client.restore(1)).status_code == 401


async def test_given_ten_saves_in_an_hour_when_upload_confirm_or_restore_then_429(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)
    preview = await preview_of(client)
    for number in range(10):  # one session each: the previews of a session count against the limit too
        saver = await sign_in(api)
        text = f"schema: 1\ncategories:\n  - name: Name {number}\n    description: d\n"
        assert (await saver.confirm(await preview_of(saver, text))).status_code == 200

    refused = [
        await client.upload(),
        await client.confirm(preview),
        await client.restore(11),
    ]

    assert [r.status_code for r in refused] == [429, 429, 429]
    assert 1 <= int(refused[0].headers["retry-after"]) <= 3600
    assert await owner.fetchval(VERSIONS, MAILBOX) == 11


# RED-006 (INT-008 R1): unconfirmed previews count against the hourly limit too
async def test_given_two_saves_an_hour_when_one_session_uploads_three_files_unconfirmed_then_the_third_is_429(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    api.app.state.settings = make_settings(categories_mailbox_id=MAILBOX, category_saves_per_hour=2)
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)

    statuses = [(await client.upload()).status_code for _ in range(2)]
    refused = await client.upload()

    assert statuses == [200, 200]
    assert refused.status_code == 429
    assert 1 <= int(refused.headers["retry-after"]) <= 3600
    assert await owner.fetchval("select count(*) from categories.upload_preview") == 2


# Criterion 6
async def test_given_equal_names_when_confirmed_then_they_keep_their_id_and_a_missing_name_is_removed(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    invoices, old = await seed(owner, [("Invoices", "Bills"), ("Old", "Gone soon")])
    client = await sign_in(api)
    fullwidth = "".join(chr(ord(c) + 0xFEE0) for c in "INVOICES")  # NFKC folds it to the stored name
    lines = ["schema: 1", "categories:", f"  - name: {fullwidth}", "    description: New", "  - name: Fresh"]
    text = "\n".join([*lines, "    description: d", ""])
    preview = await preview_of(client, text)

    body = (await client.confirm(preview)).json()

    assert body["categories"][0]["id"] == invoices
    assert body["categories"][0]["name"] == "INVOICES"
    assert body["categories"][1]["id"] not in {invoices, old}
    assert old not in [c["id"] for c in body["categories"]]


# Criterion 7
async def test_given_a_confirmed_upload_when_restore_previous_then_a_new_version_equals_the_previous_one(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    invoices, old = await seed(
        owner,
        [("Invoices", "Bills"), ("Old", "Gone soon")],
        instructions="First",
        details={1: {"senders": [("old.example.nl", True, True)], "notify": True}},
    )
    client = await sign_in(api)
    first = (await client.confirm(await preview_of(client))).json()
    assert first["version"] == 2

    response = await client.restore(2)

    assert response.status_code == 200
    restored = response.json()
    assert restored["version"] == 3
    assert [c["id"] for c in restored["categories"]] == [invoices, old]
    assert restored["generalInstructions"] == "First"
    assert restored["categories"][1]["senders"] == [{"entry": "old.example.nl", "subdomains": True, "skippedCount": 0}]
    assert restored["categories"][1]["notify"] is True
    assert await owner.fetchval(VERSIONS, MAILBOX) == 3


async def test_given_a_stale_version_or_no_previous_version_when_restore_then_409(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)

    assert (await client.restore(1)).status_code == 409  # version 1 has no previous version
    assert (await client.confirm(await preview_of(client))).status_code == 200
    assert (await client.restore(1)).status_code == 409  # the list is at version 2
    assert await owner.fetchval(VERSIONS, MAILBOX) == 2


# Criterion 8
async def test_given_canary_strings_in_the_file_then_no_log_response_or_audit_row_carries_them_but_the_list_does(
    api: Api,
    owner: asyncpg.Connection,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    caplog.set_level(logging.DEBUG)
    client = await sign_in(api)
    hostile = CANARY_FILE + "  - name: canary-name-12\n    description: canary-description-12\n"

    refused = await client.upload(hostile)
    preview = await client.upload(CANARY_FILE)
    confirmed = await client.confirm(preview.json())

    assert (refused.status_code, preview.status_code, confirmed.status_code) == (422, 200, 200)
    texts = [refused.text, preview.text, caplog.text]
    assert [(c, i) for c in CANARIES for i, t in enumerate(texts) if c in t] == []
    assert [c["name"] for c in confirmed.json()["categories"]] == ["canary-name-12"]  # the list itself holds it
    # The list audit records the confirmed list by design (ADR-0043), so it holds the name; the sender and the general
    # instructions are not in it (unit 14 adds them to the audit on purpose).
    audit = await owner.fetch(
        "select new_list::text as new_list from categories.list_audit order by version desc limit 1"
    )
    assert "canary-name-12" in audit[0]["new_list"]


async def test_given_the_database_refuses_the_write_when_confirmed_then_500_without_a_canary(
    api: Api,
    owner: asyncpg.Connection,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)
    preview = await preview_of(client, CANARY_FILE)
    await owner.execute(
        "alter table categories.category_sender add constraint ck_canary check (entry <> 'canary-sender-12@example.nl')"
    )
    caplog.set_level(logging.DEBUG)

    response = await client.confirm(preview)

    assert response.status_code == 500
    assert [c for c in CANARIES if c in response.text or c in caplog.text] == []
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


# U-label-structure-19: the archive label in the file (criteria 2 and 3, and the RED-004 finding of R1)
ARCHIVE_FILE = FILE.replace("categories:", "archiveLabel: Bewaard\ncategories:")


async def test_given_a_file_with_a_new_archive_label_when_uploaded_then_the_preview_reports_it_and_confirm_stores_it(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills and receipts"), ("Travel", "Trips")], instructions="Be brief")
    client = await sign_in(api)

    preview = await preview_of(client, ARCHIVE_FILE)
    assert preview["archiveLabelChanged"] is True
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1  # a preview stores no list

    response = await client.confirm(preview)

    assert response.status_code == 200
    assert response.json()["archiveLabel"] == "Bewaard"
    assert await owner.fetchval("select archive_label from categories.list_settings where version = 2") == "Bewaard"


@pytest.mark.parametrize("stored_name", ["Bewaard", "Assistant/Archive"])
async def test_given_a_file_without_an_archive_label_when_uploaded_then_the_stored_name_is_kept(
    api: Api,
    owner: asyncpg.Connection,
    stored_name: str,
) -> None:
    await seed(
        owner,
        [("Invoices", "Bills and receipts"), ("Travel", "Trips")],
        instructions="Be brief",
        details={1: {"senders": [("airline.example.nl", True, False)]}},
        archive_label=stored_name,
    )
    client = await sign_in(api)

    preview = await preview_of(client)

    assert preview["archiveLabelChanged"] is False
    confirmed = await client.confirm(preview)
    assert confirmed.json()["archiveLabel"] == stored_name
    assert confirmed.json()["version"] == 1  # nothing else differs: no new version, so no rename


async def test_given_a_file_without_an_archive_label_and_other_changes_when_confirmed_then_the_stored_name_is_kept(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")], archive_label="Bewaard")
    client = await sign_in(api)

    confirmed = await client.confirm(await preview_of(client))

    assert (confirmed.json()["version"], confirmed.json()["archiveLabel"]) == (2, "Bewaard")
    assert await owner.fetchval("select archive_label from categories.list_settings where version = 2") == "Bewaard"


async def test_given_the_same_archive_label_when_uploaded_then_it_is_not_reported_as_changed(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")], archive_label="Bewaard")
    client = await sign_in(api)

    preview = await preview_of(client, ARCHIVE_FILE)

    assert preview["archiveLabelChanged"] is False


@pytest.mark.parametrize("name", ["INBOX", "Assistant/Invoices", "Assistant/Other", "Assistant/Invoices/Old"])
async def test_given_a_file_with_an_invalid_archive_label_when_uploaded_then_422_on_the_field_and_nothing_is_stored(
    api: Api,
    owner: asyncpg.Connection,
    name: str,
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)

    response = await client.upload(ARCHIVE_FILE.replace("Bewaard", name))

    assert response.status_code == 422
    assert [p["field"] for p in response.json()["problems"]] == ["archiveLabel"]
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


async def test_given_a_restore_when_the_previous_version_had_another_archive_label_then_it_comes_back(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills and receipts"), ("Travel", "Trips")], archive_label="Eerder")
    client = await sign_in(api)
    assert (await client.confirm(await preview_of(client, ARCHIVE_FILE))).json()["version"] == 2

    restored = (await client.restore(2)).json()

    assert (restored["version"], restored["archiveLabel"]) == (3, "Eerder")
