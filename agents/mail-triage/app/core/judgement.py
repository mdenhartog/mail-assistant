"""The only shape the model may answer in, and the policy that turns it into a topic and an extra label (ADR-0055).

Mail text, category descriptions and the general instructions are untrusted. The model has no tools and may only name
a topic and at most one extra label by their ids from the current list (two closed sets); whatever it returns must
match ``Judgement`` exactly or the mail is treated as needing attention, never as ignorable. A topic id that is not
in the list files the mail under "Other" and drops the extra label; an extra id that is not in the list is dropped.
Urgency is kept either way, so a list can never lower an alert. The list has no cap here: the safety cap lives in
``category-policy``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from category_policy.kinds import Kind

if TYPE_CHECKING:
    from collections.abc import Sequence

    from category_policy.senders import SenderEntry

LABEL_PREFIX = "Assistant/"
OTHER_LABEL = f"{LABEL_PREFIX}Other"
OTHER_ID = "00000000-0000-0000-0000-000000000000"  # the nil UUID stands for the built-in "Other" (ADR-0043)
LOW_CONFIDENCE = 0.6
ID_MAX_CHARS = 1000  # a longer id in the answer is invalid
MAX_EXTRA_IDS_READ = 10  # a list of extra ids is read up to here; the first one is kept
REASON_MAX_CHARS = 200
SUMMARY_MAX_CHARS = 400


class JudgementError(ValueError):
    """The model output does not match the schema."""


class Judgement(BaseModel):
    """What the model says about one mail. Unknown fields, wrong types and out-of-range values are refused."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    topic_id: str = Field(min_length=1, max_length=ID_MAX_CHARS)
    extra_id: str | None = Field(default=None, max_length=ID_MAX_CHARS)
    urgent: bool
    reason: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("extra_id", mode="before")
    @classmethod
    def _one_extra(cls, value: Any) -> Any:  # noqa: ANN401
        """A model that names several extra labels keeps its first: a mail carries at most one."""
        if isinstance(value, list) and len(value) <= MAX_EXTRA_IDS_READ and all(isinstance(v, str) for v in value):
            return value[0] if value else None
        return value

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
    """One category of the list version being judged against, with what the sender rules need (ADR-0054)."""

    category_id: str
    name: str
    description: str
    kind: Kind = Kind.TOPIC
    notify: bool = False
    senders: tuple[SenderEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class JudgingList:
    """A snapshot of the list one mail is judged against; ``version`` 0 means no list version exists yet.

    ``general_instructions`` are the owner's working rules for the whole list: untrusted text for the model.
    """

    version: int
    categories: tuple[ListedCategory, ...]
    general_instructions: str = ""


@dataclass(frozen=True, slots=True)
class Filing:
    """File the mail under ``label``; ``category_id`` is the topic id recorded in ``filing`` (``OTHER_ID`` for "Other").

    ``extra`` is the extra-label category added next to the topic, ``None`` when there is none.
    """

    label: str
    category_id: str
    judgement: Judgement
    extra: ListedCategory | None = None


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


def category_label(category: ListedCategory) -> str:
    """The Gmail label name of a category."""
    return f"{LABEL_PREFIX}{category.name.strip()}"


def resolve(judgement: Judgement, categories: Sequence[ListedCategory]) -> Filing | NeedsAttention:
    """Turn a valid judgement into labels: a topic of the list by exact id, otherwise "Other" without an extra label."""
    if judgement.confidence < LOW_CONFIDENCE:
        return NeedsAttention("low_confidence")
    return file_under(judgement, categories)


def file_under(judgement: Judgement, categories: Sequence[ListedCategory]) -> Filing:
    """The topic and extra label the answer names, whatever its confidence (the plan build keeps the number itself)."""
    for category in categories:
        if (
            category.category_id == judgement.topic_id
            and category.kind is Kind.TOPIC
            and category.category_id != OTHER_ID
        ):
            return Filing(category_label(category), category.category_id, judgement, _extra(judgement, categories))
    return Filing(OTHER_LABEL, OTHER_ID, judgement)


def _extra(judgement: Judgement, categories: Sequence[ListedCategory]) -> ListedCategory | None:
    """The extra-label category the answer names, by exact id and kind; anything else is dropped."""
    for category in categories:
        if category.kind is Kind.EXTRA and category.category_id == judgement.extra_id:
            return category
    return None


def decide(raw: object, categories: Sequence[ListedCategory]) -> Filing | NeedsAttention:
    """Parse and resolve in one step; output outside the schema is needs-attention, never ignorable."""
    try:
        return resolve(parse_judgement(raw), categories)
    except JudgementError:
        return NeedsAttention("invalid_output")
