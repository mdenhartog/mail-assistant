import math
from datetime import datetime
from email.message import EmailMessage

SUBJECT = "Your Mail Assistant sign-in code"
_SECONDS_PER_MINUTE = 60


def _aware(*values: datetime) -> None:
    for value in values:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")


def _validity(expires_at: datetime, now: datetime) -> str:
    _aware(expires_at, now)
    seconds = (expires_at - now).total_seconds()
    if seconds <= 0:
        raise ValueError("expiry must lie after now")
    minutes = math.ceil(seconds / _SECONDS_PER_MINUTE)
    return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"


def build_message(sender: str, address: str, code: str, expires_at: datetime, now: datetime) -> EmailMessage:
    """Build the plain-text sign-in message (ADR-0036).

    The body holds the code and its validity in whole minutes; there is no link and no request detail,
    and the subject never holds the code.

    Raises:
        ValueError: A datetime is naive, or the expiry is not after `now`.
    """
    validity = _validity(expires_at, now)
    message = EmailMessage()
    message["From"] = sender
    message["To"] = address
    message["Subject"] = SUBJECT
    message.set_content(
        f"Your sign-in code is {code}.\n\n"
        f"It is valid for {validity}. Enter it on the sign-in page.\n"
        "If you did not ask for a code, ignore this message.\n"
    )
    return message
