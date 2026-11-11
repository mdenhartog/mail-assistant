import ssl
from datetime import datetime

from app.clock import Clock
from app.config import Settings


class SmtpMailSender:
    """Mail sender over SMTP with a required STARTTLS upgrade and a verified server certificate."""

    def __init__(self, settings: Settings, clock: Clock, *, tls_context: ssl.SSLContext | None = None) -> None:
        """Store the settings; refuse a TLS context that does not verify the server certificate."""
        raise NotImplementedError

    async def send_code(self, address: str, code: str, expires_at: datetime, /) -> None:
        """Send the code; raise MailError on any failure."""
        raise NotImplementedError
