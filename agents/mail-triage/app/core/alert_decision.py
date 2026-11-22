"""The decision of the alert: urgent, or in a ticked category, with every cause (ADR-0057, C-9).

Pure: it gets the urgency verdict and the names of the ticked categories the mail is filed under (topic and extra
label) and answers whether one alert exists and why. One mail is one alert, so every cause goes into the same decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = [
    "ALWAYS_NOTIFY_LABEL",
    "URGENT_LABEL",
    "AlertCause",
    "AlertDecision",
    "CauseKind",
    "decide_alert",
    "decode_causes",
    "encode_causes",
]

URGENT_LABEL = "Urgent: needs your attention"
ALWAYS_NOTIFY_LABEL = "Always notify"
_CATEGORY_PREFIX = "always_notify:"


class CauseKind(StrEnum):
    """Why an alert exists."""

    URGENT = "urgent"
    ALWAYS_NOTIFY = "always_notify"


@dataclass(frozen=True, slots=True)
class AlertCause:
    """One reason for the alert; ``category`` is the ticked category of an always-notify cause."""

    kind: CauseKind
    category: str | None = None

    def describe(self) -> str:
        """The fixed label of this cause, as the alert shows it."""
        if self.kind is CauseKind.URGENT:
            return URGENT_LABEL
        return f"{ALWAYS_NOTIFY_LABEL}: {self.category}"


@dataclass(frozen=True, slots=True)
class AlertDecision:
    """An alert exists, for these causes (never empty)."""

    causes: tuple[AlertCause, ...]

    @property
    def label(self) -> str:
        """The main label, which starts the alert: urgency first, else the first ticked category."""
        return self.causes[0].describe()


def decide_alert(*, urgent: bool, ticked: Iterable[str]) -> AlertDecision | None:
    """One decision with every cause, or ``None`` when the mail is neither urgent nor in a ticked category."""
    causes: list[AlertCause] = [AlertCause(CauseKind.URGENT)] if urgent else []
    for name in dict.fromkeys(ticked):  # each category once, in order
        causes.append(AlertCause(CauseKind.ALWAYS_NOTIFY, name))
    return AlertDecision(tuple(causes)) if causes else None


def encode_causes(causes: Sequence[AlertCause]) -> list[str]:
    """The stored form of the causes: ``urgent`` or ``always_notify:<category>``."""
    return [c.kind.value if c.category is None else f"{_CATEGORY_PREFIX}{c.category}" for c in causes]


def decode_causes(stored: object) -> tuple[AlertCause, ...]:
    """Read the stored causes; anything unreadable is dropped. Nothing stored: an alert from before causes existed."""
    if stored is None:
        return (AlertCause(CauseKind.URGENT),)
    if not isinstance(stored, list):
        return ()
    causes: list[AlertCause] = []
    for item in stored:
        if item == CauseKind.URGENT.value:
            causes.append(AlertCause(CauseKind.URGENT))
        elif isinstance(item, str) and item.startswith(_CATEGORY_PREFIX) and len(item) > len(_CATEGORY_PREFIX):
            causes.append(AlertCause(CauseKind.ALWAYS_NOTIFY, item[len(_CATEGORY_PREFIX) :]))
    return tuple(causes)
