"""Settings routes: ``GET`` (U-web-settings-20) and ``PUT /api/settings`` (U-web-settings-22)."""

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.auth.session import Session
from app.core.security import csrf, session
from app.errors import PROBLEM_MEDIA_TYPE, ProblemError, problem_response
from app.limit_guard import limit
from app.settings_models import Conflict409, Problem422, Settings, SettingsUpdate
from app.settings_repo import SettingsRepository, VersionConflict
from app.settings_write import field_problems, to_policy
from schedule_policy.policy import validate

if TYPE_CHECKING:
    from app.db import Database

router = APIRouter(tags=["settings"])

_JSON = "application/json"


@router.get(
    "/settings",
    response_model=Settings,
    dependencies=[Depends(limit("api")), Depends(session)],
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


async def require_json(request: Request) -> None:
    """Refuse a body that is not declared as JSON before it is read as one.

    Args:
        request: The request.

    Raises:
        ProblemError: 415 for any other content type.
    """
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != _JSON:
        raise ProblemError(415)


def _problem_content(schema: str) -> dict[str, Any]:
    return {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": f"#/components/schemas/{schema}"}}}


def _problem_json(body: Problem422 | Conflict409) -> JSONResponse:
    return JSONResponse(
        body.model_dump(mode="json", by_alias=True), status_code=body.status, media_type=PROBLEM_MEDIA_TYPE
    )


@router.put(
    "/settings",
    response_model=Settings,
    dependencies=[Depends(limit("api")), Depends(session), Depends(csrf), Depends(require_json)],
    responses={
        401: {"description": "No live session"},
        403: {"description": "Missing or wrong token, wrong Origin or cross-site request"},
        409: {
            "model": Conflict409,
            "description": "The settings changed since the version sent; carries the current",
            "content": _problem_content("Conflict409"),
        },
        415: {"description": "The body is not JSON"},
        422: {
            "model": Problem422,
            "description": "A value is refused; the field, rule, value and an example",
            "content": _problem_content("Problem422"),
        },
        429: {"description": "Too many requests; see Retry-After"},
        500: {"description": "The change could not be stored"},
    },
)
async def write_settings(
    body: SettingsUpdate,
    request: Request,
    current: Session = Depends(session),  # noqa: B008
) -> Settings | JSONResponse:
    """Validate the whole row and store it if it is still at the version the change is based on.

    Args:
        body: The new values and the version they are based on.
        request: The request, whose app holds the database access.
        current: The live session; its keyed digest is the actor of the change.

    Returns:
        The stored settings at the next version, or a 409 with the current settings, or a 422 with the problems.
    """
    problems = validate(to_policy(body.values))
    if problems:
        items = field_problems(body.values, problems)
        return _problem_json(Problem422(type="about:blank", title="Unprocessable content", status=422, problems=items))
    database: Database = request.app.state.database
    try:
        stored = await SettingsRepository(database).write(to_policy(body.values), body.version, current.username_hash)
    except VersionConflict as conflict:
        return _problem_json(
            Conflict409(
                type="about:blank", title="Conflict", status=409, current=Settings.from_stored(conflict.current)
            )
        )
    except DBAPIError:
        # Not logged and not chained: the driver text may carry the zone the user typed.
        return problem_response(500)
    return Settings.from_stored(stored)
