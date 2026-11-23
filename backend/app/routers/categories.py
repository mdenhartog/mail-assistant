"""Category list routes: ``GET`` and ``PUT`` ``/api/categories`` (U-mail-categories-04, ADR-0042; v2, ADR-0053)."""

from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.categories_models import CategoryConflict409, CategoryList, CategoryListUpdate, CategoryProblem422
from app.categories_repo import CategoriesRepository, StoredList, VersionConflict
from app.categories_write import build, canonical_instructions, is_unchanged, problems_of, to_response
from app.core.security import csrf, session
from app.errors import PROBLEM_MEDIA_TYPE, RateLimited, problem_response
from app.limit_guard import limit
from app.routers.settings import require_json

if TYPE_CHECKING:
    from app.clock import Clock
    from app.config import Settings
    from app.db import Database
    from app.ids import IdSource

router = APIRouter(tags=["categories"])


def _repository(request: Request) -> CategoriesRepository:
    database: Database = request.app.state.database
    settings: Settings = request.app.state.settings
    return CategoriesRepository(database, settings.categories_mailbox_id)


def _problem_content(schema: str) -> dict[str, Any]:
    return {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": f"#/components/schemas/{schema}"}}}


def _conflict(stored: StoredList, reason: Literal["version", "not-ready"]) -> JSONResponse:
    body = CategoryConflict409(
        type="about:blank", title="Conflict", status=409, reason=reason, current=to_response(stored)
    )
    return JSONResponse(body.model_dump(mode="json", by_alias=True), status_code=409, media_type=PROBLEM_MEDIA_TYPE)


def _refusal(body: CategoryListUpdate, stored: StoredList) -> JSONResponse | None:
    """Return the 409 or 422 a save is refused with before anything is written, or None when it may go on."""
    if stored.version == 0:
        return _conflict(stored, "not-ready")
    if body.version != stored.version:
        return _conflict(stored, "version")
    problems = problems_of(body.categories, body.general_instructions, body.archive_label, stored)
    if not problems:
        return None
    refusal = CategoryProblem422(type="about:blank", title="Unprocessable content", status=422, problems=problems)
    return JSONResponse(refusal.model_dump(mode="json", by_alias=True), status_code=422, media_type=PROBLEM_MEDIA_TYPE)


@router.get(
    "/categories",
    response_model=CategoryList,
    dependencies=[Depends(limit("api")), Depends(session)],
    responses={401: {"description": "No live session"}, 429: {"description": "Too many requests; see Retry-After"}},
)
async def read_categories(request: Request) -> CategoryList:
    """Return the stored list with the mail counts, "Other" and the older categories.

    Args:
        request: The request, whose app holds the database access.

    Returns:
        The list; version 0 and ``ready`` false until the agent has written version 1.
    """
    return to_response(await _repository(request).read())


@router.put(
    "/categories",
    response_model=CategoryList,
    dependencies=[Depends(limit("api")), Depends(session), Depends(csrf), Depends(require_json)],
    responses={
        401: {"description": "No live session"},
        403: {"description": "Missing or wrong token, wrong Origin or cross-site request"},
        409: {
            "model": CategoryConflict409,
            "description": "The list changed since the version sent, or the agent has not written version 1 yet",
            "content": _problem_content("CategoryConflict409"),
        },
        415: {"description": "The body is not JSON"},
        422: {
            "model": CategoryProblem422,
            "description": "A rule is broken; the rule, the field and the position of each problem",
            "content": _problem_content("CategoryProblem422"),
        },
        429: {"description": "Too many saves in an hour for the account; see Retry-After"},
        500: {"description": "The change could not be stored"},
    },
)
async def write_categories(body: CategoryListUpdate, request: Request) -> CategoryList | JSONResponse:
    """Validate the whole list and store it as the next version if it is still based on the latest one.

    A list equal to the stored one stores nothing and returns the stored list.

    Args:
        body: The new list and the version it is based on.
        request: The request, whose app holds the database access, the settings and the id source.

    Returns:
        The stored list, or a 409 with the current list, or a 422 with the problems, or a generic 500.

    Raises:
        RateLimited: The account used up its saves of the hour.
    """
    repository = _repository(request)
    settings: Settings = request.app.state.settings
    clock: Clock = request.app.state.clock
    recent = await repository.recent_saves(clock.now())
    if recent.saves >= settings.category_saves_per_hour:
        raise RateLimited(recent.retry_after_seconds)
    stored = await repository.read()
    refusal = _refusal(body, stored)
    if refusal is not None:
        return refusal
    ids: IdSource = request.app.state.ids
    rows, new_ids = build(body.categories, ids.category_id)
    instructions = canonical_instructions(body.general_instructions)
    if is_unchanged(rows, instructions, body.archive_label, stored):
        return to_response(stored)
    try:
        await repository.add_version(stored.version, rows, new_ids, instructions, body.archive_label)
    except VersionConflict:
        return _conflict(await repository.read(), "version")
    except DBAPIError:
        # Not logged and not chained: the driver text may carry the names the user typed.
        return problem_response(500)
    return to_response(await repository.read())
