import logging
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app

# Values that must never appear in a log record (plan: "Test rules and levels").
CANARIES = ("canary-user", "424242", "Pacific/Kiritimati", "canary-smtp-secret")


def find_canaries(records: list[logging.LogRecord]) -> list[str]:
    """Return one finding per canary per record, naming the canary and the logger."""
    formatter = logging.Formatter()
    findings: list[str] = []
    for record in records:
        text = formatter.format(record)
        findings.extend(
            f"canary {canary!r} in a record of logger {record.name!r}" for canary in CANARIES if canary in text
        )
    return findings


class _Collector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture(autouse=True)
def canary_log_records() -> Iterator[list[logging.LogRecord]]:
    """Collect every log record of the test and fail it when a canary was logged."""
    root = logging.getLogger()
    collector = _Collector()
    previous_level = root.level
    root.addHandler(collector)
    root.setLevel(logging.DEBUG)
    try:
        yield collector.records
    finally:
        root.removeHandler(collector)
        root.setLevel(previous_level)
    findings = find_canaries(collector.records)
    if findings:
        pytest.fail("; ".join(findings), pytrace=False)


@pytest.fixture
def app() -> FastAPI:
    return create_app(Settings(environment="test"))


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
