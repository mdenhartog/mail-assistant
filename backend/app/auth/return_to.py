# pure module (mutation-gated)
"""Allow-list for the post-sign-in return path (AC-6, W-2)."""

DEFAULT_RETURN_TO = "/settings"
_ALLOWED = frozenset({DEFAULT_RETURN_TO})


def safe_return_to(value: str | None) -> str:
    """Return the value when it is an allowed relative path, else `/settings`."""
    if value in _ALLOWED:
        return str(value)
    return DEFAULT_RETURN_TO
