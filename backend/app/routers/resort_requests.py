"""Sort-again routes: ``POST /api/resort-requests`` and ``GET /api/resort-requests/latest`` (U-label-structure-21)."""

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app.core.security import csrf, session
from app.errors import problem_response
from app.limit_guard import limit
from app.plan_repo import PlanConflict, PlanMalformed
from app.resort_repo import ResortRepository
from app.routers.settings import require_json
from app.schemas.resort_requests import ResortLatest, ResortRequestCreate, ResortRequested
from app.services.resort_requests import ResortRequests

if TYPE_CHECKING:
    from app.clock import Clock
    from app.config import Settings
    from app.db import Database

router = APIRouter(tags=["categories"])


def _service(request: Request) -> ResortRequests:
    database: Database = request.app.state.database
    settings: Settings = request.app.state.settings
    clock: Clock = request.app.state.clock
    return ResortRequests(
        ResortRepository(database, settings.categories_mailbox_id), clock, settings.category_saves_per_hour
    )


@router.post(
    "/resort-requests",
    status_code=201,
    response_model=ResortRequested,
    dependencies=[Depends(limit("api")), Depends(session), Depends(csrf), Depends(require_json)],
    responses={
        401: {"description": "No live session"},
        403: {"description": "Missing or wrong token, wrong Origin or cross-site request"},
        409: {"description": "A plan is open, or the latest request has not become a plan yet; nothing was stored"},
        415: {"description": "The body is not JSON"},
        422: {"description": "The threshold is not a JSON integer from 50 to 100"},
        429: {"description": "Too many requests in an hour (the limit of list saves); see Retry-After"},
        500: {"description": "The request could not be stored"},
    },
)
async def create_resort_request(body: ResortRequestCreate, request: Request) -> ResortRequested | JSONResponse:
    """Ask the agent to sort the mail again with a threshold; one request while no plan or request is open.

    Args:
        body: The threshold, a JSON integer from 50 to 100.
        request: The request, whose app holds the database access, the settings and the clock.

    Returns:
        The id of the request and its threshold, or a 409 with nothing stored.

    Raises:
        RateLimited: The hourly limit is used up.
    """
    try:
        request_id = await _service(request).ask(body.threshold)
    except PlanConflict:
        return problem_response(409)
    except PlanMalformed:
        return problem_response(422)
    except DBAPIError:
        # Not logged and not chained: nothing of the driver text is for the response.
        return problem_response(500)
    return ResortRequested(request_id=request_id, threshold=body.threshold)


@router.get(
    "/resort-requests/latest",
    response_model=ResortLatest,
    dependencies=[Depends(limit("api")), Depends(session)],
    responses={401: {"description": "No live session"}, 429: {"description": "Too many requests; see Retry-After"}},
)
async def read_latest_resort_request(request: Request) -> ResortLatest:
    """Return the value the threshold field shows: 50 on the first visit, else the latest request's threshold.

    Args:
        request: The request, whose app holds the database access.

    Returns:
        The threshold.
    """
    return ResortLatest(threshold=await _service(request).latest_threshold())
