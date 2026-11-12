import asyncio
import logging
import ssl
from datetime import datetime

import aiosmtplib

from app.clock import Clock
from app.config import Settings
from app.mail.message import build_message
from app.mail.sender import MailError

# The library logs protocol detail; keep it out of the logs (W-15, W-16).
logging.getLogger("aiosmtplib").setLevel(logging.WARNING)

_log = logging.getLogger(__name__)


class SmtpMailSender:
    """Mail sender over SMTP: STARTTLS is required and the server certificate is always verified."""

    def __init__(self, settings: Settings, clock: Clock, *, tls_context: ssl.SSLContext | None = None) -> None:
        """Keep the settings; the TLS context defaults to the system trust store.

        Raises:
            ValueError: The given TLS context does not verify the server certificate and host name.
        """
        context = tls_context if tls_context is not None else ssl.create_default_context()
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            raise ValueError("the TLS context must verify the server certificate and host name")
        self._settings = settings
        self._clock = clock
        self._context = context

    async def send_code(self, address: str, code: str, expires_at: datetime, /) -> None:
        """Send the code; the whole call ends within the configured timeout.

        Raises:
            MailError: Sending failed for any reason; the error carries no cause, address, code or secret.
        """
        settings = self._settings
        message = build_message(settings.smtp_from, address, code, expires_at, self._clock.now())
        timeout = settings.smtp_timeout_seconds
        failure: str | None = None
        try:
            async with asyncio.timeout(timeout):
                await aiosmtplib.send(
                    message,
                    hostname=settings.smtp_host,
                    port=settings.smtp_port,
                    username=settings.smtp_user,
                    password=settings.smtp_password.get_secret_value(),
                    start_tls=True,
                    use_tls=False,
                    tls_context=self._context,
                    timeout=timeout,
                )
        except (aiosmtplib.SMTPException, OSError, TimeoutError) as error:
            failure = type(error).__name__
        if failure is not None:
            _log.warning("mail send failed: %s", failure)
            # Raised outside the handler so the error has no cause or context that could carry text.
            raise MailError("mail send failed")
