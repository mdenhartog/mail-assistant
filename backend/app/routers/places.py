"""Place search for the time-zone combobox: ``GET /api/places?q=`` (U-web-settings-23)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.core.security import session
from app.limit_guard import limit

router = APIRouter(tags=["places"])


class Place(BaseModel):
    """One selectable time zone."""

    model_config = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)

    zone: str
    label: str
    utc_offset_minutes: int


class PlaceResults(BaseModel):
    """Up to five places, or a near-miss suggestion, or neither."""

    model_config = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)

    places: list[Place]
    suggestion: str | None = None


@router.get("/places", response_model=PlaceResults, dependencies=[Depends(session), Depends(limit("api"))])
async def search_places(q: Annotated[str, Query()] = "") -> PlaceResults:
    """Skeleton: not implemented yet."""
    return PlaceResults(places=[])
