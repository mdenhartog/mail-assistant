"""The facts about one mail or label write that the Gmail adapter and the re-sort use cases share.

They live here so the adapter never has to import a use case (INT-010 U-18: that import cycle kept the adapter from
loading whenever the use case was broken).
"""

from __future__ import annotations

__all__ = ["LabelWritesHeld", "MailFailed", "MailGone"]


class MailGone(Exception):  # noqa: N818 - a fact about the mail, not a failure
    """The mail no longer exists in Gmail."""


class MailFailed(Exception):  # noqa: N818 - a fact about one mail, not a failure of the agent
    """Gmail refused or failed an operation on one mail after the adapter's own retries; the mail is not gone."""


class LabelWritesHeld(Exception):  # noqa: N818 - a wait, not a failure
    """The rename plan is not done, so no label may be created, adopted or renamed yet (R4, ADR-0061 point 1).

    The message is a code. The mail or item that met it is left alone and tried again once the plan is done.
    """
