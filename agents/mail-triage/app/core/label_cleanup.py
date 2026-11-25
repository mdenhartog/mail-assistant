"""The delete rule of the delayed label cleanup (ADR-0060 point 5; threat model T1, T2, T13 to T16).

Pure logic: no clock, no Gmail, no database. For one label and one check it decides exactly one ``Action``. The caller
(unit 09) reads the facts from Gmail and the stores, applies the action, and makes the last emptiness check and the
delete call itself; this module is only the rule, and ``DELETE`` is the one result that may lead to a delete.

Rules, in this order:

1. A label is kept (``KEEP``) when it is not of type ``user`` (the exact string, so an unknown type is not deletable),
   is in the current list or a setting (a category, "Other", the archive label), is the target of a Gmail filter, has a
   child, left the list less than the protection period ago, or has no known time of leaving. Parents therefore go after
   children: a label with a child is never deleted, and its own timer starts the check after the child is gone.
   ``KEEP`` never touches a stored timer; the timer ends by the gap rule below.
2. A label with mail (messages or threads above 0) resets a running timer (``RESET_TIMER``) or is kept (``KEEP``).
3. An empty label without a timer starts one (``START_TIMER``) with the wait that applies now.
4. A running timer resets (``RESET_TIMER``) when the last check that saw the label empty is more than 3 cycles ago, or
   lies in the future (the clock went back). A restart of the agent therefore keeps a timer; a long absence does not.
5. Otherwise the label waits (``WAIT``) until the timer is as old as the wait it started with, then ``DELETE``.

The wait of a running timer is the one stored with it (``Timer.wait``): lowering or raising the setting changes only
timers that start afterwards (R3, T16). ``Decision.wait`` is the wait to store with a new timer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

__all__ = ["MAX_MISSED_CYCLES", "USER_TYPE", "Action", "Decision", "LabelFacts", "Rules", "Timer", "decide"]

USER_TYPE = "user"
MAX_MISSED_CYCLES = 3  # a gap of more than this many cycles between two checks resets the timer (R3)


class Action(StrEnum):
    """What the cleanup does with one label at one check."""

    KEEP = "keep"
    START_TIMER = "start_timer"
    RESET_TIMER = "reset_timer"
    WAIT = "wait"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class LabelFacts:
    """What is known about one label at this check; ``left_list_at`` is when it left the list, ``None`` when unknown."""

    label_type: str
    in_list: bool
    has_child: bool
    messages_total: int
    threads_total: int
    filter_target: bool
    left_list_at: datetime | None


@dataclass(frozen=True, slots=True)
class Timer:
    """A stored timer: when the label was first seen empty, when last, and the wait it started with."""

    empty_since: datetime
    last_seen_empty: datetime
    wait: timedelta


@dataclass(frozen=True, slots=True)
class Rules:
    """The settings of one run: the wait for new timers, the protection period and the interval between checks."""

    wait: timedelta
    protection: timedelta
    cycle: timedelta


@dataclass(frozen=True, slots=True)
class Decision:
    """The one action; ``wait`` is the length to store with the timer when the action is ``START_TIMER``."""

    action: Action
    wait: timedelta | None = None


_KEEP = Decision(Action.KEEP)


def _blocked(facts: LabelFacts, now: datetime, protection: timedelta) -> bool:
    """Whether anything but mail and time forbids a delete."""
    if facts.label_type != USER_TYPE or facts.in_list or facts.filter_target or facts.has_child:
        return True
    return facts.left_list_at is None or now - facts.left_list_at < protection


def decide(facts: LabelFacts, timer: Timer | None, *, now: datetime, rules: Rules) -> Decision:
    """Decide one action. ``rules.wait`` is used only for a new timer; a running timer keeps its own wait."""
    if _blocked(facts, now, rules.protection):
        return _KEEP
    if facts.messages_total > 0 or facts.threads_total > 0:
        return Decision(Action.RESET_TIMER) if timer is not None else _KEEP
    if timer is None:
        return Decision(Action.START_TIMER, rules.wait)
    gap = now - timer.last_seen_empty
    if gap < timedelta(0) or gap > MAX_MISSED_CYCLES * rules.cycle:
        return Decision(Action.RESET_TIMER)
    if now - timer.empty_since >= timer.wait:
        return Decision(Action.DELETE)
    return Decision(Action.WAIT)
