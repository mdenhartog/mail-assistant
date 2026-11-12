"""Request and response models of the settings API (U-web-settings-20)."""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from pydantic.alias_generators import to_camel
from pydantic.json_schema import models_json_schema

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
                },
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


def declare_write_schemas(app: FastAPI) -> None:
    """Add the schemas of the write route to the OpenAPI document before that route exists (U-web-settings-22).

    ``SettingsUpdate``, ``Problem422`` and ``Conflict409`` are part of the contract the web client types are generated
    from. Once the write route uses them FastAPI emits them itself and this hook can go.

    Args:
        app: The application whose document is extended.
    """
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        schema = generate()
        schemas: dict[str, Any] = schema.setdefault("components", {}).setdefault("schemas", {})
        if "SettingsUpdate" not in schemas:
            _, extra = models_json_schema(
                [(SettingsUpdate, "validation"), (Problem422, "serialization"), (Conflict409, "serialization")],
                ref_template="#/components/schemas/{model}",
            )
            for name, definition in extra.get("$defs", {}).items():
                schemas.setdefault(name, definition)
        return schema

    app.openapi = openapi
