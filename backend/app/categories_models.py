"""Request and response models of the category list API (U-mail-categories-04, category contract v2).

The v2 fields (U-label-structure-11, ADR-0053) are required on a save: no default stands in for a missing one.
"""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool
from pydantic.alias_generators import to_camel

from category_policy import Kind

_CONFIG = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)


class SenderItem(BaseModel):
    """A sender entry of a category: a full address or a domain, with the opt-in for subdomains.

    On a save it is the text as typed; on a read it is the stored form (lower-case A-labels).
    """

    model_config = _CONFIG

    entry: str
    subdomains: StrictBool


class SenderView(BaseModel):
    """A sender entry as ``GET /api/categories`` shows it: the stored form and how many mails it skipped (read-only).

    The count is not a field of ``SenderItem``: a save refuses it (``extra="forbid"``).
    """

    model_config = _CONFIG

    entry: str
    subdomains: bool
    skipped_count: Annotated[int, Field(ge=0)]


class CategoryItem(BaseModel):
    """One category of the stored list with the number of mails filed under it."""

    model_config = _CONFIG

    id: uuid.UUID
    name: str
    description: str
    kind: Kind
    notify: bool
    senders: list[SenderView]
    mail_count: Annotated[int, Field(ge=0)]


class OtherItem(BaseModel):
    """The built-in "Other": it has no name to change and cannot be removed."""

    model_config = _CONFIG

    mail_count: Annotated[int, Field(ge=0)]


class OlderCategory(BaseModel):
    """An ``Assistant/`` label in Gmail that is not on the list; ``mail_count`` is None while it is not counted."""

    model_config = _CONFIG

    label_name: str
    mail_count: Annotated[int, Field(ge=0)] | None


class CategoryList(BaseModel):
    """What ``GET /api/categories`` returns; ``ready`` is False until the agent has written version 1."""

    model_config = _CONFIG

    version: Annotated[int, Field(ge=0)]
    ready: bool
    categories: list[CategoryItem]
    general_instructions: str
    other: OtherItem
    older_categories: list[OlderCategory]


class CategoryInput(BaseModel):
    """One category as the user writes it; a missing ``id`` is a new category.

    The text is not bounded here: the rules of ``category_policy`` decide and answer with ``problems``.
    """

    model_config = _CONFIG

    id: uuid.UUID | None = None
    name: str
    description: str
    kind: Kind
    notify: StrictBool
    senders: list[SenderItem]


class CategoryListUpdate(BaseModel):
    """The body of the write route: the whole list and the version it is based on."""

    model_config = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)

    version: Annotated[int, Field(ge=0)]
    categories: list[CategoryInput]
    general_instructions: str


class CategoryProblem(BaseModel):
    """One refusal: the rule, the field, the category (None for the whole list) and for a sender entry its position.

    ``other_index`` names the category that already has the entry of a ``sender_duplicate`` (the same category when it
    repeats the entry itself). No value is ever carried.
    """

    model_config = _CONFIG

    rule: str
    field: Literal["name", "description", "id", "list", "senders", "instructions"]
    index: int | None
    position: int | None
    other_index: int | None


class CategoryProblem422(BaseModel):
    """The 422 body of the write route."""

    model_config = _CONFIG

    type: str
    title: str
    status: Literal[422]
    problems: list[CategoryProblem]


class CategoryConflict409(BaseModel):
    """The 409 body of the write route: ``version`` (the list changed) or ``not-ready`` (no seed yet), and the list."""

    model_config = _CONFIG

    type: str
    title: str
    status: Literal[409]
    reason: Literal["version", "not-ready"]
    current: CategoryList
