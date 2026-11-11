# pure module (mutation-gated)
"""Rules of the verify-code endpoint (U-web-settings-18): the shape of a code, of the login cookie and of a refusal."""

import re

_CODE = re.compile(r"[0-9]{6}")
_LOGIN_ID = re.compile(r"[A-Za-z0-9_-]{32}")
_GENERIC_REFUSAL: dict[str, object] = {"type": "about:blank", "title": "Bad request", "status": 400}


def code_well_formed(value: object) -> bool:
    """Return True only for exactly six ASCII digits."""
    return isinstance(value, str) and _CODE.fullmatch(value) is not None


def login_id_well_formed(value: str | None) -> bool:
    """Return True only for a login request id as the store makes it: 32 URL-safe characters."""
    return value is not None and _LOGIN_ID.fullmatch(value) is not None


def refusal_body(attempts_left: int | None) -> dict[str, object]:
    """Return the one generic 400 body; ``attemptsLeft`` is in it only when a number is given."""
    if attempts_left is None:
        return dict(_GENERIC_REFUSAL)
    return {**_GENERIC_REFUSAL, "attemptsLeft": attempts_left}
