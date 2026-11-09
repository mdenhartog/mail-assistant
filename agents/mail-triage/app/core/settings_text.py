"""The words of the settings dialogue (spec C-10, Behaviour 1 to 5): English, 24-hour time, the alert-text terms.

Every message is HTML for Telegram, so everything that is not written here is escaped. Nothing in this module logs.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from app.core.alert_text import AlertMessage, Button

if TYPE_CHECKING:
    from datetime import time

    from schedule_policy.policy import Problem, TimePolicy

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


TIME_EXAMPLES = {OVERVIEW: "18:00", REMIND: "09:00"}


def with_cancel(text: str, cancel_data: str) -> AlertMessage:
    """A question: its text and one Cancel button (every question has one)."""
    return AlertMessage(html.escape(text, quote=False), (Button("Cancel", cancel_data),))


def time_question(key: str) -> str:
    """'Daily overview: type a time, for example 18:00.': names the value; it has one step."""
    return f"{VALUE_NAMES[key]}: type a time, for example {TIME_EXAMPLES[key]}."


def did_you_mean(suggestion: str) -> str:
    """A near miss: the listed name that is closest to what was typed, offered as a button."""
    return f"Did you mean {suggestion}?\nTap it, or type another place."


def with_choices(text: str, choices: list[tuple[str, str]], cancel_data: str) -> AlertMessage:
    """A question with one button per ``(label, callback data)`` choice, then Cancel."""
    buttons = (*(Button(label, data) for label, data in choices), Button("Cancel", cancel_data))
    return AlertMessage(html.escape(text, quote=False), buttons)


def quiet_start_question() -> str:
    """Step 1 of the quiet hours."""
    return f"{VALUE_NAMES[QUIET]}, step 1 of 2: start time\nType a time, for example 23:00."


def quiet_end_question(start: time) -> str:
    """Step 2 of the quiet hours; shows the start that was taken."""
    return f"{VALUE_NAMES[QUIET]}, step 2 of 2: end time\nStart: {clock(start)}. Type a time, for example 07:00."


SHOWN_ANSWER_CHARS = 20
SAVE_FAILED = "I could not save that. Nothing was changed. Try again in a moment."
START_AGAIN = "start:settings"


def with_start_button(text: str) -> AlertMessage:
    """A note with a 'Show settings' button that starts the dialogue again (callback ``start:settings``)."""
    return AlertMessage(html.escape(text, quote=False), (Button("Show settings", START_AGAIN),))


def unreadable(answer: str, example: str) -> str:
    """The answer is not a time: say what was read, what a time looks like and a working example."""
    shown = "".join(char for char in answer[:SHOWN_ANSWER_CHARS] if char.isprintable())
    if len(answer) > SHOWN_ANSWER_CHARS:
        shown += "..."
    return f'I could not read "{shown}" as a time (hours and minutes, such as {example} or 7pm). Try {example}.'


def duration(minutes: int) -> str:
    """'13 hours', '1 hour', '30 minutes', '12 hours 1 minute'."""
    hours, rest = divmod(minutes, 60)
    parts = [f"{hours} hour{'s' if hours != 1 else ''}"] if hours else []
    if rest or not hours:
        parts.append(f"{rest} minute{'s' if rest != 1 else ''}")
    return " ".join(parts)


def refusal(problem: Problem, window_minutes: int) -> str:
    """One broken rule in plain words: the rule, the value given and the working example from the policy check."""
    shown, example = problem.value, problem.example
    if problem.rule == "quiet_window_length":
        return f"Quiet hours can be 1 to 12 hours. {shown} is {duration(window_minutes)}. {example}."
    if problem.rule == "quiet_window_empty":
        return f"Quiet hours must start and end at different times. {shown} is empty. {example}."
    if problem.rule in {"overview_in_quiet_hours", "remind_in_quiet_hours"}:
        name = VALUE_NAMES[OVERVIEW if problem.rule.startswith("overview") else REMIND].lower()
        return f"The {name} at {shown} would fall inside quiet hours. {example}."
    return f"That is not allowed ({problem.rule}). {example}."


CHANGED_ELSEWHERE = "Your settings changed elsewhere. Nothing was saved. These are the current values."
ZONE_QUESTION = f"{VALUE_NAMES[ZONE]}: type a city or a country, for example Paris or Japan."
ZONE_NOT_FOUND = "I could not find a time zone for that. Try the nearest big city or the country."
ZONE_NOT_A_PLACE = "That does not look like a city or a country (letters only, at most 64 characters)."
ZONE_CHOOSE = "Which one do you mean? Tap a button, or type another place."
ZONE_TAP_ONE = "Tap one of the buttons below, or type another place."
TAP_A_BUTTON = "Tap one of the Change buttons below."
_MOVABLE = {
    "overview_in_quiet_hours": "the daily overview",
    "remind_in_quiet_hours": "the remind-me-later default",
}


def is_movable(problem: Problem) -> bool:
    """True when the rule is 'this value is inside quiet hours': the one a one-tap move can fix."""
    return problem.rule in _MOVABLE


def move_label(end: time) -> str:
    """The label of the one-tap move."""
    return f"Move to {clock(end)} and save"


def move_offer(policy: TimePolicy, problems: list[Problem], move_data: str, cancel_data: str) -> AlertMessage:
    """Say which values the new quiet hours would trap and offer to move them to the quiet end, in one save."""
    trapped = [f"{_MOVABLE[p.rule]} at {p.value}" for p in problems]
    names = [_MOVABLE[p.rule] for p in problems]
    window = f"{clock(policy.quiet_start)} to {clock(policy.quiet_end)}"
    both = "both" if len(names) == 1 else "all three"
    lines = [
        f"Quiet hours {window} are not saved yet: {' and '.join(trapped)} would fall inside them.",
        f"Move {' and '.join(names)} to {clock(policy.quiet_end)} and save {both}?",
    ]
    buttons = (Button(move_label(policy.quiet_end), move_data), Button("Cancel", cancel_data))
    return AlertMessage(html.escape("\n".join(lines), quote=False), buttons)


def card(policy: TimePolicy, change_data: dict[str, str], note: str | None = None) -> AlertMessage:
    """The settings card; ``change_data`` maps each value key to the callback data of its Change button."""
    buttons = tuple(Button(CHANGE_LABELS[key], change_data[key]) for key in VALUE_NAMES)
    return AlertMessage(card_text(policy, note), buttons)
