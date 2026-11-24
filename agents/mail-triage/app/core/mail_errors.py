"""The two facts about one mail that the Gmail adapter and the re-sort use cases share.

They live here so the adapter never has to import a use case (INT-010 U-18: that import cycle kept the adapter from
loading whenever the use case was broken).
"""

from __future__ import annotations

__all__ = ["MailFailed", "MailGone"]


class MailGone(Exception):  # noqa: N818 - a fact about the mail, not a failure
    """The mail no longer exists in Gmail."""


class MailFailed(Exception):  # noqa: N818 - a fact about one mail, not a failure of the agent
    """Gmail refused or failed an operation on one mail after the adapter's own retries; the mail is not gone."""
