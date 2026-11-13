"""Session routes of the web page: ``GET /api/session`` and ``POST /auth/logout`` (U-web-settings-19).

Kept apart from the sign-in routes of ``routers/auth.py``; both live outside the ``/api`` prefix rule of the other
routers, so this module sets an empty prefix and spells the full paths.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.auth.csrf import csrf_token, fetch_site_ok
from app.auth.csrf_guard import refuse
from app.auth.expiry import next_idle_expiry
from app.auth.mask import mask_address
from app.auth.session import COOKIE_NAME, Session, SessionStore, clear_session_cookie, client_key
from app.core.security import csrf, session
from app.limit_guard import limit

if TYPE_CHECKING:
    from app.config import Settings

ROUTER_PREFIX = ""  # the paths below are complete: `/api/session` and `/auth/logout`
router = APIRouter(tags=["session"])


class SessionInfo(BaseModel):
    """What the page needs to know about the signed-in session; no username and no full address."""

    model_config = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)

    masked_address: str
    csrf_token: str
    idle_expires_at: datetime
    absolute_expires_at: datetime
    notice_interval_minutes: int


@router.get(
    "/api/session",
    response_model=SessionInfo,
    dependencies=[Depends(limit("api")), Depends(session)],
    responses={
        401: {"description": "No live session"},
        403: {"description": "Not a same-origin request"},
        429: {"description": "Too many requests; see Retry-After"},
    },
)
async def read_session(request: Request, current: Session = Depends(session)) -> SessionInfo:  # noqa: B008
    """Return the masked address, the CSRF token and the expiry times of the session.

    Only a same-origin request (``Sec-Fetch-Site`` absent or ``same-origin``) gets the token.

    Args:
        request: The request.
        current: The live session.

    Returns:
        The session information.

    Raises:
        ProblemError: 403 (through ``refuse``) for a request that is not same-origin.
    """
    if not fetch_site_ok(request.headers.get("sec-fetch-site")):
        raise await refuse(request, current)
    settings: Settings = request.app.state.settings
    now = request.app.state.clock.now()
    return SessionInfo(
        masked_address=mask_address(settings.email_address),
        csrf_token=csrf_token(settings.csrf_key.get_secret_value().encode("utf-8"), current.id_hash),
        idle_expires_at=next_idle_expiry(now, current.created_at),
        absolute_expires_at=current.absolute_expires_at,
        notice_interval_minutes=settings.notice_interval_minutes,
    )


@router.post(
    "/auth/logout",
    status_code=204,
    dependencies=[Depends(limit("api")), Depends(session), Depends(csrf)],
    responses={
        401: {"description": "No live session"},
        403: {"description": "CSRF check failed"},
        429: {"description": "Too many requests; see Retry-After"},
    },
)
async def logout(request: Request) -> Response:
    """End the session on the server and clear the cookie.

    Args:
        request: The request; its cookie names the session to delete.

    Returns:
        An empty 204 that clears the ``__Host-session`` cookie.
    """
    store: SessionStore = request.app.state.sessions
    await store.delete(request.cookies[COOKIE_NAME], request.state.request_id, client_key(request))
    return Response(status_code=204, headers={"Set-Cookie": clear_session_cookie()})
