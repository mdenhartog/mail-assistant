# pyright: reportUnusedImport=false, reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# (schemathesis is only partly typed: its strategies and checks have no complete type arguments)
"""U-mail-categories-04, criterion 8: schemathesis cases built from the OpenAPI document, sent with a session and CSRF.

The cases are drawn from the document (the same one ``docs/api/openapi.json`` is exported from) and sent through the
test client, so the asyncpg pool stays on the test's event loop. No answer may be a 5xx and every answer must match the
schema.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import asyncpg
import pytest
import schemathesis
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from hypothesis import HealthCheck, given, settings
from schemathesis import Case
from schemathesis.specs.openapi.checks import positive_data_acceptance

from app.auth.cookies import COOKIE_NAME
from app.auth.csrf import csrf_token
from app.auth.digest import username_digest
from app.auth.session import SessionStore, attach_sessions
from app.db import Database
from app.ids import SecretsIdSource
from app.security_events import SecurityEvents
from app.startup import attach_database
from tests.db.conftest import (  # noqa: F401  # the shared fixtures of U-09, used here without editing them
    db,
    owner,
    pg_server,
    server,
    template_name,
    web_database,
)
from tests.fakes import FakeClock, make_app, make_settings, real_minute

T0 = real_minute()  # the list versions carry the database's clock, so the app's fake clock starts at the real time
ORIGIN = "https://settings.example.test"
OPERATIONS = ("GET", "PUT")
EXAMPLES = 40


@dataclass
class Session:
    http: AsyncClient
    app: FastAPI
    headers: dict[str, str]
    cookies: dict[str, str]


@pytest.fixture
async def session(web_database: Database) -> AsyncIterator[Session]:  # noqa: F811
    clock = FakeClock(T0)
    events = SecurityEvents(web_database, clock, b"e" * 32)
    store = SessionStore(web_database, SecretsIdSource(), events)
    app = make_app(make_settings(rate_limit_per_minute=100_000, categories_mailbox_id="primary"))
    app.state.clock = clock
    attach_database(app, web_database, clock)
    attach_sessions(app, store, events)
    value, created = await store.create(username_digest(b"k" * 32, "canary-user"), T0)
    headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf_token(b"b" * 32, created.id_hash)}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Session(http, app, headers, {COOKIE_NAME: value})


def _cases(app: FastAPI, method: str) -> list[Case[Any]]:
    schema = schemathesis.openapi.from_dict(app.openapi())
    drawn: list[Case[Any]] = []

    @settings(
        max_examples=EXAMPLES,
        derandomize=True,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large, HealthCheck.filter_too_much],
    )
    @given(case=schema["/api/categories"][method].as_strategy())
    def draw(case: Case[Any]) -> None:
        drawn.append(case)

    draw()
    return drawn


@pytest.mark.parametrize("method", OPERATIONS)
async def test_given_the_openapi_document_when_cases_are_sent_with_a_session_then_no_5xx_and_the_schema_matches(
    session: Session,
    owner: asyncpg.Connection,  # noqa: F811
    method: str,
) -> None:
    await owner.execute("insert into categories.mailbox (id) values ('primary')")
    async with owner.transaction():
        await owner.execute("insert into categories.list_version (mailbox_id, version) values ('primary', 1)")
    cases = _cases(session.app, method)
    assert cases
    seen: set[int] = set()

    for case in cases:
        sent = case.as_transport_kwargs(base_url="http://test")
        body = sent.get("json")
        if isinstance(body, dict):  # based on the stored version, so the rules and the write are reached, not only 409
            body["version"] = await owner.fetchval("select max(version) from categories.list_version")
        response = await session.http.request(
            method,
            "/api/categories",
            json=body,
            headers={**sent.get("headers", {}), **session.headers},
            cookies=session.cookies,
        )
        assert response.status_code < 500
        # A text that breaks a name rule is valid to the schema and answered with 422 problems by design (the rules
        # live in category_policy, not in the schema), so the "valid data must be accepted" check is left out.
        case.validate_response(
            schemathesis.Response.from_httpx(response, verify=True), excluded_checks=[positive_data_acceptance]
        )
        seen.add(response.status_code)
    assert seen >= ({200} if method == "GET" else {422})
