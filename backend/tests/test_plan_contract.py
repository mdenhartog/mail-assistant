# pyright: reportUnusedImport=false, reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# (schemathesis is only partly typed: its strategies and checks have no complete type arguments)
"""U-mail-categories-17, criterion 8: schemathesis cases built from the OpenAPI document for the plan routes.

The cases are sent through the test client with a session and CSRF. Where a case carries a plan id or an item count it
is pointed at the seeded plan now and then, so the writes reach the database functions and not only the 409. No answer
may be a 5xx and every answer must match the schema.
"""

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
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
from tests.test_plan_api import MAILBOX, ORIGIN, seed_plan, set_apply_config

T0 = real_minute()
EXAMPLES = 40
OPERATIONS = [
    ("GET", "/api/plan"),
    ("GET", "/api/plan/items"),
    ("POST", "/api/plan/decisions"),
    ("POST", "/api/plan/approve"),
    ("POST", "/api/plan/{plan_id}/move-back"),
]


class Session:
    def __init__(self, http: AsyncClient, app: FastAPI, headers: dict[str, str]) -> None:
        self.http = http
        self.app = app
        self.headers = headers


@pytest.fixture
async def session(web_database: Database) -> AsyncIterator[Session]:  # noqa: F811
    clock = FakeClock(T0)
    events = SecurityEvents(web_database, clock, b"e" * 32)
    store = SessionStore(web_database, SecretsIdSource(), events)
    app = make_app(make_settings(rate_limit_per_minute=100_000, categories_mailbox_id=MAILBOX))
    app.state.clock = clock
    attach_database(app, web_database, clock)
    attach_sessions(app, store, events)
    value, created = await store.create(username_digest(b"k" * 32, "canary-user"), T0)
    headers = {
        "Origin": ORIGIN,
        "X-CSRF-Token": csrf_token(b"b" * 32, created.id_hash),
        "Cookie": f"{COOKIE_NAME}={value}",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield Session(http, app, headers)


def _cases(app: FastAPI, method: str, path: str) -> list[Case[Any]]:
    schema = schemathesis.openapi.from_dict(app.openapi())
    drawn: list[Case[Any]] = []

    @settings(
        max_examples=EXAMPLES,
        derandomize=True,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large, HealthCheck.filter_too_much],
    )
    @given(case=schema[path][method].as_strategy())
    def draw(case: Case[Any]) -> None:
        drawn.append(case)

    draw()
    return drawn


@pytest.mark.parametrize(("method", "path"), OPERATIONS)
async def test_given_the_openapi_document_when_cases_are_sent_with_a_session_then_no_5xx_and_the_schema_matches(
    session: Session,
    owner: asyncpg.Connection,  # noqa: F811
    method: str,
    path: str,
) -> None:
    await set_apply_config(owner, threshold=2)
    ready = await seed_plan(owner, state="ready", tag="r")
    applied = await seed_plan(
        owner, state="applied", moves=(), terminal_at=datetime.fromisoformat("2026-11-01T00:00:00+00:00"), tag="a"
    )
    cases = _cases(session.app, method, path)
    assert cases
    seen: set[int] = set()

    for number, case in enumerate(cases):
        sent = case.as_transport_kwargs(base_url="http://test")
        body = sent.get("json")
        url = str(sent["url"])
        if number % 3 == 0 and isinstance(body, dict) and "planId" in body:  # reach the functions, not only the 409
            body["planId"] = str(ready.plan_id)
            body["itemCount"] = len(ready.item_ids)
        if number % 3 == 0 and "/move-back" in url:
            url = f"http://test/api/plan/{applied.plan_id}/move-back"
        elif "/move-back" in url and "plan_id" in url:
            url = url.replace("{plan_id}", str(uuid.uuid4()))
        response = await session.http.request(
            method,
            url,
            params=sent.get("params"),
            json=body,
            headers={**sent.get("headers", {}), **session.headers},
        )
        assert response.status_code < 500
        case.validate_response(
            schemathesis.Response.from_httpx(response, verify=True), excluded_checks=[positive_data_acceptance]
        )
        seen.add(response.status_code)
    assert 200 in seen or method == "POST"
    assert seen <= {200, 401, 403, 409, 415, 422, 429}
