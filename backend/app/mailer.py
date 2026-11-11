from datetime import datetime
from typing import Protocol


class Mailer(Protocol):
    """Port that sends the sign-in code to the configured address (ADR-0036); adapters live elsewhere."""

    async def send_code(self, _address: str, _code: str, _expires_at: datetime, /) -> None:
        """Send the code to the address; it is valid until the given expiry (positional arguments)."""
        ...
