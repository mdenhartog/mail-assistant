"""U-web-settings-14: logging hygiene (AC-15, AC-20, W-13, W-15)."""

import json
import logging
import re
from pathlib import Path

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient, Response

from app.core.security import public
from app.logging_setup import PINNED_LOGGERS
from tests.fakes import make_app

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"
ACCESS_LOGGER = "app.access"


class CanaryBodyError(Exception):
    """Raised on a request with a canary body; only its class may be logged."""


def _app() -> FastAPI:
    app = make_app()

    @app.get("/t/items/{item_id}", dependencies=[Depends(public)])
    async def item(item_id: str) -> dict[str, str]:
        return {"id": item_id}

    @app.post("/t/boom", dependencies=[Depends(public)])
    async def boom() -> None:
        raise CanaryBodyError

    return app


def _texts(records: list[logging.LogRecord]) -> list[str]:
    return [logging.Formatter().format(record) for record in records]


async def _get(url: str, headers: dict[str, str] | None = None) -> Response:
    transport = ASGITransport(app=_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        return await http.get(url, headers=headers)


async def test_given_a_query_string_when_served_then_no_log_line_has_it(
    canary_log_records: list[logging.LogRecord],
) -> None:
    await _get("/t/items/7?code=424242&q=Pacific/Kiritimati")

    for text in _texts(canary_log_records):
        assert "424242" not in text
        assert "Kiritimati" not in text
        assert "code=" not in text
        assert not re.search(r"\?\w", text)
        assert not re.search(r"\bq=", text)


async def test_given_a_cookie_canary_when_served_then_no_log_line_has_it(
    canary_log_records: list[logging.LogRecord],
) -> None:
    await _get("/t/items/7", {"Cookie": "__Host-session=canary-user"})

    assert not [text for text in _texts(canary_log_records) if "canary-user" in text]


def test_given_the_image_command_when_read_then_the_access_log_is_disabled() -> None:
    cmd = [line for line in DOCKERFILE.read_text(encoding="utf-8").splitlines() if line.startswith("CMD ")][-1]

    argv = json.loads(cmd[4:])
    assert "--no-access-log" in argv
    assert "--access-log" not in argv


def test_given_the_app_is_created_when_the_loggers_are_read_then_they_are_at_warning() -> None:
    for name in PINNED_LOGGERS:
        logging.getLogger(name).setLevel(logging.NOTSET)

    _app()

    assert set(PINNED_LOGGERS) == {"httpx", "httpcore", "aiosmtplib"}
    for name in PINNED_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING


async def test_given_an_unhandled_error_when_logged_then_the_line_has_class_and_request_id_only(
    canary_log_records: list[logging.LogRecord],
) -> None:
    transport = ASGITransport(app=_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.post("/t/boom", content=b"canary-user 424242")

    request_id = response.headers["x-request-id"]
    errors = [r for r in canary_log_records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    text = _texts(errors)[0]
    assert "CanaryBodyError" in text
    assert request_id in text
    assert "canary-user" not in text
    assert "Traceback" not in text
    assert errors[0].exc_info is None


async def test_given_one_request_when_served_then_one_request_line_has_id_and_path_template(
    canary_log_records: list[logging.LogRecord],
) -> None:
    response = await _get("/t/items/12345")

    lines = [r for r in canary_log_records if r.name == ACCESS_LOGGER]
    assert len(lines) == 1
    text = _texts(lines)[0]
    assert "GET" in text
    assert "/t/items/{item_id}" in text
    assert "12345" not in text
    assert "200" in text
    assert response.headers["x-request-id"] in text


async def test_given_an_unknown_path_when_served_then_the_line_has_no_raw_path(
    canary_log_records: list[logging.LogRecord],
) -> None:
    await _get("/nope/12345?q=1")

    lines = [r for r in canary_log_records if r.name == ACCESS_LOGGER]
    assert len(lines) == 1
    text = _texts(lines)[0]
    assert "12345" not in text
    assert "404" in text
