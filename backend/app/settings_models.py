"""Request and response models of the settings API (U-web-settings-20)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel

from app.settings_repo import StoredSettings

HHMM = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]
_CONFIG = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)


class SettingsValues(BaseModel):
    """The five values of the schedule; times are ``HH:MM`` wall-clock times in ``time_zone``."""

    model_config = _CONFIG

    time_zone: Annotated[str, StringConstraints(max_length=64)]
    quiet_start: HHMM
    quiet_end: HHMM
    overview_at: HHMM
    remind_at: HHMM


class Settings(BaseModel):
    """What ``GET /api/settings`` returns; never the actor."""

    model_config = _CONFIG

    values: SettingsValues
    version: Annotated[int, Field(ge=0)]
    updated_at: datetime | None
    updated_via: Literal["telegram", "web"] | None

    @classmethod
    def from_stored(cls, stored: StoredSettings) -> "Settings":
        """Build the response from the stored row."""
        raise NotImplementedError


class SettingsUpdate(BaseModel):
    """The body of the write route (U-web-settings-22): new values and the version they were based on."""

    model_config = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)

    values: SettingsValues
    version: Annotated[int, Field(ge=0)]


class ProblemItem(BaseModel):
    """One refused field."""

    model_config = _CONFIG

    field: str
    rule: str
    value: str
    example: str


class Problem422(BaseModel):
    """The 422 body of the write route."""

    model_config = _CONFIG

    type: str
    title: str
    status: Literal[422]
    problems: list[ProblemItem]


class Conflict409(BaseModel):
    """The 409 body of the write route: the current settings."""

    model_config = _CONFIG

    type: str
    title: str
    status: Literal[409]
    current: Settings
