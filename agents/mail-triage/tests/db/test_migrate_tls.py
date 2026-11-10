"""U-quiet-hours-16b: the migrate job honours the TLS setting in the owner URL (ADR-0030, RT-2). No database needed."""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from app.db import migrate
from app.db.migrate import migrate_database


async def _connect(url: str) -> None:
    with contextlib.suppress(ConnectionRefusedError):
        await migrate_database(url, "unused-runtime-password")


def _spy(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    async def fake_connect(**kwargs: Any) -> object:
        seen.update(kwargs)
        raise ConnectionRefusedError  # the first thing the job does is connect; nothing more is needed

    monkeypatch.setattr(migrate.asyncpg, "connect", fake_connect)
    return seen


async def test_given_ssl_verify_full_in_the_owner_url_when_the_job_connects_then_asyncpg_gets_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _spy(monkeypatch)

    await _connect("postgresql+asyncpg://owner:pw@db.internal:5432/mail?ssl=verify-full")

    assert seen["ssl"] == "verify-full"
    assert (seen["host"], seen["port"], seen["user"], seen["database"]) == ("db.internal", 5432, "owner", "mail")


async def test_given_no_ssl_in_the_owner_url_when_the_job_connects_then_asyncpg_keeps_its_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _spy(monkeypatch)

    await _connect("postgresql+asyncpg://owner:pw@db.internal:5432/mail")

    assert "ssl" not in seen


@pytest.mark.parametrize("value", ["bogus", "true"])
async def test_given_an_unknown_ssl_value_when_the_job_connects_then_it_fails_without_the_url(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    seen = _spy(monkeypatch)

    with pytest.raises(ValueError, match="ssl") as error:
        await migrate_database(f"postgresql+asyncpg://owner:pw-secret@db:5432/mail?ssl={value}", "unused")

    assert "pw-secret" not in str(error.value)
    assert seen == {}
