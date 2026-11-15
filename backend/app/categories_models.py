"""Request and response models of the category list API (U-mail-categories-04)."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

_CONFIG = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)


class CategoryItem(BaseModel):
    """One category of the stored list with the number of mails filed under it."""

    model_config = _CONFIG

    id: uuid.UUID
    name: str
    description: str
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


class CategoryListUpdate(BaseModel):
    """The body of the write route: the whole list and the version it is based on."""

    model_config = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)

    version: Annotated[int, Field(ge=0)]
    categories: list[CategoryInput]


class CategoryProblem(BaseModel):
    """One refusal: the rule, the field and the position of the category (None for the whole list). No value."""

    model_config = _CONFIG

    rule: str
    field: Literal["name", "description", "id", "list"]
    index: int | None


class Problem422(BaseModel):
    """The 422 body of the write route."""

    model_config = _CONFIG

    type: str
    title: str
    status: Literal[422]
    problems: list[CategoryProblem]


class Conflict409(BaseModel):
    """The 409 body of the write route: ``version`` (the list changed) or ``not-ready`` (no seed yet), and the list."""

    model_config = _CONFIG

    type: str
    title: str
    status: Literal[409]
    reason: Literal["version", "not-ready"]
    current: CategoryList
