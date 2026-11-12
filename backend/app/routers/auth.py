"""Sign-in routes under ``/auth``."""

from datetime import datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, StringConstraints
from pydantic.alias_generators import to_camel

from app.auth.request_code import LOGIN_COOKIE_NAME, CodeRequests, login_cookie, require_signin_origin
from app.auth.session import client_key
from app.auth.verify_code import VerifyCodeBody
from app.core.security import public
from app.limit_guard import limit

if TYPE_CHECKING:
    from app.auth.verify_code import VerifyCode

ROUTER_PREFIX = ""  # the sign-in routes live under /auth, outside /api
router = APIRouter(tags=["auth"])

# ---- request-code (U-web-settings-17) ----------------------------------------------------------------------------


class RequestCodeBody(BaseModel):
    """The username a code is asked for: 1 to 64 characters, no control characters."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    username: Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r"^[^\x00-\x1f\x7f]+$")]


class RequestCodeResponse(BaseModel):
    """The same answer for every username."""

    model_config = ConfigDict(frozen=True, alias_generator=to_camel, populate_by_name=True)

    masked_address: str
    expires_at: datetime
    resend_after_seconds: int


def _code_requests(request: Request) -> CodeRequests:
    service: CodeRequests = request.app.state.code_requests
    return service


@router.post(
    "/auth/request-code",
    response_model=RequestCodeResponse,
    dependencies=[Depends(public), Depends(require_signin_origin), Depends(limit("signin"))],
    responses={
        403: {"description": "Wrong or missing Origin"},
        422: {"description": "Invalid username"},
        429: {"description": "Cooldown or hourly cap; see Retry-After"},
    },
)
async def request_code(
    body: RequestCodeBody,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    service: Annotated[CodeRequests, Depends(_code_requests)],
) -> RequestCodeResponse:
    """Ask for a sign-in code; the answer and the cookie are the same for every username.

    Args:
        body: The username.
        request: The request.
        response: The response, which gets the login cookie.
        background: Sends the message after the answer.
        service: The use case.

    Returns:
        The masked address, the expiry and the wait before the next request.
    """
    issued = await service.request(body.username, client_key(request), request.state.request_id)
    response.headers.append("set-cookie", login_cookie(issued.login_request_id))
    if issued.delivery is not None:
        background.add_task(service.deliver, issued.delivery)
    return RequestCodeResponse(
        masked_address=issued.masked_address,
        expires_at=issued.expires_at,
        resend_after_seconds=issued.resend_after_seconds,
    )


# ---- verify-code (U-web-settings-18) -----------------------------------------------------------------------------


@router.post(
    "/auth/verify-code",
    status_code=204,
    dependencies=[Depends(public), Depends(require_signin_origin), Depends(limit("signin"))],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": VerifyCodeBody.model_json_schema(by_alias=True)}},
        }
    },
    responses={
        204: {
            "description": "Signed in: the session cookie is set; the path to go to is in the X-Return-To header",
            "headers": {"X-Return-To": {"schema": {"type": "string"}}},
        },
        400: {"description": "The one generic refusal; attemptsLeft only while the login cookie names a live request"},
        403: {"description": "Wrong or missing Origin"},
        429: {"description": "Too many attempts; see Retry-After"},
    },
)
async def verify_code(request: Request) -> Response:
    """Check the code and sign in; every failure is the same 400.

    The body is read here and checked by the use case, so a malformed body gets the same 400 as a wrong code.

    Args:
        request: The request, with the ``__Host-login`` cookie.

    Returns:
        204 with the session cookie, or the generic 400.
    """
    service: VerifyCode = request.app.state.verify_code
    cookie = request.cookies.get(LOGIN_COOKIE_NAME)
    return await service.verify(await request.body(), cookie, client_key(request), request.state.request_id)
