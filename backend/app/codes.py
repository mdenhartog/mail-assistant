from typing import Protocol


class CodeSource(Protocol):
    """Source of sign-in codes."""

    def six_digits(self) -> str:
        """Return a code of exactly six decimal digits."""
        ...


class SecretsCodeSource:
    """Production code source."""

    def six_digits(self) -> str:
        """Return a code of exactly six decimal digits."""
        raise NotImplementedError
