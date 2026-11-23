# pyright: reportUnusedImport=false
# ruff: noqa: F811  # the shared fixtures are imported and used as parameters, like the other database tests
"""U-label-structure-13: export and template of the category list against a real PostgreSQL."""

from typing import Any

import asyncpg
import pytest
from httpx import Response

from category_policy.yaml_file import FileProblems, parse_category_file
from tests.db.conftest import (  # noqa: F401  # the shared fixtures of U-09
    db,
    owner,
    pg_server,
    server,
    template_name,
    web_database,
)
from tests.test_categories_api import (  # noqa: F401  # the app fixture and the seed helpers of the list tests
    MAILBOX,
    Api,
    api,
    seed,
)
from tests.test_category_upload_api import VERSIONS, Client, sign_in

EXPORT = "/api/categories/export"
TEMPLATE = "/api/categories/template"
OTHER_MAILBOX = "other-mailbox@example.test"
DETAILS: dict[int, dict[str, Any]] = {
    0: {
        "kind": "topic",
        "notify": True,
        "senders": [("billing.example.nl", True, True), ("a@shop.example.nl", False, False)],
    },
    1: {"kind": "extra", "senders": []},
}


async def get(client: Client, path: str) -> Response:
    return await client.api.http.get(path, headers={"Cookie": client.headers["Cookie"]})


# Criterion 1
async def test_given_the_current_list_when_exported_and_uploaded_unchanged_then_no_change_and_no_new_version(
    api: Api, owner: asyncpg.Connection
) -> None:
    await seed(
        owner,
        [("Invoices", "Bills and receipts"), ("Travel/Trips", "Trips: é")],
        details=DETAILS,
        instructions="Be brief",
    )
    client = await sign_in(api)

    exported = await get(client, EXPORT)
    assert exported.status_code == 200
    preview = await client.upload(exported.text)

    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert (body["added"], body["changed"], body["removed"], body["instructionsChanged"]) == (0, 0, 0, False)
    confirmed = await client.confirm(body)
    assert confirmed.status_code == 200
    assert confirmed.json()["version"] == 1
    assert await owner.fetchval(VERSIONS, MAILBOX) == 1


# Criterion 2
@pytest.mark.parametrize(
    ("path", "name"), [(EXPORT, "mail-categories.yaml"), (TEMPLATE, "mail-categories.template.yaml")]
)
async def test_given_a_file_response_then_it_is_an_attachment_with_nosniff_and_no_store(
    api: Api, owner: asyncpg.Connection, path: str, name: str
) -> None:
    await seed(owner, [("Invoices", "Bills")])
    client = await sign_in(api)

    response = await get(client, path)

    assert response.status_code == 200
    headers = response.headers
    assert headers["content-disposition"] == f'attachment; filename="{name}"'
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["cache-control"] == "no-store"
    assert headers["content-type"].split(";")[0] == "application/yaml"


# Criterion 3
@pytest.mark.parametrize("path", [EXPORT, TEMPLATE, f"{TEMPLATE}?file=example"])
async def test_given_no_session_when_fetched_then_401(api: Api, owner: asyncpg.Connection, path: str) -> None:
    await seed(owner, [("Invoices", "Bills")])

    response = await api.http.get(path)

    assert response.status_code == 401


async def test_given_no_list_yet_when_exported_then_409(api: Api) -> None:
    client = await sign_in(api)

    assert (await get(client, EXPORT)).status_code == 409


async def test_given_an_unknown_template_file_when_fetched_then_422(api: Api) -> None:
    client = await sign_in(api)

    assert (await get(client, f"{TEMPLATE}?file=other")).status_code == 422


# Criterion 4
@pytest.mark.parametrize("query", ["", "?file=template", "?file=example"])
async def test_given_the_template_and_the_example_when_fetched_then_they_parse(api: Api, query: str) -> None:
    client = await sign_in(api)

    response = await get(client, f"{TEMPLATE}{query}")

    assert response.status_code == 200
    parsed = parse_category_file(response.content)
    assert not isinstance(parsed, FileProblems)
    assert parsed.categories


async def test_given_the_example_when_fetched_then_the_name_is_the_example_file(api: Api) -> None:
    client = await sign_in(api)

    response = await get(client, f"{TEMPLATE}?file=example")

    assert 'filename="mail-categories.example.yaml"' in response.headers["content-disposition"]


# Criterion 5
async def test_given_an_export_then_it_has_only_the_upload_fields_and_no_id_or_other_mailbox(
    api: Api, owner: asyncpg.Connection
) -> None:
    ids = await seed(owner, [("Invoices", "Bills")], details=DETAILS, instructions="Be brief")
    await seed(owner, [("Secret", "Other mailbox canary")], mailbox=OTHER_MAILBOX)
    client = await sign_in(api)

    text = (await get(client, EXPORT)).text

    assert "Secret" not in text
    assert OTHER_MAILBOX not in text
    assert ids[0] not in text
    assert "mailCount" not in text
    assert "version" not in text.lower().replace("schema", "")
    parsed = parse_category_file(text.encode())
    assert not isinstance(parsed, FileProblems)
    assert [c.name for c in parsed.categories] == ["Invoices"]
    assert parsed.categories[0].notify is True


# U-label-structure-19, criterion 3
async def test_given_a_custom_archive_label_when_exported_and_uploaded_then_it_is_in_the_file_and_unchanged(
    api: Api, owner: asyncpg.Connection
) -> None:
    await seed(owner, [("Invoices", "Bills")], archive_label="Bewaard")
    client = await sign_in(api)

    exported = await get(client, EXPORT)
    preview = await client.upload(exported.text)

    assert "archiveLabel: Bewaard" in exported.text
    assert preview.json()["archiveLabelChanged"] is False
