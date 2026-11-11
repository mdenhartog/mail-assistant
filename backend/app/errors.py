"""Problem responses (``application/problem+json``) with generic titles."""

from fastapi import FastAPI

PROBLEM_MEDIA_TYPE = "application/problem+json"


class ProblemError(Exception):
    """A refusal that is answered with a generic problem of the given status."""

    def __init__(self, status: int) -> None:
        """Remember the status."""
        super().__init__(status)
        self.status = status


class RateLimited(Exception):  # noqa: N818 - named after the 429 condition it signals
    """A limit was hit; the client may retry after the given number of seconds."""

    def __init__(self, retry_after_seconds: int) -> None:
        """Remember the wait."""
        super().__init__(retry_after_seconds)
        self.retry_after_seconds = retry_after_seconds


def install_error_handlers(app: FastAPI) -> None:
    """Register the problem handlers on the application."""
    raise NotImplementedError
