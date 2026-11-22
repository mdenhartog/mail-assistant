"""Category file routes: export of the list and the template files (U-label-structure-13, ADR-0058)."""

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.categories_repo import CategoriesRepository
from app.core.security import session
from app.errors import problem_response
from app.limit_guard import limit
from app.services.category_export import EXPORT_NAME, TEMPLATE_NAMES, NoList, TemplateKind, export_list, template_file

if TYPE_CHECKING:
    from app.config import Settings
    from app.db import Database

router = APIRouter(tags=["categories"])

_YAML = "application/yaml"
_GUARDS = [Depends(limit("api")), Depends(session)]
_FILE_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {"description": "The file", "content": {_YAML: {"schema": {"type": "string"}}}},
    401: {"description": "No live session"},
    429: {"description": "Too many requests; see Retry-After"},
}


def _attachment(content: bytes, name: str) -> Response:
    # The middleware adds nosniff and no-store to every response; they are named here as well so that this
    # route never depends on it for a file that holds the user's list.
    return Response(
        content,
        media_type=_YAML,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/categories/export",
    response_model=str,
    dependencies=_GUARDS,
    responses={**_FILE_RESPONSE, 409: {"description": "There is no list yet"}},
)
async def export_categories(request: Request) -> Response | JSONResponse:
    """Send the current list as ``mail-categories.yaml`` (schema 1), the same format the upload reads.

    Args:
        request: The request, whose app holds the database access and the settings.

    Returns:
        The file as an attachment, or a 409 while there is no list.
    """
    database: Database = request.app.state.database
    settings: Settings = request.app.state.settings
    try:
        content = await export_list(CategoriesRepository(database, settings.categories_mailbox_id))
    except NoList:
        return problem_response(409)
    return _attachment(content, EXPORT_NAME)


@router.get("/categories/template", response_model=str, dependencies=_GUARDS, responses=_FILE_RESPONSE)
async def category_template(file: TemplateKind = "template") -> Response:
    """Send the commented template file, or the example file with a worked list.

    Args:
        file: ``template`` (every field explained) or ``example``.

    Returns:
        The file as an attachment.
    """
    return _attachment(await template_file(file), TEMPLATE_NAMES[file])
