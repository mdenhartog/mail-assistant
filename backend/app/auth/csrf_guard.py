"""The CSRF dependency: ``require_csrf`` for every state-changing route, and the one refusal both checks share (W-4)."""

from typing import TYPE_CHECKING

from fastapi import Depends, Request

from app.auth.csrf import fetch_site_ok, origin_ok, token_valid
from app.auth.session import Session, client_key, require_session
from app.errors import ProblemError

if TYPE_CHECKING:
    from app.config import Settings

CSRF_HEADER = "X-CSRF-Token"


async def refuse(request: Request, session: Session) -> ProblemError:
    """Record ``csrf_refused`` (once per client and window) and build the one 403 for every CSRF refusal.

    Args:
        request: The refused request.
        session: The session it came with.

    Returns:
        The error to raise: 403 with the generic body.
    """
    await request.app.state.security_events.record(
        "csrf_refused", request.state.request_id, client_key(request), session.username_hash
    )
    return ProblemError(403)


async def require_csrf(request: Request, session: Session = Depends(require_session)) -> None:  # noqa: B008
    """Accept a write only with this session's token, the public ``Origin`` and no cross-site Fetch Metadata.

    The session is checked first (401 when there is none); a refusal is always the same 403.

    Args:
        request: The request.
        session: The live session.

    Raises:
        ProblemError: 403 for a missing or wrong token, a missing or wrong ``Origin`` or a cross-site request.
    """
    settings: Settings = request.app.state.settings
    key = settings.csrf_key.get_secret_value().encode("utf-8")
    allowed = (
        fetch_site_ok(request.headers.get("sec-fetch-site"))
        and origin_ok(settings.public_origin, request.headers.get("origin"))
        and token_valid(key, session.id_hash, request.headers.get(CSRF_HEADER))
    )
    if not allowed:
        raise await refuse(request, session)
