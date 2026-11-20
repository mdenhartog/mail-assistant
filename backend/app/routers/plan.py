"""Review plan routes: plan, items, decisions, approve and move back (U-mail-categories-17, ADR-0044, ADR-0047).

Decisions and the approval call the database functions; the move-back request is one insert guarded by a trigger. A
plan, count, group, id or state mismatch is a 409; 403 stays for the lock-free CSRF and Origin checks. Sender and
subject are only ever read into the response of the items route.
"""

import uuid
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.core.security import csrf, session
from app.errors import PROBLEM_MEDIA_TYPE, problem_response
from app.limit_guard import limit
from app.plan_models import (
    MAX_IDS,
    MAX_PAGE,
    PAGE_SIZE,
    AllScope,
    ApprovalResult,
    ApproveRequest,
    DecisionRequest,
    DecisionResult,
    GroupExample,
    GroupScope,
    IdsScope,
    ItemSearchRequest,
    LastPlan,
    MoveBackResult,
    PlanConflict409,
    PlanCounts,
    PlanGroup,
    PlanItem,
    PlanItemsPage,
    PlanProblem422,
    PlanProgress,
    PlanView,
)
from app.plan_repo import (
    EndedPlan,
    ItemQuery,
    ItemsPage,
    OpenPlan,
    PlanConflict,
    PlanMalformed,
    PlanRepository,
    PlanSnapshot,
)
from app.routers.settings import require_json

if TYPE_CHECKING:
    from app.config import Settings
    from app.db import Database

router = APIRouter(tags=["plan"])

_CONFLICT_BODY = PlanConflict409(type="about:blank", title="Conflict", status=409)
_TOO_MANY_IDS = PlanProblem422(type="about:blank", title="Unprocessable content", status=422, reason="too_many_ids")


def _repository(request: Request) -> PlanRepository:
    database: Database = request.app.state.database
    settings: Settings = request.app.state.settings
    return PlanRepository(database, settings.categories_mailbox_id)


def _problem_content(schema: str) -> dict[str, Any]:
    return {PROBLEM_MEDIA_TYPE: {"schema": {"$ref": f"#/components/schemas/{schema}"}}}


def _conflict() -> JSONResponse:
    return JSONResponse(_CONFLICT_BODY.model_dump(mode="json"), status_code=409, media_type=PROBLEM_MEDIA_TYPE)


_CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    409: {
        "model": PlanConflict409,
        "description": "The plan, the item count, the group, an id or the state no longer matches; nothing changed",
        "content": _problem_content("PlanConflict409"),
    }
}
_WRITE_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"description": "No live session, or the web lock is set"},
    403: {"description": "Missing or wrong token, wrong Origin or cross-site request"},
    415: {"description": "The body is not JSON"},
    422: {"description": "The body is malformed"},
    429: {"description": "Too many requests; see Retry-After"},
}


def progress_view(plan: OpenPlan | None) -> PlanProgress:
    """How far the build is; every number is zero and the estimate unknown when no plan is open."""
    if plan is None:
        return PlanProgress(checked=0, cap=0, unclear=0, estimate=None, not_looked_at=0)
    return PlanProgress(
        checked=plan.checked,
        cap=plan.cap,
        unclear=plan.unclear,
        estimate=plan.estimate,
        not_looked_at=plan.not_looked_at,
    )


def last_plan_view(last: EndedPlan | None) -> LastPlan | None:
    """The plan that ended most recently, or None when no plan has ended."""
    if last is None:
        return None
    return LastPlan(
        id=last.id,
        state=last.state,  # pyright: ignore[reportArgumentType]  # the query selects the three states
        ended_at=last.ended_at,
        moved_count=last.moved,
    )


def _view(snapshot: PlanSnapshot) -> PlanView:
    plan = snapshot.open
    decisions = snapshot.decisions
    last = snapshot.last_ended
    return PlanView(
        id=None if plan is None else plan.id,
        state=None if plan is None else plan.state,  # pyright: ignore[reportArgumentType]  # the table checks the set
        progress=progress_view(plan),
        groups=[
            PlanGroup(
                from_category=g.old_id,
                to_category=g.new_id,
                count=g.count,
                approved=g.approved,
                rejected=g.rejected,
                example=GroupExample(sender_name=g.sender_name, sender_address=g.sender_address, subject=g.subject),
            )
            for g in snapshot.groups
        ],
        counts=PlanCounts(
            items=sum(decisions.values()),
            pending=decisions.get("pending", 0),
            approved=decisions.get("approved", 0),
            rejected=decisions.get("rejected", 0),
        ),
        apply_after=None if plan is None else plan.apply_after,
        apply_threshold=snapshot.apply_threshold,
        apply_delay_minutes=snapshot.apply_delay_minutes,
        last_plan=last_plan_view(last),
    )


def _scope_json(scope: GroupScope | IdsScope | AllScope) -> dict[str, Any]:
    """The scope in the shape ``record_decision`` takes."""
    if isinstance(scope, GroupScope):
        return {
            "kind": "group",
            "from": str(scope.group.from_category),
            "to": str(scope.group.to_category),
            "groupCount": scope.group_count,
        }
    if isinstance(scope, IdsScope):
        return {"kind": "ids", "ids": scope.ids}
    return {"kind": "all"}


@router.get(
    "/plan",
    response_model=PlanView,
    response_model_by_alias=True,
    dependencies=[Depends(limit("api")), Depends(session)],
    responses={
        401: {"description": "No live session, or the web lock is set"},
        429: {"description": "Too many requests"},
    },
)
async def read_plan(request: Request) -> PlanView:
    """Return the open plan with its progress, groups, counts and apply time, and the plan that ended last.

    Args:
        request: The request, whose app holds the database access.

    Returns:
        The plan view; ``state`` is null while no plan is open.
    """
    return _view(await _repository(request).snapshot())


def _items_page(found: ItemsPage, page: int) -> PlanItemsPage:
    return PlanItemsPage(
        items=[
            PlanItem(
                id=i.id,
                sender_name=i.sender_name,
                sender_address=i.sender_address,
                subject=i.subject,
                from_category=i.old_id,
                to_category=i.new_id,
                decision=i.decision,  # pyright: ignore[reportArgumentType]  # the table checks the set
                state=i.state,  # pyright: ignore[reportArgumentType]  # the table checks the set
                reason=i.reason,
            )
            for i in found.items
        ],
        page=page,
        has_more=found.has_more,
    )


@router.get(
    "/plan/items",
    response_model=PlanItemsPage,
    dependencies=[Depends(limit("api")), Depends(session)],
    responses={
        401: {"description": "No live session, or the web lock is set"},
        422: {"description": "The page or a category id is invalid"},
        429: {"description": "Too many requests; see Retry-After"},
    },
)
async def read_plan_items(
    request: Request,
    page: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 1,
    from_category: Annotated[uuid.UUID | None, Query(alias="from")] = None,
    to_category: Annotated[uuid.UUID | None, Query(alias="to")] = None,
) -> PlanItemsPage:
    """Return one page of at most 100 items of the open plan; the only filters are the two category ids.

    Args:
        request: The request, whose app holds the database access.
        page: The page, from 1.
        from_category: Only items that leave this category.
        to_category: Only items that go to this category.

    Returns:
        The items with sender name and address and subject as text, and whether another page follows.
    """
    found = await _repository(request).items(page, PAGE_SIZE, ItemQuery(from_category, to_category))
    return _items_page(found, page)


@router.post(
    "/plan/items/search",
    response_model=PlanItemsPage,
    dependencies=[Depends(limit("api")), Depends(session), Depends(csrf), Depends(require_json)],
    responses=_WRITE_RESPONSES,
)
async def search_plan_items(body: ItemSearchRequest, request: Request) -> PlanItemsPage:
    """Return one page of the open plan's items filtered by sender text and sorted, as a read.

    The sender text is personal data, so it travels in the body and never in a URL. Nothing is written.

    Args:
        body: The page, the optional category filters, sender text (part of a name or address, any case) and sort.
        request: The request, whose app holds the database access.

    Returns:
        The same page shape as the items route; without filter and sort it is the same answer.
    """
    query = ItemQuery(body.from_category, body.to_category, body.sender, body.sort, descending=body.order == "desc")
    found = await _repository(request).items(body.page, PAGE_SIZE, query)
    return _items_page(found, body.page)


@router.post(
    "/plan/decisions",
    response_model=DecisionResult,
    dependencies=[Depends(limit("api")), Depends(session), Depends(csrf), Depends(require_json)],
    responses={
        **_WRITE_RESPONSES,
        **_CONFLICT_RESPONSE,
        422: {
            "model": PlanProblem422,
            "description": "The body is malformed; more than 200 ids carry the reason too_many_ids",
            "content": _problem_content("PlanProblem422"),
        },
    },
)
async def post_decision(body: DecisionRequest, request: Request) -> DecisionResult | JSONResponse:
    """Approve or reject a group, named items or the whole plan, if the plan and its item count are still as seen.

    Args:
        body: The plan id and item count the user saw, the scope and the decision.
        request: The request, whose app holds the database access.

    Returns:
        How many items changed, or a 409 (nothing changed), or a 422 for too many ids.
    """
    if isinstance(body.scope, IdsScope) and len(body.scope.ids) > MAX_IDS:
        return JSONResponse(_TOO_MANY_IDS.model_dump(mode="json"), status_code=422, media_type=PROBLEM_MEDIA_TYPE)
    try:
        changed = await _repository(request).decide(
            body.plan_id, body.item_count, _scope_json(body.scope), body.decision
        )
    except PlanConflict:
        return _conflict()
    except PlanMalformed:
        return problem_response(422)
    return DecisionResult(changed=changed)


@router.post(
    "/plan/approve",
    response_model=ApprovalResult,
    dependencies=[Depends(limit("api")), Depends(session), Depends(csrf), Depends(require_json)],
    responses={**_WRITE_RESPONSES, **_CONFLICT_RESPONSE},
)
async def post_approve(body: ApproveRequest, request: Request) -> ApprovalResult | JSONResponse:
    """Approve the plan: pending items are rejected and the plan is scheduled; a repeat returns the same.

    Args:
        body: The plan id and item count the user saw.
        request: The request, whose app holds the database access.

    Returns:
        The state and the time the apply may start, or a 409 (nothing changed).
    """
    try:
        state, apply_after = await _repository(request).approve(body.plan_id, body.item_count)
    except PlanConflict:
        return _conflict()
    except PlanMalformed:
        return problem_response(422)
    return ApprovalResult(state=state, apply_after=apply_after)  # pyright: ignore[reportArgumentType]


@router.post(
    "/plan/{plan_id}/move-back",
    response_model=MoveBackResult,
    dependencies=[Depends(limit("api")), Depends(session), Depends(csrf)],
    responses={**_WRITE_RESPONSES, **_CONFLICT_RESPONSE},
)
async def post_move_back(plan_id: uuid.UUID, request: Request) -> MoveBackResult | JSONResponse:
    """Ask the agent to restore the old labels of an applied plan; a repeat stores nothing new.

    Args:
        plan_id: The applied plan.
        request: The request, whose app holds the database access.

    Returns:
        The request, or a 409 when the plan is not an applied plan of this mailbox.
    """
    try:
        processed = await _repository(request).move_back(plan_id)
    except PlanConflict:
        return _conflict()
    return MoveBackResult(plan_id=plan_id, processed=processed)
