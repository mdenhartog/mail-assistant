"""Glue of the write route: the request values to a ``TimePolicy`` and the policy problems to API problems."""

from datetime import time

from app.settings_fields import FIELD_OF_RULE, TIME_FIELDS
from app.settings_models import ProblemItem, SettingsValues
from schedule_policy.policy import Problem, TimePolicy


def _clock(text: str) -> time:
    # The model's pattern guarantees ``HH:MM`` before this runs.
    return time(int(text[:2]), int(text[3:]))


def to_policy(values: SettingsValues) -> TimePolicy:
    """Convert the ``HH:MM`` strings of a request into the policy the shared validation takes.

    Args:
        values: The request values; their times match ``HH:MM``.

    Returns:
        The policy with naive, whole-minute times.
    """
    return TimePolicy(
        zone=values.time_zone,
        quiet_start=_clock(values.quiet_start),
        quiet_end=_clock(values.quiet_end),
        overview_at=_clock(values.overview_at),
        remind_at=_clock(values.remind_at),
    )


def _time_field(values: SettingsValues, shown: str) -> str:
    sent = dict(
        zip(TIME_FIELDS, (values.quiet_start, values.quiet_end, values.overview_at, values.remind_at), strict=True)
    )
    return next((field for field, text in sent.items() if text == shown), TIME_FIELDS[0])


def field_problems(values: SettingsValues, problems: list[Problem]) -> list[ProblemItem]:
    """Name the field of every problem; a rule that belongs to a window names both of its fields.

    Args:
        values: The request values, to find which time field a malformed-time rule is about.
        problems: What ``schedule_policy.validate`` reported.

    Returns:
        One item per problem and field, with the rule, the value given and the example of the shared validation.
    """
    items: list[ProblemItem] = []
    for problem in problems:
        fields = FIELD_OF_RULE[problem.rule]
        if fields == TIME_FIELDS:
            fields = (_time_field(values, problem.value),)
        items.extend(
            ProblemItem(field=field, rule=problem.rule, value=problem.value, example=problem.example)
            for field in fields
        )
    return items
