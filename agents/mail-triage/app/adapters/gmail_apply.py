"""Gmail for the apply and the move back: the ``ApplyMailbox`` port on the narrow adapters (INT-004, ADR-0046).

Reads go through ``GmailReader`` and every write through ``GmailResort``, so its guards stay in force: only labels under
``Assistant/`` are added or removed, nothing is deleted, archived or sent. This module only maps what Gmail says to the
port's two facts about one mail: ``MailGone`` (the mail does not exist any more, Gmail answers 404) and ``MailFailed``
(anything else Gmail or a guard refuses). Failures that are not about one mail (a lost connection) pass through.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Final

from googleapiclient.errors import HttpError

from app.adapters.gmail_read import HTTP_NOT_FOUND, GmailReader
from app.adapters.gmail_resort import GmailResort, LabelRefused
from app.usecases.resort_apply import MailFailed, MailGone

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.gmail_read import FetchedMail

__all__ = ["GmailApply"]

_REFUSED: Final = (HttpError, LabelRefused)


class GmailApply:
    """The ``ApplyMailbox`` port on a Gmail v1 service. ``sleep`` is injectable so tests do not wait."""

    def __init__(self, service: Any, sleep: Callable[[float], None] = time.sleep) -> None:  # noqa: ANN401
        """Build the reader and the narrow label adapter on one service."""
        self._reader = GmailReader(service, sleep)
        self._resort = GmailResort(service, sleep)

    def label_names(self) -> dict[str, str]:
        """Label id to label name (this also refreshes the names the label guards use)."""
        return {label.id: label.name for label in self._resort.list_labels()}

    def fetch(self, message_id: str) -> FetchedMail | None:
        """Headers, text and label ids of one mail; ``None`` when it no longer exists."""
        try:
            return self._reader.fetch(message_id)
        except HttpError as error:
            if error.resp.status == HTTP_NOT_FOUND:
                return None
            raise MailFailed from error

    def ensure_label(self, name: str) -> str:
        """The id of the label ``name``: the one that exists, else a new one (also when another run made it first)."""
        try:
            existing = next((label for label in self._resort.list_labels() if label.name == name), None)
            return existing.id if existing is not None else self._resort.create_label(name).id
        except _REFUSED as error:
            raise MailFailed from error

    def add_label(self, message_id: str, label_id: str) -> None:
        """Add one ``Assistant/`` label (idempotent in Gmail); ``MailGone`` when the mail is gone."""
        self._change(lambda: self._resort.add_label(message_id, label_id))

    def remove_label(self, message_id: str, label_id: str) -> None:
        """Remove one ``Assistant/`` label (idempotent in Gmail); ``MailGone`` when the mail is gone."""
        self._change(lambda: self._resort.remove_label(message_id, label_id))

    def count_mail(self, label_id: str) -> int:
        """The number of mails that carry the label."""
        try:
            return self._resort.count_mail(label_id)
        except HttpError as error:
            raise MailFailed from error

    @staticmethod
    def _change(call: Callable[[], None]) -> None:
        try:
            call()
        except HttpError as error:
            if error.resp.status == HTTP_NOT_FOUND:
                raise MailGone from error
            raise MailFailed from error
        except LabelRefused as error:
            raise MailFailed from error
