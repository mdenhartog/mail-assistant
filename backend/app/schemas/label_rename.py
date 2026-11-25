"""Request and response models of the label rename routes (U-label-prefix-removal-11, ADR-0061).

Label names appear in the two read responses only: they are never part of an error, a log line or an audit row.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

_CONFIG = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)
MAX_SKIPPED = 10000  # Gmail allows at most this many labels
PlanHash = Annotated[
    str,
    Field(pattern=r"^[0-9a-f]{64}$", description="The hash of the plan the user saw, as the preview gave it."),
]
LabelId = Annotated[str, Field(min_length=1, max_length=256)]


class RenameItem(BaseModel):
    """One label of the plan."""

    model_config = _CONFIG

    id: str
    old_name: str
    new_name: str
    mail_count: int
    action: Literal["rename", "merge"]
    item_state: Literal["planned", "skipped", "done", "kept"]


class RenameSummary(BaseModel):
    """How many labels and mails the plan touches."""

    model_config = _CONFIG

    labels: int
    mails: int


class RenamePreview(BaseModel):
    """The plan, its state and the hash to confirm it with; ``none`` when the mailbox has no migration."""

    model_config = _CONFIG

    state: Literal["none", "pending", "confirmed", "done"]
    plan_hash: str | None
    items: list[RenameItem]
    summary: RenameSummary


class RenameConfirm(BaseModel):
    """The confirmation: the hash of the plan that was shown and the ids the user keeps as they are."""

    model_config = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)

    plan_hash: PlanHash
    skipped_ids: Annotated[list[LabelId], Field(max_length=MAX_SKIPPED)]


class RenameConfirmed(BaseModel):
    """The id of the stored confirmation (the same on a repeat)."""

    model_config = _CONFIG

    confirmation_id: uuid.UUID


class RestoreRequested(BaseModel):
    """The id of the open restore request (the same on a repeat)."""

    model_config = _CONFIG

    request_id: uuid.UUID


class DeletedLabel(BaseModel):
    """A label the agent deleted: its name and when."""

    model_config = _CONFIG

    name: str
    deleted_at: datetime


class DeletedLabels(BaseModel):
    """The recently deleted labels, newest first, for the retention period."""

    model_config = _CONFIG

    retention_days: int
    items: list[DeletedLabel]
