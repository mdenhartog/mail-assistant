"""Stub."""

import pytest

from tests.fakes import FakeMailer


class StepRecorder:
    def __init__(self) -> None:
        self.steps: list[str] = []

    def attach(self, monkeypatch: pytest.MonkeyPatch, mailer: FakeMailer) -> None:
        raise NotImplementedError

    def take(self) -> list[str]:
        raise NotImplementedError


def first_difference(first: list[str], second: list[str]) -> str | None:
    raise NotImplementedError
