"""Request and response models of the sort-again routes (U-label-structure-21, ADR-0056)."""

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

MIN_THRESHOLD = 50
MAX_THRESHOLD = 100
DEFAULT_THRESHOLD = MIN_THRESHOLD  # what the field shows on the first visit

_CONFIG = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)
# Strict: only a JSON integer passes; "50 ", "50", 50.5, 50.0 and true are refused before anything is asked.
Threshold = Annotated[
    int,
    Field(
        strict=True,
        ge=MIN_THRESHOLD,
        le=MAX_THRESHOLD,
        description="How sure the agent must be, in percent, for a move to be approved without review.",
    ),
]


class ResortRequestCreate(BaseModel):
    """The body of a sort-again request."""

    model_config = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)

    threshold: Threshold


class ResortRequested(BaseModel):
    """The answer to a stored request: its id and the threshold it holds."""

    model_config = _CONFIG

    request_id: uuid.UUID
    threshold: Threshold


class ResortLatest(BaseModel):
    """The value the threshold field shows: 50 on the first visit, else the latest request's threshold."""

    model_config = _CONFIG

    threshold: Threshold
