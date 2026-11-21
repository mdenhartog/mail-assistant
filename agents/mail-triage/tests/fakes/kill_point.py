"""A kill point: stops the agent at a named place, for example between filing and the Telegram send.

Arm it, run the code until ``reach`` raises ``AgentKilledError``, then inspect the state that was written and run the
restart against it. ``disarm`` before the restart so the second run passes the same place.
"""

from __future__ import annotations


class AgentKilledError(Exception):
    """The agent was killed at a kill point (a simulated crash, not an application error)."""


class KillPoint:
    """Raises ``AgentKilledError`` when the armed point is reached."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.armed = False
        self.triggered = False
        self.reached: list[str] = []

    def arm(self) -> None:
        """The next time the point is reached the agent dies."""
        self.armed = True

    def disarm(self) -> None:
        """Let the agent pass the point (used for the restart)."""
        self.armed = False

    def reach(self, point: str) -> None:
        """Called by the code under test at ``point``; dies when this is the armed point.

        Raises:
            AgentKilledError: the point matches and the kill point is armed.
        """
        self.reached.append(point)
        if self.armed and point == self.name:
            self.triggered = True
            raise AgentKilledError(point)
