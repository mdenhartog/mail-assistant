"""The only shape the model may answer in, and the policy that turns it into a category (spec AC-13, AC-18).

Mail text is untrusted. The model has no tools; whatever it returns must match ``Judgement`` exactly or the mail is
treated as needing attention, never as ignorable. Category names become Gmail labels, so they are held to a strict
pattern and a maximum number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import get_close_matches
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

if TYPE_CHECKING:
    from collections.abc import Collection

LABEL_PREFIX = "Assistant/"
OTHER_LABEL = f"{LABEL_PREFIX}Other"
MAX_CATEGORIES = 15  # spec C2
LOW_CONFIDENCE = 0.6
REASON_MAX_CHARS = 200
SUMMARY_MAX_CHARS = 400
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9 &,-]{0,39}$")


class JudgementError(ValueError):
    """The model output does not match the schema."""


class Judgement(BaseModel):
    """What the model says about one mail. Unknown fields, wrong types and out-of-range values are refused."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    category: str = Field(max_length=500)
    urgent: bool
    reason: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("reason", mode="before")
    @classmethod
    def _cut_reason(cls, value: Any) -> Any:  # noqa: ANN401
        return value[:REASON_MAX_CHARS] if isinstance(value, str) else value

    @field_validator("summary", mode="before")
    @classmethod
    def _cut_summary(cls, value: Any) -> Any:  # noqa: ANN401
        return value[:SUMMARY_MAX_CHARS] if isinstance(value, str) else value


@dataclass(frozen=True, slots=True)
class Filing:
    """File the mail under ``label``; ``create`` says the label does not exist yet."""

    label: str
    create: bool
    judgement: Judgement


@dataclass(frozen=True, slots=True)
class NeedsAttention:
    """The mail cannot be trusted to be ignorable: alert Marco instead."""

    reason: str


def parse_judgement(raw: object) -> Judgement:
    """Validate model output; raise ``JudgementError`` on anything that does not match."""
    try:
        return Judgement.model_validate(raw)
    except ValidationError:
        raise JudgementError("model output does not match the schema") from None


def _name_of(label: str) -> str:
    return label.removeprefix(LABEL_PREFIX)


def resolve(judgement: Judgement, existing: Collection[str]) -> Filing | NeedsAttention:
    """Turn a valid judgement into a label decision, within the category limit and name pattern."""
    if judgement.confidence < LOW_CONFIDENCE:
        return NeedsAttention("low_confidence")
    name = judgement.category.strip()
    known = {_name_of(label).casefold(): label for label in existing}
    if name.casefold() in known:
        return Filing(known[name.casefold()], create=False, judgement=judgement)
    if _NAME.fullmatch(name) and len(known) < MAX_CATEGORIES:
        return Filing(f"{LABEL_PREFIX}{name}", create=True, judgement=judgement)
    if OTHER_LABEL in existing:
        return Filing(OTHER_LABEL, create=False, judgement=judgement)
    if len(known) < MAX_CATEGORIES:
        return Filing(OTHER_LABEL, create=True, judgement=judgement)
    closest = get_close_matches(name.casefold(), list(known), n=1, cutoff=0.0)
    return Filing(known[closest[0]], create=False, judgement=judgement)


def decide(raw: object, existing: Collection[str]) -> Filing | NeedsAttention:
    """Parse and resolve in one step; output outside the schema is needs-attention, never ignorable."""
    try:
        return resolve(parse_judgement(raw), existing)
    except JudgementError:
        return NeedsAttention("invalid_output")
