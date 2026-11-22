# pyright: reportUnusedImport=false
# ruff: noqa: F811  # the shared fixtures are imported and used as parameters, like the other database tests
"""The per-entry skipped counts of ``GET /api/categories`` (U-label-structure-37, AC-16)."""

import asyncpg

from tests.db.conftest import (  # noqa: F401  # the shared fixtures of U-09, used here without editing them
    db,
    owner,
    pg_server,
    server,
    template_name,
    web_database,
)
from tests.test_categories_api import (  # noqa: F401  # the app fixture and the seed helpers of the list tests
    MAILBOX,
    OTHER_MAILBOX,
    VERSIONS,
    Api,
    api,
    entry,
    get,
    put,
    seed,
)

SENDERS = {0: {"senders": [("a@example.com", False, False), ("example.org", True, True)]}}


async def skip(owner: asyncpg.Connection, text: str, skipped: int, mailbox: str = MAILBOX) -> None:
    await owner.execute(
        "insert into categories.sender_skip (mailbox_id, entry, skipped) values ($1, $2, $3)", mailbox, text, skipped
    )


# Criterion 1
async def test_given_counts_for_two_entries_when_get_then_each_carries_its_count_and_a_missing_row_is_0(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(
        owner, [("Invoices", "Bills")], details={0: {"senders": [*SENDERS[0]["senders"], ("b.org", True, False)]}}
    )
    await skip(owner, "a@example.com", 4)
    await skip(owner, "example.org", 17)

    response = await get(api)

    senders = response.json()["categories"][0]["senders"]
    assert senders == [
        {"entry": "a@example.com", "subdomains": False, "skippedCount": 4},
        {"entry": "b.org", "subdomains": False, "skippedCount": 0},
        {"entry": "example.org", "subdomains": True, "skippedCount": 17},
    ]


# Criterion 2
async def test_given_a_count_for_an_entry_not_on_the_list_when_get_then_it_does_not_appear(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")], details=SENDERS)
    await skip(owner, "gone@example.com", 9)

    response = await get(api)

    assert "gone@example.com" not in response.text
    assert [s["skippedCount"] for s in response.json()["categories"][0]["senders"]] == [0, 0]


# Criterion 3
async def test_given_a_put_body_with_skipped_count_when_put_then_422_and_nothing_is_written(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")], details=SENDERS)
    body = [entry("Invoices", senders=[{"entry": "a@example.com", "subdomains": False, "skippedCount": 3}])]

    response = await put(api, 1, body)

    assert response.status_code == 422
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


# Criterion 4
async def test_given_another_mailboxs_counts_when_get_then_they_never_appear(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")], details=SENDERS)
    await seed(owner, [("Elsewhere", "Not mine")], mailbox=OTHER_MAILBOX, details=SENDERS)
    await skip(owner, "a@example.com", 8, mailbox=OTHER_MAILBOX)

    response = await get(api)

    assert [s["skippedCount"] for s in response.json()["categories"][0]["senders"]] == [0, 0]


async def test_given_counts_when_put_then_the_response_carries_them_for_the_new_version(
    api: Api,
    owner: asyncpg.Connection,
) -> None:
    await seed(owner, [("Invoices", "Bills")], details=SENDERS)
    await skip(owner, "a@example.com", 2)
    body = [entry("Invoices", senders=[{"entry": "a@example.com", "subdomains": False}])]

    response = await put(api, 1, body)

    assert response.status_code == 200
    assert response.json()["categories"][0]["senders"] == [
        {"entry": "a@example.com", "subdomains": False, "skippedCount": 2}
    ]
