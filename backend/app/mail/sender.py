from datetime import datetime
from typing import Protocol


class MailError(Exception):
    """The code could not be sent; carries no cause text, so no address, code or secret can leak through it."""


class MailSender(Protocol):
    """Port that sends the sign-in code to the configured address (ADR-0036); adapters implement it."""

    async def send_code(self, _address: str, _code: str, _expires_at: datetime, /) -> None:
        """Send the code to the address; it is valid until the given expiry.

        Raises:
            MailError: Sending failed for any reason.
        """
        ...
