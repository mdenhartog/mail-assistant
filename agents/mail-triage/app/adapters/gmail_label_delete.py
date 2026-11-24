"""Deleting one empty Gmail label by id (ADR-0060 point 5, spec AC 7, 8, 10b, 21, 22, 30).

``delete`` is the only place in the agent that calls ``labels().delete``. It deletes a label only when everything
below holds, read from Gmail itself just before the call:

- the label is of type ``user`` and is not a system label, neither by id nor by name (``CATEGORY_*`` included);
- its message and thread counts are 0, and a list that includes spam and trash finds no mail on it;
- no other label is nested under it, and no Gmail filter adds it to mail.

Any Gmail error or unclear answer counts as "not empty": the label stays and ``LabelDeleteRefused`` is raised. The
final re-read and the delete call are adjacent: nothing else is called between them, so the window for a mail that
arrives is that one gap (accepted risk A2). Errors and logs carry a code, a status and a reason, never a label name.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from googleapiclient.errors import HttpError

from app.adapters.gmail_read import ME, GmailLabelError, error_reason, execute

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

USER_TYPE: Final = "user"
CATEGORY_PREFIX: Final = "CATEGORY_"
SYSTEM_IDS: Final = frozenset({"INBOX", "SENT", "DRAFT", "SPAM", "TRASH", "UNREAD", "STARRED", "IMPORTANT", "CHAT"})
# Display names of system labels in other case or wording; no user label may be deleted under one of them.
_SYSTEM_NAMES: Final = frozenset(
    {name.casefold() for name in SYSTEM_IDS} | {"drafts", "sent mail", "chats", "all mail", "bin", "junk"}
)
CHECK_FAILED: Final = "label_check_failed"


class LabelDeleteRefused(ValueError):  # noqa: N818  # a refusal, not a failure of Gmail
    """The label is kept. ``code`` says why; it is also the message and never holds a label name."""

    def __init__(self, code: str) -> None:
        """Keep the code as the message."""
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class LabelState:
    """One read of a label: what the delete decision rests on."""

    id: str
    name: str
    type: str
    messages_total: int
    threads_total: int
    has_children: bool


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_system(label_id: str, name: str) -> tuple[bool, bool]:
    """Whether the id and the name belong to a system label."""
    by_id = label_id in SYSTEM_IDS or label_id.startswith(CATEGORY_PREFIX)
    folded = name.casefold()
    by_name = folded in _SYSTEM_NAMES or folded.startswith(CATEGORY_PREFIX.casefold())
    return by_id, by_name


class GmailLabelDelete:
    """Read the facts about a label and delete it by id when it is safe. ``sleep`` is injectable for the retries."""

    def __init__(self, service: Any, sleep: Callable[[float], None] = time.sleep) -> None:  # noqa: ANN401
        """Keep the Gmail service and the sleep function used between retries."""
        self._service = service
        self._sleep = sleep

    def _call(self, request: Any) -> Any:  # noqa: ANN401
        """Execute with retries; a Gmail error leaves as ``GmailLabelError`` with the status and reason only."""
        try:
            return execute(request, self._sleep)
        except HttpError as error:
            raise GmailLabelError(error.resp.status, error_reason(error)) from None

    def read_label(self, label_id: str) -> LabelState:
        """Type, counts and whether another label is nested under this one, read from Gmail now."""
        listing = self._call(self._service.users().labels().list(userId=ME))
        entries = listing.get("labels", []) if isinstance(listing, dict) else None
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise LabelDeleteRefused(CHECK_FAILED)
        names = {str(e.get("id")): str(e.get("name")) for e in entries}
        if label_id not in names:
            raise LabelDeleteRefused("label_unknown")
        name = names[label_id]
        prefix = f"{name.casefold()}/"
        has_children = any(
            other.casefold().startswith(prefix) for other_id, other in names.items() if other_id != label_id
        )
        label = self._call(self._service.users().labels().get(userId=ME, id=label_id))
        if not (
            isinstance(label, dict)
            and isinstance(label.get("type"), str)
            and _is_count(label.get("messagesTotal"))
            and _is_count(label.get("threadsTotal"))
        ):
            raise LabelDeleteRefused(CHECK_FAILED)
        return LabelState(label_id, name, label["type"], label["messagesTotal"], label["threadsTotal"], has_children)

    def labels_in_filters(self) -> frozenset[str]:
        """Every label id that a Gmail filter of the user adds to mail (``addLabelIds``)."""
        answer = self._call(self._service.users().settings().filters().list(userId=ME))
        filters = answer.get("filter", []) if isinstance(answer, dict) else None
        if not isinstance(filters, list):
            raise LabelDeleteRefused(CHECK_FAILED)
        found: set[str] = set()
        for entry in filters:
            action = entry.get("action", {}) if isinstance(entry, dict) else None
            added = action.get("addLabelIds", []) if isinstance(action, dict) else None
            if not isinstance(added, list) or not all(isinstance(item, str) for item in added):
                raise LabelDeleteRefused(CHECK_FAILED)
            found.update(added)
        return frozenset(found)

    def has_mail_including_trash(self, label_id: str) -> bool:
        """Whether one mail with the label exists, spam and trash included. An unclear answer says yes."""
        request = (
            self._service.users().messages().list(userId=ME, labelIds=[label_id], includeSpamTrash=True, maxResults=1)
        )
        answer = self._call(request)
        if not isinstance(answer, dict):
            return True
        messages = answer.get("messages", [])
        return not isinstance(messages, list) or bool(messages)

    def delete(self, label_id: str) -> None:
        """Delete the label by id, or raise ``LabelDeleteRefused`` and leave it as it is.

        A Gmail error while checking refuses the label (it counts as not empty); an error of the delete call itself
        is raised as ``GmailLabelError``.
        """
        try:
            self._check(label_id)
        except LabelDeleteRefused as refusal:
            logger.info("label delete refused: code=%s", refusal.code)
            raise
        except GmailLabelError as failure:
            logger.warning("label delete check failed: status=%s reason=%s", failure.status, failure.reason)
            raise LabelDeleteRefused(CHECK_FAILED) from None
        self._call(self._service.users().labels().delete(userId=ME, id=label_id))

    def _check(self, label_id: str) -> None:
        """Every check; the last step is the final re-read, so the caller deletes right after it."""
        self._require_deletable(self.read_label(label_id))
        if label_id in self.labels_in_filters():
            raise LabelDeleteRefused("label_in_filter")
        if self.has_mail_including_trash(label_id):
            raise LabelDeleteRefused("label_has_mail_listed")
        self._require_deletable(self.read_label(label_id))

    @staticmethod
    def _require_deletable(state: LabelState) -> None:
        if state.type != USER_TYPE:
            raise LabelDeleteRefused("label_not_user_type")
        by_id, by_name = _is_system(state.id, state.name)
        if by_id:
            raise LabelDeleteRefused("label_is_system_id")
        if by_name:
            raise LabelDeleteRefused("label_is_system_name")
        if state.messages_total or state.threads_total:
            raise LabelDeleteRefused("label_has_mail")
        if state.has_children:
            raise LabelDeleteRefused("label_has_child")
