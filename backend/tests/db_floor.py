"""Stub."""

from pathlib import Path

MINIMUM_DB_TESTS = 60


def count_ran(report: Path) -> int:
    raise NotImplementedError


def check(report: Path) -> str | None:
    raise NotImplementedError
