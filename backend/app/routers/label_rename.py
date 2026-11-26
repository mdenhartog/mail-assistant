"""Label rename routes: the preview, the confirmation, the restore and the recently deleted record (ADR-0061)."""

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.core.security import csrf, session
from app.errors import problem_response
from app.label_rename_repo import LabelRenameRepository
from app.limit_guard import limit
from app.plan_repo import PlanConflict, PlanMalformed
from app.routers.settings import require_json
from app.schemas.label_rename import (
    DeletedLabels,
    RenameConfirm,
    RenameConfirmed,
    RenamePreview,
    RestoreRequested,
)
from app.services.label_rename import LabelRename

if TYPE_CHECKING:
    from app.clock import Clock
    from app.config import Settings
    from app.db import Database

router = APIRouter(tags=["categories"])

_READ = [Depends(limit("api")), Depends(session)]
_READ_ERRORS: dict[int | str, dict[str, str]] = {
    401: {"description": "No live session"},
    429: {"description": "Too many requests; see Retry-After"},
}
_CSRF_ERROR: dict[int | str, dict[str, str]] = {
    403: {"description": "Missing or wrong token, wrong Origin or cross-site request"},
}


def _service(request: Request) -> LabelRename:
    database: Database = request.app.state.database
    settings: Settings = request.app.state.settings
    clock: Clock = request.app.state.clock
    return LabelRename(LabelRenameRepository(database, settings.categories_mailbox_id), clock)


@router.get("/label-rename", response_model=RenamePreview, dependencies=_READ, responses=_READ_ERRORS)
async def read_label_rename(request: Request) -> RenamePreview:
    """Return the rename plan, largest labels first, with its state and the hash to confirm it with.

    Args:
        request: The request, whose app holds the database access.

    Returns:
        The state, the plan hash, the items and a summary. Nothing is changed.
    """
    return await _service(request).preview()


@router.post(
    "/label-rename/confirmation",
    response_model=RenameConfirmed,
    dependencies=[*_READ, Depends(csrf), Depends(require_json)],
    responses={
        **_READ_ERRORS,
        **_CSRF_ERROR,
        409: {"description": "The hash is wrong, stale or replayed, or the plan is not pending; nothing was stored"},
        415: {"description": "The body is not JSON"},
        422: {"description": "The body has the wrong shape, or a skipped id is not in the plan"},
        500: {"description": "The confirmation could not be stored"},
    },
)
async def confirm_label_rename(body: RenameConfirm, request: Request) -> RenameConfirmed | JSONResponse:
    """Confirm the plan that was shown; the same hash and skip set again returns the same confirmation.

    Args:
        body: The plan hash and the ids to skip.
        request: The request, whose app holds the database access.

    Returns:
        The id of the confirmation, or a generic problem with nothing stored.
    """
    try:
        confirmation = await _service(request).confirm(body.plan_hash, body.skipped_ids)
    except PlanConflict:
        return problem_response(409)
    except PlanMalformed:
        return problem_response(422)
    except DBAPIError:
        return problem_response(500)  # not logged and not chained: nothing of the driver text is for the response
    return RenameConfirmed(confirmation_id=confirmation)


@router.post(
    "/label-rename/restore",
    response_model=RestoreRequested,
    dependencies=[*_READ, Depends(csrf)],
    responses={
        **_READ_ERRORS,
        **_CSRF_ERROR,
        409: {"description": "No label was renamed yet; nothing was stored"},
        500: {"description": "The request could not be stored"},
    },
)
async def restore_label_rename(request: Request) -> RestoreRequested | JSONResponse:
    """Ask the agent to restore the old names; one open request at a time.

    Args:
        request: The request, whose app holds the database access.

    Returns:
        The id of the open restore request, or a generic problem with nothing stored.
    """
    try:
        requested = await _service(request).restore()
    except PlanConflict:
        return problem_response(409)
    except DBAPIError:
        return problem_response(500)
    return RestoreRequested(request_id=requested)


@router.get("/label-rename/deleted", response_model=DeletedLabels, dependencies=_READ, responses=_READ_ERRORS)
async def read_deleted_labels(request: Request) -> DeletedLabels:
    """Return the labels the agent deleted within the retention period, newest first (read-only).

    Args:
        request: The request, whose app holds the database access and the clock.

    Returns:
        The retention in days and the names with the time they were deleted.
    """
    return await _service(request).deleted()
