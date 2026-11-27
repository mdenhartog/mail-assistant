"""Request and response models of the category file routes (U-label-structure-12, ADR-0058)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

_CONFIG = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)
_HASH = r"^[0-9a-f]{64}$"


class UploadPreview(BaseModel):
    """What an upload returns: the preview id, the hash to confirm with and what a confirm would change."""

    model_config = _CONFIG

    preview_id: uuid.UUID
    file_hash: Annotated[str, Field(pattern=_HASH)]
    base_version: Annotated[int, Field(ge=1)]
    expires_at: datetime
    added: Annotated[int, Field(ge=0)]
    adopted: Annotated[
        int,
        Field(ge=0, description="How many new or renamed categories take over a label that already exists in Gmail."),
    ]
    changed: Annotated[int, Field(ge=0)]
    removed: Annotated[int, Field(ge=0)]
    removed_categories: list[str]
    instructions_changed: bool
    archive_label_changed: Annotated[
        bool, Field(description="True when the file gives a different archive label; absent keeps the stored one.")
    ]


class UploadConfirm(BaseModel):
    """The body of a confirm: the hash of the file the preview was made from."""

    model_config = _CONFIG

    file_hash: Annotated[str, Field(pattern=_HASH)]


class RestoreRequest(BaseModel):
    """The body of a restore: the version the user sees as the current one."""

    model_config = _CONFIG

    version: Annotated[int, Field(ge=1)]


class UploadProblem(BaseModel):
    """One problem of a refused file: the rule, the line and field in the file and a fixed text, never a value."""

    model_config = _CONFIG

    rule: str
    line: Annotated[int, Field(ge=1)]
    field: str
    message: str


class UploadProblems422(BaseModel):
    """The 422 body of an upload: every problem of the file."""

    model_config = _CONFIG

    type: str
    title: str
    status: Literal[422]
    problems: list[UploadProblem]
