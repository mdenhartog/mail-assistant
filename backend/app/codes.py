import secrets
from typing import Protocol

_CODE_SPACE = 10**6


class CodeSource(Protocol):
    """Source of sign-in codes."""

    def six_digits(self) -> str:
        """Return a code of exactly six decimal digits."""
        ...


class SecretsCodeSource:
    """Production code source."""

    def six_digits(self) -> str:
        """Return a code of exactly six decimal digits, zero-padded."""
        return f"{secrets.randbelow(_CODE_SPACE):06d}"
