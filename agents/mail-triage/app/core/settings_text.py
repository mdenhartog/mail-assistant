"""The words of the settings dialogue (spec C-10, Behaviour 1 to 5): English, 24-hour time, the terms of the alert texts.

Every message is HTML for Telegram, so everything that is not written here is escaped. Nothing in this module logs.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from app.core.alert_text import AlertMessage, Button

if TYPE_CHECKING:
    from datetime import time

    from schedule_policy.policy import TimePolicy

QUIET = "quiet"
OVERVIEW = "overview"
REMIND = "remind"
ZONE = "zone"

VALUE_NAMES = {
    QUIET: "Quiet hours",
    OVERVIEW: "Daily overview",
    REMIND: "Remind-me-later default",
    ZONE: "Time zone",
}
CHANGE_LABELS = {key: f"Change {name[0].lower()}{name[1:]}" for key, name in VALUE_NAMES.items()}


def clock(value: time) -> str:
    """``07:05``: 24-hour time, whole minutes."""
    return f"{value.hour:02d}:{value.minute:02d}"


def card_text(policy: TimePolicy, note: str | None = None) -> str:
    """The four values, one per line, optionally under a one-line note such as 'Saved.'."""
    lines = [
        f"{VALUE_NAMES[QUIET]}: {clock(policy.quiet_start)} to {clock(policy.quiet_end)}",
        f"{VALUE_NAMES[OVERVIEW]}: {clock(policy.overview_at)}",
        f"{VALUE_NAMES[REMIND]}: {clock(policy.remind_at)}",
        f"{VALUE_NAMES[ZONE]}: {html.escape(policy.zone, quote=False)}",
    ]
    return "\n".join([html.escape(note, quote=False), "", *lines] if note else lines)


def card(policy: TimePolicy, change_data: dict[str, str], note: str | None = None) -> AlertMessage:
    """The settings card; ``change_data`` maps each value key to the callback data of its Change button."""
    buttons = tuple(Button(CHANGE_LABELS[key], change_data[key]) for key in VALUE_NAMES)
    return AlertMessage(card_text(policy, note), buttons)
