"""A recording of the steps a request takes (U-web-settings-62, AC-30): the SQL it runs and the mail it sends, in order.

Two usernames must take the same steps before the answer; comparing recorded steps replaces comparing wall-clock
times, which only a noisy machine can tell apart. A step is the text of a statement without its parameter values (the
ids and times differ by nature) or a mail call.
"""

from datetime import datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeMailer


class StepRecorder:
    """Collects the steps of the database session and of a mailer while attached."""

    def __init__(self) -> None:
        """Start with no steps."""
        self.steps: list[str] = []

    def attach(self, monkeypatch: pytest.MonkeyPatch, mailer: FakeMailer) -> None:
        """Record every statement a session executes and every ``send_code`` of the mailer until the test ends."""
        original_execute: Any = AsyncSession.execute
        original_send = mailer.send_code

        async def execute(session: AsyncSession, statement: Any, *args: Any, **kwargs: Any) -> Any:
            self.steps.append("sql: " + " ".join(str(statement).split()))
            return await original_execute(session, statement, *args, **kwargs)

        async def send_code(address: str, code: str, expires_at: datetime) -> None:
            self.steps.append("mail: send_code")
            await original_send(address, code, expires_at)

        monkeypatch.setattr(AsyncSession, "execute", execute)
        monkeypatch.setattr(mailer, "send_code", send_code)

    def take(self) -> list[str]:
        """Return the steps recorded since the last call and start again."""
        taken, self.steps = self.steps, []
        return taken


def first_difference(first: list[str], second: list[str]) -> str | None:
    """Return a description of the first step at which two recordings differ, or None when they are equal."""
    for index in range(max(len(first), len(second))):
        left = repr(first[index]) if index < len(first) else "nothing"
        right = repr(second[index]) if index < len(second) else "nothing"
        if left != right:
            return f"step {index + 1}: {left} against {right}"
    return None
