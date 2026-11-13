"""The words of the settings dialogue (spec C-10, Behaviour 1 to 5): English, 24-hour time, the alert-text terms.

Every message is HTML for Telegram, so everything that is not written here is escaped. Nothing in this module logs.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import UTC
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.core.alert_text import AlertMessage, Button

if TYPE_CHECKING:
    from datetime import date, datetime, time

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


INVALID_SAVED = (
    "The saved settings are not valid, so I am using the values below. "
    "Change any one of them and I will save all four as a new set."
)
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


# ---- the confirmation and Undo (spec C-7; AC-20, AC-21) -------------------------------------------------------------

SAVED = "Saved."
UNDONE = "Undone. The previous values are back."
UNDO_CHANGED = "The settings changed since then, so I did not undo anything. Nothing was changed."
NOTHING_TO_UNDO = "There is nothing to undo: that was the first saved change. Nothing was changed."
UNDO_REFUSED = "I could not put the previous values back because they are no longer allowed. Nothing was changed."
UNDO_AGAIN = "Tap Undo to put the previous values back, or open the settings."
UNDO_LABEL = "Undo"
SHOW_SETTINGS = "Show settings"


@dataclass(frozen=True, slots=True)
class Elsewhere:
    """The zone Marco left, for the comparison after a zone change: the time there now and the quiet hours there."""

    city: str
    now: time
    quiet_start: time
    quiet_end: time


@dataclass(frozen=True, slots=True)
class ClockChange:
    """A clock change in the new zone: its local day and wall time (before the change) and the offsets around it."""

    day: date
    at: time
    before_minutes: int
    after_minutes: int


@dataclass(frozen=True, slots=True)
class Picture:
    """Everything the confirmation says; ``left`` is set only when the time zone changed."""

    headline: str
    policy: TimePolicy
    offset_minutes: int
    here: time
    overview_day: str
    overview_clock: time
    left: Elsewhere | None
    clock_change: ClockChange | None


def offset_label(minutes: int) -> str:
    """``UTC-5``, ``UTC+1``, ``UTC+5:30``, ``UTC+5:45``, ``UTC+0``."""
    hours, rest = divmod(abs(minutes), 60)
    return f"UTC{'-' if minutes < 0 else '+'}{hours}" + (f":{rest:02d}" if rest else "")


def city_of(zone: str) -> str:
    """``America/New_York`` -> ``New York``: the last part of the zone name, for speaking."""
    return zone.rsplit("/", maxsplit=1)[-1].replace("_", " ")


def _picture_lines(picture: Picture) -> list[str]:
    policy, left = picture.policy, picture.left
    lines = [picture.headline, f"{VALUE_NAMES[ZONE]}: {policy.zone} ({offset_label(picture.offset_minutes)})"]
    quiet = f"{VALUE_NAMES[QUIET]}: {clock(policy.quiet_start)} to {clock(policy.quiet_end)}"
    if left is not None:
        here = city_of(policy.zone)
        lines.append(f"It is now {clock(picture.here)} there, {clock(left.now)} in {left.city}.")
        quiet += f" {here} time ({clock(left.quiet_start)} to {clock(left.quiet_end)} {left.city} time)"
    lines += [
        quiet,
        f"{VALUE_NAMES[OVERVIEW]}: {clock(policy.overview_at)}",
        f"{VALUE_NAMES[REMIND]}: {clock(policy.remind_at)}",
        f"Next overview: {picture.overview_day} {clock(picture.overview_clock)}",
    ]
    if (change := picture.clock_change) is not None:
        span = f"{offset_label(change.before_minutes)} to {offset_label(change.after_minutes)}"
        lines.append(f"Next clock change: {change.day.isoformat()} at {clock(change.at)} ({span})")
    return lines


def confirmation(picture: Picture, undo_data: str, start_data: str) -> AlertMessage:
    """The full picture after a change, with Undo and a button that shows the settings again."""
    buttons = (Button(UNDO_LABEL, undo_data), Button(SHOW_SETTINGS, start_data))
    return AlertMessage(html.escape("\n".join(_picture_lines(picture)), quote=False), buttons)


def undo_offer(undo_data: str, start_data: str) -> AlertMessage:
    """The Undo button again, under a fresh nonce, when the confirmation was answered with something else."""
    buttons = (Button(UNDO_LABEL, undo_data), Button(SHOW_SETTINGS, start_data))
    return AlertMessage(html.escape(UNDO_AGAIN, quote=False), buttons)


# ---- the notice for a change made on the web (spec C-8; AC-13; ADR-0033) ---------------------------------------------

WEB_UNDO = "webundo"
WEB_LOCK = "weblock"
WEB_UNDO_LABEL = UNDO_LABEL
WEB_LOCK_LABEL = "Undo and lock web sign-in"
_WEB_TOKEN = re.compile(r"[A-Za-z0-9_-]{22,40}")  # the 16-byte URL-safe token; 7 + 1 + 40 stays under 64 bytes


def web_button_data(action: str, token: str) -> str:
    """Callback data ``webundo:<token>`` or ``weblock:<token>``; the token must be URL-safe ASCII and fit the limit."""
    if action not in {WEB_UNDO, WEB_LOCK} or not _WEB_TOKEN.fullmatch(token) or not token.isascii():
        raise ValueError("web notice token is malformed")
    return f"{action}:{token}"


def split_web_button(data: str) -> tuple[str, str] | None:
    """``(action, token)`` of ``webundo:<token>`` or ``weblock:<token>``; ``None`` for anything else."""
    action, _, token = data.partition(":")
    if action not in {WEB_UNDO, WEB_LOCK} or not _WEB_TOKEN.fullmatch(token) or not data.isascii():
        return None
    return action, token


def _changed(name: str, new: str, old: str | None) -> str:
    """One value line: the new value, then what it was (or that it did not change)."""
    return f"{name}: {new} ({'unchanged' if old is None else f'was {old}'})"


def _value_lines(old: TimePolicy | None, new: TimePolicy) -> list[str]:
    rows = [
        (VALUE_NAMES[QUIET], f"{clock(new.quiet_start)} to {clock(new.quiet_end)}"),
        (VALUE_NAMES[OVERVIEW], clock(new.overview_at)),
        (VALUE_NAMES[REMIND], clock(new.remind_at)),
        (VALUE_NAMES[ZONE], new.zone),
    ]
    if old is None:
        return [f"{name}: {value}" for name, value in rows]
    before = [
        f"{clock(old.quiet_start)} to {clock(old.quiet_end)}",
        clock(old.overview_at),
        clock(old.remind_at),
        old.zone,
    ]
    return [
        _changed(name, value, None if value == was else was) for (name, value), was in zip(rows, before, strict=True)
    ]


def web_notice(version: int, at: datetime, old: TimePolicy | None, new: TimePolicy, token: str) -> AlertMessage:
    """The notice for the web change that made ``version``: old and new values, number, channel, time, two buttons.

    The time is the moment of the change in the new time zone. There is no username in it: nobody is named.
    """
    local = at.astimezone(ZoneInfo(new.zone))
    lines = [
        f"Your settings were changed on the web (change {version}).",
        f"Channel: web. Time: {local:%Y-%m-%d %H:%M} ({new.zone})",
        *(["These are the first saved values."] if old is None else []),
        *_value_lines(old, new),
    ]
    buttons = (
        Button(WEB_UNDO_LABEL, web_button_data(WEB_UNDO, token)),
        Button(WEB_LOCK_LABEL, web_button_data(WEB_LOCK, token)),
    )
    return AlertMessage(html.escape("\n".join(lines), quote=False), buttons)


# ---- what the buttons of the web notice answer, and /web_unlock (spec C-8; AC-13, AC-27) -----------------------------

WEB_UNLOCK_COMMAND = "/web_unlock"
WEB_LOCK_COMMAND = "/web_lock"  # the command the sign-in mail names (backend LOCK_COMMAND)
WEB_UNDONE = "Undone. The values from before the web changes are back."
WEB_EXPIRED = "Expired"
WEB_DONE = "Already done"
WEB_UNLOCKED = "Web sign-in is unlocked."
WEB_NOT_LOCKED = "Web sign-in was not locked. Nothing was changed."
_WEB_LOCK_NOTE = f"Web sign-in is locked. Send {WEB_UNLOCK_COMMAND} to allow it again."
WEB_LOCKED_NOW = _WEB_LOCK_NOTE
WEB_ALREADY_LOCKED = f"Web sign-in was already locked. Send {WEB_UNLOCK_COMMAND} to allow it again."


def web_locked(outcome: str) -> str:
    """The answer to "Undo and lock web sign-in": what happened to the values, then that sign-in is locked."""
    return f"{outcome} {_WEB_LOCK_NOTE}"


# ---- the notice for wrong sign-in codes (spec AC-20; W-13, W-15): a count and a time, never who or what was typed ----


def code_alert(count: int, at: datetime) -> str:
    """The notice after wrong or expired codes in ten minutes: the number, the time in UTC, nothing else."""
    return (
        f"{count} wrong or expired web sign-in codes in the last 10 minutes. "
        f"Time: {at.astimezone(UTC):%Y-%m-%d %H:%M} UTC."
    )


def code_lock_alert(count: int, at: datetime) -> str:
    """The notice after the agent locked web sign-in for repeated wrong codes: number, time, how to unlock."""
    return (
        f"{count} wrong or expired web sign-in codes in 24 hours. Web sign-in is locked. "
        f"Time: {at.astimezone(UTC):%Y-%m-%d %H:%M} UTC. Send {WEB_UNLOCK_COMMAND} to allow it again."
    )
