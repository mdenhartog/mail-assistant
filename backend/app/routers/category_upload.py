"""Category file routes: upload with a bound preview, confirm and restore (U-label-structure-12, ADR-0058)."""

import uuid
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.auth.session import Session
from app.categories_models import CategoryList
from app.categories_repo import CategoriesRepository
from app.categories_write import to_response
from app.core.security import csrf, session
from app.errors import PROBLEM_MEDIA_TYPE, ProblemError, problem_response
from app.limit_guard import limit
from app.routers.settings import require_json
from app.schemas.category_upload import RestoreRequest, UploadConfirm, UploadPreview, UploadProblems422
from app.services.category_upload import CategoryUpload, FileRefused, Unconfirmable
from app.upload_preview_repo import UploadPreviewRepository

if TYPE_CHECKING:
    from app.clock import Clock
    from app.config import Settings
    from app.db import Database
    from app.ids import IdSource

router = APIRouter(tags=["categories"])

_FILE_TYPES = frozenset({"application/yaml", "application/x-yaml", "text/yaml", "text/x-yaml", "text/plain"})
_FILE_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {"application/yaml": {"schema": {"type": "string", "format": "binary"}}},
    }
}
_REFUSALS: dict[int | str, dict[str, Any]] = {
    401: {"description": "No live session"},
    403: {"description": "Missing or wrong token, wrong Origin or cross-site request"},
    409: {"description": "Nothing was stored: another session or file, an expired or used preview, a changed list"},
    429: {"description": "Too many list saves in an hour for the account; see Retry-After"},
    500: {"description": "The change could not be stored"},
}
_GUARDS = [Depends(limit("api")), Depends(session), Depends(csrf)]


def _service(request: Request) -> CategoryUpload:
    database: Database = request.app.state.database
    settings: Settings = request.app.state.settings
    clock: Clock = request.app.state.clock
    ids: IdSource = request.app.state.ids
    mailbox = settings.categories_mailbox_id
    return CategoryUpload(
        CategoriesRepository(database, mailbox),
        UploadPreviewRepository(database, mailbox),
        clock,
        ids,
        settings.category_saves_per_hour,
    )


def _require_file_type(request: Request) -> None:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in _FILE_TYPES:
        raise ProblemError(415)


def _refused(error: FileRefused) -> JSONResponse:
    body = UploadProblems422(type="about:blank", title="Unprocessable content", status=422, problems=error.problems)
    return JSONResponse(body.model_dump(mode="json", by_alias=True), status_code=422, media_type=PROBLEM_MEDIA_TYPE)


@router.post(
    "/categories/upload",
    response_model=UploadPreview,
    dependencies=_GUARDS,
    openapi_extra=_FILE_BODY,
    responses={
        **_REFUSALS,
        413: {"description": "The file is larger than the upload limit"},
        415: {"description": "The body is not declared as YAML"},
        422: {
            "model": UploadProblems422,
            "description": "The file breaks a rule; every problem with its line and field",
            "content": {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/UploadProblems422"}}},
        },
    },
)
async def upload_categories(request: Request, current: Session = Depends(session)) -> UploadPreview | JSONResponse:  # noqa: B008
    """Check a category file and return what confirming it would change; only the preview is stored.

    The body is the file itself (``application/yaml``). Nothing of the file is returned except the names of the
    categories that the stored list has and the file lacks.

    Args:
        request: The request, with the file as its body.
        current: The live session the preview is bound to.

    Returns:
        The preview, or a 422 with every problem of the file.
    """
    _require_file_type(request)
    data = await request.body()
    try:
        return await _service(request).preview(data, current.id_hash)
    except FileRefused as error:
        return _refused(error)
    except Unconfirmable:
        return problem_response(409)
    except DBAPIError:
        # Not logged and not chained: the driver text may carry the values of the file.
        return problem_response(500)


@router.post(
    "/categories/upload/{preview_id}/confirm",
    response_model=CategoryList,
    dependencies=[*_GUARDS, Depends(require_json)],
    responses={**_REFUSALS, 415: {"description": "The body is not JSON"}},
)
async def confirm_upload(
    preview_id: uuid.UUID,
    body: UploadConfirm,
    request: Request,
    current: Session = Depends(session),  # noqa: B008
) -> CategoryList | JSONResponse:
    """Replace the list with the previewed file as one new version, when every binding of the preview holds.

    Args:
        preview_id: The id the upload returned.
        body: The hash of the file the preview was made from.
        request: The request, whose app holds the database access and the settings.
        current: The live session; it must be the one that uploaded the file.

    Returns:
        The stored list, or a 409 and nothing stored.
    """
    try:
        return to_response(await _service(request).confirm(preview_id, body.file_hash, current.id_hash))
    except Unconfirmable:
        return problem_response(409)
    except DBAPIError:
        return problem_response(500)


@router.post(
    "/categories/restore-previous",
    response_model=CategoryList,
    dependencies=[*_GUARDS, Depends(require_json)],
    responses={**_REFUSALS, 415: {"description": "The body is not JSON"}},
)
async def restore_previous(body: RestoreRequest, request: Request) -> CategoryList | JSONResponse:
    """Store a new list version equal to the one before the current version.

    Args:
        body: The version the user sees as the current one.
        request: The request, whose app holds the database access and the settings.

    Returns:
        The stored list, or a 409 and nothing stored.
    """
    try:
        return to_response(await _service(request).restore_previous(body.version))
    except Unconfirmable:
        return problem_response(409)
    except DBAPIError:
        return problem_response(500)
