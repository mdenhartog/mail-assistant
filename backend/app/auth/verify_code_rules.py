# pure module (mutation-gated)
"""Rules of the verify-code endpoint (U-web-settings-18): the shape of a code, of the login cookie and of a refusal."""


def code_well_formed(value: object) -> bool:
    """Return True only for exactly six ASCII digits."""
    raise NotImplementedError


def login_id_well_formed(value: str | None) -> bool:
    """Return True only for a login request id as the store makes it: 32 URL-safe characters."""
    raise NotImplementedError


def refusal_body(attempts_left: int | None) -> dict[str, object]:
    """Return the one generic 400 body; ``attemptsLeft`` is in it only when a number is given."""
    raise NotImplementedError
