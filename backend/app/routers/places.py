"""Place search for the time-zone combobox: ``GET /api/places?q=`` (U-web-settings-23)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.core.security import session
from app.limit_guard import limit
from schedule_policy.places import MAX_TEXT_LENGTH, lookup

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


@router.get(
    "/places",
    response_model=PlaceResults,
    dependencies=[Depends(session), Depends(limit("api"))],
    responses={401: {"description": "No live session"}, 422: {"description": "Query too long or invalid"}},
)
async def search_places(
    request: Request,
    q: Annotated[str, Query(max_length=MAX_TEXT_LENGTH, pattern=r"^[^\x00-\x1f\x7f]*$")],
) -> PlaceResults:
    """Find time zones for a typed place name, with the same lookup and aliases as Telegram.

    The query is validated before matching and is never logged.

    Args:
        request: The request; its clock gives the moment the UTC offsets are computed for.
        q: The typed text, at most 64 characters, no control characters.

    Returns:
        Up to five places, or a suggestion for a near miss, or neither.
    """
    result = lookup(q, now=request.app.state.clock.now())
    return PlaceResults(
        places=[Place(zone=h.zone, label=h.label, utc_offset_minutes=h.utc_offset_minutes) for h in result.hits],
        suggestion=result.suggestion,
    )
