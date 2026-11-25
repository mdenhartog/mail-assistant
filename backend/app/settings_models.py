"""Request and response models of the settings API (U-web-settings-20)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints
from pydantic.alias_generators import to_camel

from app.settings_repo import StoredSettings
from category_policy import settings as bounds

HHMM = Annotated[str, StringConstraints(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]
_CONFIG = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)


class SettingsValues(BaseModel):
    """The schedule and the label cleanup numbers; times are ``HH:MM`` wall-clock times in ``time_zone``.

    The numbers are whole numbers, checked against their ranges by ``category_policy`` (not here), so a value outside
    its range gets the same 422 body as every other refused value.
    """

    model_config = _CONFIG

    time_zone: Annotated[str, StringConstraints(max_length=64)]
    quiet_start: HHMM
    quiet_end: HHMM
    overview_at: HHMM
    remind_at: HHMM
    waiting_minutes: StrictInt
    protection_days: StrictInt
    retention_days: StrictInt


class Range(BaseModel):
    """The lowest and highest value of a number and the value a new installation starts with."""

    model_config = _CONFIG

    min: int
    max: int
    default: int


class Ranges(BaseModel):
    """The ranges and defaults of the label cleanup numbers, so the page shows them without a copy of its own."""

    model_config = _CONFIG

    waiting_minutes: Range = Range(
        min=bounds.WAIT_MINUTES_MIN, max=bounds.WAIT_MINUTES_MAX, default=bounds.WAIT_MINUTES_DEFAULT
    )
    protection_days: Range = Range(
        min=bounds.PROTECTION_DAYS_MIN, max=bounds.PROTECTION_DAYS_MAX, default=bounds.PROTECTION_DAYS_DEFAULT
    )
    retention_days: Range = Range(
        min=bounds.RETENTION_DAYS_MIN, max=bounds.RETENTION_DAYS_MAX, default=bounds.RETENTION_DAYS_DEFAULT
    )


class Settings(BaseModel):
    """What ``GET /api/settings`` returns; never the actor."""

    model_config = _CONFIG

    values: SettingsValues
    ranges: Ranges
    version: Annotated[int, Field(ge=0)]
    updated_at: datetime | None
    updated_via: Literal["telegram", "web"] | None

    @classmethod
    def from_stored(cls, stored: StoredSettings) -> "Settings":
        """Build the response from the stored row.

        Args:
            stored: The row as the repository read it.

        Returns:
            The settings with ``HH:MM`` times; the database check keeps ``updated_via`` to its two channels.
        """
        policy = stored.policy
        return cls.model_validate(
            {
                "values": {
                    "time_zone": policy.zone,
                    "quiet_start": f"{policy.quiet_start:%H:%M}",
                    "quiet_end": f"{policy.quiet_end:%H:%M}",
                    "overview_at": f"{policy.overview_at:%H:%M}",
                    "remind_at": f"{policy.remind_at:%H:%M}",
                    "waiting_minutes": stored.cleanup.waiting_minutes,
                    "protection_days": stored.cleanup.protection_days,
                    "retention_days": stored.cleanup.retention_days,
                },
                "ranges": Ranges(),
                "version": stored.version,
                "updated_at": stored.updated_at,
                "updated_via": stored.updated_via,
            }
        )


class SettingsUpdate(BaseModel):
    """The body of the write route (U-web-settings-22): new values and the version they were based on."""

    model_config = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)

    values: SettingsValues
    version: Annotated[int, Field(ge=0)]


class SettingsReset(BaseModel):
    """The body of the reset route (U-web-settings-45): only the version the reset is based on."""

    model_config = _CONFIG

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
