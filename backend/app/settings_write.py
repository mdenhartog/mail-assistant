"""Glue of the write route: the request values to a ``TimePolicy`` and the policy problems to API problems."""

from app.settings_models import ProblemItem, SettingsValues
from schedule_policy.policy import Problem, TimePolicy


def to_policy(values: SettingsValues) -> TimePolicy:
    """Convert the ``HH:MM`` strings of a request into the policy the shared validation takes."""
    raise NotImplementedError


def field_problems(values: SettingsValues, problems: list[Problem]) -> list[ProblemItem]:
    """Name the field of every problem; a rule that belongs to a window names both of its fields."""
    raise NotImplementedError
