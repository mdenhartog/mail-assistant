"""The one-time catch-up of the unread mail that was already in the inbox (INT-003, ADR-0021).

Only the state type lives here so far; the use case follows in the next units.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime  # noqa: TC003  # a dataclass field


@dataclass(frozen=True, slots=True)
class CatchUpState:
    """When the catch-up started (the cut-off) and, once it is done, when it finished."""

    started_at: datetime
    finished_at: datetime | None
