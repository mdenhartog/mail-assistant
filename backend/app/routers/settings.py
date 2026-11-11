"""Settings routes: ``GET /api/settings`` (U-web-settings-20); the write route follows in U-web-settings-22."""

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Request

from app.core.security import session
from app.limit_guard import limit
from app.settings_models import Settings
from app.settings_repo import SettingsRepository

if TYPE_CHECKING:
    from app.db import Database

router = APIRouter(tags=["settings"])


@router.get(
    "/settings",
    response_model=Settings,
    dependencies=[Depends(session), Depends(limit("api"))],
    responses={401: {"description": "No live session"}, 429: {"description": "Too many requests; see Retry-After"}},
)
async def read_settings(request: Request) -> Settings:
    """Return the stored settings, or the defaults at version 0 when nothing is stored yet.

    Args:
        request: The request, whose app holds the database access.

    Returns:
        The settings; the actor of the last change is never part of it.
    """
    database: Database = request.app.state.database
    return Settings.from_stored(await SettingsRepository(database).read())
