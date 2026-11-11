from datetime import datetime
from email.message import EmailMessage


def build_message(sender: str, address: str, code: str, expires_at: datetime, now: datetime) -> EmailMessage:
    """Build the plain-text sign-in message: the code and its validity, no link, no code in the subject."""
    raise NotImplementedError
