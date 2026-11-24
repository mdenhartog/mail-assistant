"""The narrow Gmail adapter for category labels and re-sort plans (ADR-0046 item 6, ADR-0060, spec AC-28).

The public operations are exactly: list (labels, mail of a label), read (one mail's labels, the size of a label),
add label, remove label, create label, ensure label, rename a label by id, and replace the managed set. Nothing else
about a mailbox can be changed through it. A reflection test holds the allow-list and reads this source.

Rules the adapter enforces itself, whatever the caller asks:

- A label is changed only when the ``ManagedSet`` of the run knows it: its id is the id of a category of the list, of
  "Other" or of the archive label (a label without a stored id is matched by name until the id is known). Anything
  else raises ``LabelRefused`` and Gmail is not called.
- Mail never gets or loses the archive label through it, so the agent never files mail there (AC-25).
- A label is created by its list name; an existing label of that name is adopted and its mail is left alone (D8).
- A rename patches the one given id. A label deleted by hand while its id is stored is created again once; the
  caller stores the id that comes back.
- Errors and logs carry a code, a status and a reason, never a label name (AC-29).

The guards use label names from the latest listing only for labels without a stored id; call ``list_labels`` at the
start of a run.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from app.adapters.gmail_read import (
    ME,
    GmailLabelError,
    Label,
    LabelNameRejected,
    LabelNameTaken,
    LabelRefused,
    ManagedLabels,
    execute,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.core.managed import ManagedLabel, ManagedSet

__all__ = [
    "GmailLabelError",
    "GmailResort",
    "Label",
    "LabelNameRejected",
    "LabelNameTaken",
    "LabelRefused",
]


class GmailResort:
    """Label and list operations on one mailbox. ``service`` is the Gmail v1 service; ``sleep`` is injectable."""

    def __init__(
        self,
        service: Any,  # noqa: ANN401
        managed: ManagedSet,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Keep the service, the managed labels of this run and the sleep used between retries."""
        self._service = service
        self._sleep = sleep
        self._labels = ManagedLabels(service, managed, self._run)

    def _run(self, request: Any) -> Any:  # noqa: ANN401
        return execute(request, self._sleep)

    def set_managed(self, managed: ManagedSet) -> None:
        """Use the managed labels of a new run (read from the database by the caller)."""
        self._labels.set_managed(managed)

    def list_labels(self) -> list[Label]:
        """All labels of the mailbox, system labels included; refreshes the names the guards use."""
        return self._labels.list_labels()

    def count_mail(self, label_id: str) -> int:
        """The number of mails that carry the label."""
        label = self._run(self._service.users().labels().get(userId=ME, id=label_id))
        return int(label.get("messagesTotal", 0))

    def list_mail(self, label_id: str) -> list[str]:
        """Ids of the mails that carry the label."""
        ids: list[str] = []
        token: str | None = None
        while True:
            request: dict[str, Any] = {"userId": ME, "labelIds": [label_id]}
            if token:
                request["pageToken"] = token
            page = self._run(self._service.users().messages().list(**request))
            ids.extend(item["id"] for item in page.get("messages", []))
            token = page.get("nextPageToken")
            if not token:
                return ids

    def read_mail(self, message_id: str) -> frozenset[str]:
        """The label ids of one mail; nothing else about it is read."""
        mail = self._run(self._service.users().messages().get(userId=ME, id=message_id, fields="id,labelIds"))
        return frozenset(mail.get("labelIds", []))

    def add_label(self, message_id: str, label_id: str) -> str:
        """Add one managed label to a mail; nothing else about the mail changes. Returns the label id used."""
        return self._labels.add_to_mail(message_id, label_id)

    def remove_label(self, message_id: str, label_id: str) -> None:
        """Remove one managed label from a mail; nothing else about the mail changes."""
        self._labels.remove_from_mail(message_id, label_id)

    def create_label(self, label: ManagedLabel) -> Label:
        """Create a managed label by its list name; when Gmail says the name exists, adopt the existing label."""
        return self._labels.create(label)

    def ensure_label(self, label: ManagedLabel) -> Label:
        """The label as Gmail has it now; created again (once) when its stored id was deleted by hand."""
        return self._labels.ensure(label)

    def rename_label(self, label_id: str, new_name: str) -> Label:
        """Rename a managed label by id; the id, the mail and the other settings stay."""
        return self._labels.rename(label_id, new_name)
