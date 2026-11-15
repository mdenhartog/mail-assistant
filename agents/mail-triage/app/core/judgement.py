"""The only shape the model may answer in, and the policy that turns it into a category (ADR-0045, AC-5 to AC-8).

Mail text and category descriptions are untrusted. The model has no tools and may only name a category by its id from
the current list (a closed set); whatever it returns must match ``Judgement`` exactly or the mail is treated as
needing attention, never as ignorable. An id that is not in the list files the mail under "Other" and keeps the
model's urgency, so a list can never lower an alert. The list has no cap here: the safety cap lives in
``category-policy``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

if TYPE_CHECKING:
    from collections.abc import Sequence

LABEL_PREFIX = "Assistant/"
OTHER_LABEL = f"{LABEL_PREFIX}Other"
OTHER_ID = "00000000-0000-0000-0000-000000000000"  # the nil UUID stands for the built-in "Other" (ADR-0043)
LOW_CONFIDENCE = 0.6
CATEGORY_ID_MAX_CHARS = 1000  # AC-7: a longer answer is invalid
REASON_MAX_CHARS = 200
SUMMARY_MAX_CHARS = 400


class JudgementError(ValueError):
    """The model output does not match the schema."""


class Judgement(BaseModel):
    """What the model says about one mail. Unknown fields, wrong types and out-of-range values are refused."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    category_id: str = Field(min_length=1, max_length=CATEGORY_ID_MAX_CHARS)
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
class ListedCategory:
    """One category of the list version being judged against."""

    category_id: str
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class Filing:
    """File the mail under ``label``; ``category_id`` is the id recorded in ``filing`` (``OTHER_ID`` for "Other")."""

    label: str
    category_id: str
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


def resolve(judgement: Judgement, categories: Sequence[ListedCategory]) -> Filing | NeedsAttention:
    """Turn a valid judgement into a label: a category of the list by exact id, otherwise "Other"."""
    if judgement.confidence < LOW_CONFIDENCE:
        return NeedsAttention("low_confidence")
    for category in categories:
        if category.category_id == judgement.category_id and category.category_id != OTHER_ID:
            return Filing(f"{LABEL_PREFIX}{category.name.strip()}", category.category_id, judgement)
    return Filing(OTHER_LABEL, OTHER_ID, judgement)


def decide(raw: object, categories: Sequence[ListedCategory]) -> Filing | NeedsAttention:
    """Parse and resolve in one step; output outside the schema is needs-attention, never ignorable."""
    try:
        return resolve(parse_judgement(raw), categories)
    except JudgementError:
        return NeedsAttention("invalid_output")
